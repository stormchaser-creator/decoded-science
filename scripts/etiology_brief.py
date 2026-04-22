"""Clinical Etiology ("Why Me") mode — fan-out orchestrator + synthesizer.

Usage:
    python scripts/etiology_brief.py run \
        --question "How does GBM start in an individual patient?" \
        --condition glioblastoma \
        --frames germline_predisposition,cell_of_origin,aging_senescence \
        [--patient-context '{"age":36,"sex":"F","location":"brainstem"}']

Architecture:
    1. Creates an rf_etiology_briefs row.
    2. For each frame: resolves seeds (default + condition-aware), interpolates
       target templates with {condition}, runs Discovery traversal in parallel
       against entity_edges_extended. Stores discovery_run_id in
       rf_etiology_frame_runs.
    3. Structural synthesis over all frame runs:
       - convergent_nodes: concepts appearing in paths of ≥3 distinct frames
       - bridge_nodes: concepts spanning ≥2 frames (shared mid-graph nodes)
       - patient_variable_factors: convergent nodes from frames flagged
         patient_variable=TRUE (germline, microbiome, lifestyle, etc.)
       - gaps: frames where <3 paths scored (substrate thin)
    4. Narrative synthesis via Claude Sonnet: reads the structural object
       and produces a clinician-facing markdown brief with sections for
       convergent attractors, bridges, patient-variable factors, gaps, and
       orderable stratifying questions.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras


class _DecimalEncoder(json.JSONEncoder):
    """psycopg2 returns numeric(...) columns as Decimal — default json can't
    serialize those. Cast to float for JSONB storage."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _json_dumps(obj) -> str:
    return json.dumps(obj, cls=_DecimalEncoder)

# Make sibling scripts importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("etiology")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://whit@Whits-Mac-mini.local:5432/encoded_human")

# ─────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────

def db_connect():
    """Short-lived connection used as a context manager. Autocommit off so
    callers decide commit boundaries. Each helper opens its own connection
    to avoid poisoning the shared state when one thread errors."""
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn


def load_frames(frame_ids: list[str]) -> list[dict[str, Any]]:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, label, description, frame_question, default_seeds,
                      target_templates, patient_variable, stratifying_questions
               FROM rf_etiology_frames WHERE id = ANY(%s) AND active""",
            (frame_ids,),
        )
        return [dict(r) for r in cur.fetchall()]


def create_brief(question: str, condition: str | None,
                 patient_context: dict | None, frame_ids: list[str]) -> str:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rf_etiology_briefs
                 (question, condition, patient_context, frames_requested, status)
               VALUES (%s, %s, %s::jsonb, %s, 'fanning_out')
               RETURNING id::text""",
            (question, condition, json.dumps(patient_context or {}), frame_ids),
        )
        brief_id = cur.fetchone()["id"]
        conn.commit()
    return brief_id


def update_brief(brief_id: str, **fields) -> None:
    if not fields:
        return
    cols = []
    vals = []
    for k, v in fields.items():
        if k == "structural_synthesis":
            cols.append(f"{k} = %s::jsonb")
            vals.append(_json_dumps(v))
        else:
            cols.append(f"{k} = %s")
            vals.append(v)
    vals.append(brief_id)
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE rf_etiology_briefs SET {', '.join(cols)} WHERE id = %s",
            vals,
        )
        conn.commit()


def create_frame_run(brief_id: str, frame_id: str,
                     seeds: list[str], targets: list[str]) -> str:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rf_etiology_frame_runs
                 (brief_id, frame_id, resolved_seeds, resolved_targets, status)
               VALUES (%s, %s, %s, %s, 'running')
               RETURNING id::text""",
            (brief_id, frame_id, seeds, targets),
        )
        rid = cur.fetchone()["id"]
        conn.commit()
    return rid


def update_frame_run(run_id: str, **fields) -> None:
    if not fields:
        return
    cols = [f"{k} = %s" for k in fields]
    vals = list(fields.values()) + [run_id]
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE rf_etiology_frame_runs SET {', '.join(cols)}, "
            f"completed_at = NOW() WHERE id = %s",
            vals,
        )
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────
# Per-frame Discovery traversal
# ─────────────────────────────────────────────────────────────────────────
# We call run_discovery from discovery.py directly rather than going through
# the full foundry_question_orchestrator (which also handles decomposition,
# density, and acquisition). For the etiology mode, decomposition is
# replaced by the frame's declared seeds+targets, and we assume the
# connectome substrate is what it is — the synthesizer reports gaps
# explicitly rather than triggering acquisition mid-fan-out.

def run_frame_discovery(frame: dict, condition: str | None,
                        extra_seeds: list[str] | None = None,
                        max_hops: int = 3, keep_top: int = 20,
                        path_limit: int = 200) -> dict:
    """Run Discovery for one frame. Returns dict with discovery_run_id
    and the top paths."""
    from discovery import run_discovery  # lazy import

    seeds = list(frame["default_seeds"])
    if extra_seeds:
        seeds.extend(extra_seeds)
    # Dedupe preserving order
    seen = set()
    seeds = [s for s in seeds if not (s.lower() in seen or seen.add(s.lower()))]

    # Interpolate {condition} into target templates
    cond = (condition or "").strip()
    targets = []
    for t in frame["target_templates"]:
        if "{condition}" in t:
            if cond:
                targets.append(t.format(condition=cond))
        else:
            targets.append(t)
    # Dedupe targets
    seen = set()
    targets = [t for t in targets if not (t.lower() in seen or seen.add(t.lower()))]

    topic = f"[{frame['id']}] {frame['frame_question']}"
    log.info("Frame %s: seeds=%s targets=%s", frame["id"], seeds[:3], targets[:3])

    run_id = run_discovery(
        seed_topic=topic,
        seeds=seeds,
        targets=targets or None,
        max_hops=max_hops,
        min_hops=2,
        path_limit=path_limit,
        min_cross_ops=1,
        keep_top=keep_top,
    )
    return {"frame_id": frame["id"], "discovery_run_id": run_id}


# ─────────────────────────────────────────────────────────────────────────
# Structural synthesizer
# ─────────────────────────────────────────────────────────────────────────

def fetch_paths_for_run(run_id: str) -> list[dict]:
    """Read scored paths for a discovery run. Column names match pearl_path_scores."""
    if not run_id:
        return []
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT path_entity_names   AS names,
                      path_predicates     AS preds,
                      path_operations     AS ops,
                      hops, composite_score,
                      novelty_score, coherence_score, plausibility_score,
                      contradiction_load, op_boundary_crossings
               FROM pearl_path_scores
               WHERE run_id = %s
               ORDER BY rank""",
            (run_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def structural_synthesize(brief_id: str, frame_runs: list[dict]) -> dict:
    """Compute convergent nodes, bridge nodes, gaps, patient-variable factors.

    frame_runs is a list of {frame_id, frame (full row), discovery_run_id}.
    """
    # Per-frame node set (mid-graph nodes only, not seeds/targets)
    per_frame_mid_nodes: dict[str, set[str]] = {}
    # Per-frame path sample (top 10)
    per_frame_paths: dict[str, list[dict]] = {}
    # Per-frame stats
    per_frame_stats: dict[str, dict] = {}

    for fr in frame_runs:
        run_id = fr.get("discovery_run_id")
        paths = fetch_paths_for_run(run_id) if run_id else []
        per_frame_paths[fr["frame_id"]] = paths[:10]
        per_frame_stats[fr["frame_id"]] = {
            "label": fr["frame"]["label"],
            "paths_scored": len(paths),
            "top_score": float(paths[0]["composite_score"]) if paths else 0.0,
            "thin": len(paths) < 3,
        }
        mids = set()
        for p in paths:
            names = p.get("names") or []
            # first node is a seed, last is target; middle nodes are bridges
            for n in names[1:-1]:
                if n and len(n) > 2:
                    mids.add(n.lower())
        per_frame_mid_nodes[fr["frame_id"]] = mids

    # Convergent nodes: appear in ≥3 frames' mid-node sets
    node_to_frames: dict[str, set[str]] = {}
    for fid, mids in per_frame_mid_nodes.items():
        for n in mids:
            node_to_frames.setdefault(n, set()).add(fid)

    convergent = [
        {"node": n, "frames": sorted(frames), "frame_count": len(frames)}
        for n, frames in node_to_frames.items()
        if len(frames) >= 3
    ]
    convergent.sort(key=lambda x: -x["frame_count"])

    # Bridge nodes: appear in exactly 2 frames (cross-silo arbitrage candidates)
    bridges = [
        {"node": n, "frames": sorted(frames)}
        for n, frames in node_to_frames.items()
        if len(frames) == 2
    ]
    bridges.sort(key=lambda x: x["node"])

    # Gaps: frames with <3 scored paths
    gaps = [
        {"frame_id": fid, "label": s["label"], "paths": s["paths_scored"]}
        for fid, s in per_frame_stats.items() if s["thin"]
    ]

    # Patient-variable factors: convergent+bridge nodes whose frames include
    # at least one patient_variable frame
    pv_frame_ids = {fr["frame_id"] for fr in frame_runs
                    if fr["frame"].get("patient_variable")}
    patient_variable = []
    for item in convergent + bridges:
        overlap = pv_frame_ids.intersection(item["frames"])
        if overlap:
            patient_variable.append({**item, "patient_variable_frames": sorted(overlap)})

    return {
        "per_frame_stats": per_frame_stats,
        "per_frame_paths_sample": per_frame_paths,
        "convergent_nodes": convergent,
        "bridge_nodes": bridges[:40],  # cap for output
        "gaps": gaps,
        "patient_variable_factors": patient_variable[:25],
    }


# ─────────────────────────────────────────────────────────────────────────
# Narrative synthesizer (Claude)
# ─────────────────────────────────────────────────────────────────────────

NARRATIVE_SYSTEM = """You are a clinical etiologist writing a "why me" brief
for a physician. You integrate evidence across ten normally-siloed literatures
(genomics, developmental biology, aging, immunology, microbiome, etc.) to
answer why a specific condition may have arisen in a specific patient.

You are NOT writing a review article. You are writing a clinician-facing brief
that is:
  - Honest about uncertainty
  - Explicit about patient-variable vs baseline factors
  - Specific about which questions to ask THIS patient and which labs/records
    would most change the picture
  - Grounded in the frame data provided — do not fabricate mechanisms the
    data does not support
  - Aware that tumor boards already cover diagnosis/treatment — your value is
    in the etiologic integration they do not produce

Use clean markdown. No emojis. Do not overclaim. Prefer the word "contributory"
over "cause" when the evidence is correlational or multi-factor."""


def narrative_synthesize(question: str, condition: str | None,
                         patient_context: dict | None,
                         frames: list[dict], structural: dict,
                         projectish_id: str) -> str:
    """Claude Sonnet reads the structural synthesis and drafts the brief.
    Falls back to a structured template if Claude is unavailable."""
    if not (HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY")):
        log.warning("Claude unavailable — producing structured template brief")
        return render_template_brief(question, condition, patient_context,
                                     frames, structural)

    # Build the prompt with structural data
    frame_summaries = []
    for fr in frames:
        fid = fr["id"]
        stats = structural["per_frame_stats"].get(fid, {})
        sample_paths = structural["per_frame_paths_sample"].get(fid, [])
        paths_text = "\n".join(
            f"    - {' → '.join((p.get('names') or [])[:5])}"
            for p in sample_paths[:5]
        ) or "    (no paths found — substrate thin)"
        frame_summaries.append(
            f"### Frame: {fr['label']}\n"
            f"Question: {fr['frame_question']}\n"
            f"Seeds: {', '.join(fr['default_seeds'][:6])}\n"
            f"Paths scored: {stats.get('paths_scored', 0)}\n"
            f"Top paths:\n{paths_text}\n"
            f"Stratifying questions for this patient: {fr.get('stratifying_questions') or []}"
        )

    convergent_text = "\n".join(
        f"  - **{c['node']}** — appears in {c['frame_count']} frames: {', '.join(c['frames'])}"
        for c in structural["convergent_nodes"][:10]
    ) or "  (no node appears in ≥3 frames — substrate too thin or frames too orthogonal)"

    bridge_text = "\n".join(
        f"  - **{b['node']}** — bridges: {' ↔ '.join(b['frames'])}"
        for b in structural["bridge_nodes"][:15]
    ) or "  (no cross-silo bridge nodes detected)"

    pv_text = "\n".join(
        f"  - **{p['node']}** (from {', '.join(p.get('patient_variable_frames', []))})"
        for p in structural["patient_variable_factors"][:10]
    ) or "  (no patient-variable factors detected from the frames run)"

    gaps_text = "\n".join(
        f"  - **{g['label']}**: only {g['paths']} paths (connectome substrate thin)"
        for g in structural["gaps"]
    ) or "  (no frames are substrate-thin)"

    pc_text = json.dumps(patient_context or {}, indent=2)

    user_prompt = f"""Write a clinician-facing "Why Me" brief answering:

QUESTION: {question}
CONDITION: {condition or '(not specified)'}
PATIENT CONTEXT: {pc_text}

You have run {len(frames)} parallel etiologic frame analyses against a
connectome of {270000}+ edges. Here is the data:

---
## Frame-by-frame outputs

{chr(10).join(frame_summaries)}

---
## Structural synthesis

### Convergent nodes (concepts appearing in ≥3 frames' paths)
{convergent_text}

### Bridge nodes (concepts spanning 2 normally-siloed frames)
{bridge_text}

### Patient-variable factors (convergent/bridge nodes from frames that vary person-to-person)
{pv_text}

### Gaps (frames where substrate is thin — literature may not support this frame)
{gaps_text}

---
## Your task

Write a markdown brief with these sections:

1. **Question and scope** — 1-2 sentences naming the question and what the
   brief is and is not. (It is not a diagnostic or treatment plan. It is an
   etiologic integration.)

2. **What a standard tumor board would already cover** — 1 paragraph
   acknowledging the genomic, pathologic, and treatment frame the patient
   already has or will have.

3. **The integrated picture** — the core of the brief. Walk through the
   convergent attractors and the bridge nodes. Explain the mechanistic
   chain the graph is implying across frames. Be honest: these are mostly
   established mechanisms viewed through a new lens, not brand-new findings.

4. **Patient-variable contributory factors** — list the factors most likely
   to differ person-to-person and therefore most worth asking about for
   THIS patient. For each: what it is, why it may contribute, what would
   confirm or refute it for this patient (a lab, a history question, a
   family-history probe).

5. **Orderable next steps** — a concrete, prioritized list of questions to
   ask the patient, labs/records to obtain, and any imaging or genetic
   testing that would meaningfully change the integrated picture.

6. **Gaps and honest uncertainty** — frames where the connectome is too
   thin to say anything useful, and what that means (either the literature
   is silent, or we have not yet ingested enough of it — say which).

7. **Citations and evidence trail** — note that the full path evidence
   appendix is linked separately; do not reproduce it here.

Guidance:
- Do NOT overclaim. Prefer "contributory" to "cause."
- Do NOT invent mechanisms the frame data does not support.
- Do NOT turn this into a review article — it is a clinical brief.
- Be specific. "Chronic inflammation" is less useful than "chronic
  inflammation, specifically the IL-6/TNF-α axis that frame X and frame Y
  both converged on."
- Write as if the reader is a physician colleague, not a patient or a
  grant reviewer."""

    client = Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8000,
        system=NARRATIVE_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return msg.content[0].text


def render_template_brief(question: str, condition: str | None,
                          patient_context: dict | None,
                          frames: list[dict], structural: dict) -> str:
    """Structured template fallback when Claude isn't available."""
    lines = [
        f"# Clinical Etiology Brief: {question}",
        "",
        f"**Condition:** {condition or 'unspecified'}",
        f"**Patient context:** {json.dumps(patient_context or {})}",
        "",
        "## Frame-by-frame findings",
        "",
    ]
    for fr in frames:
        fid = fr["id"]
        stats = structural["per_frame_stats"].get(fid, {})
        lines += [
            f"### {fr['label']}",
            f"*{fr['frame_question']}*",
            f"- Paths scored: {stats.get('paths_scored', 0)}",
            f"- Top score: {stats.get('top_score', 0):.3f}",
            f"- Stratifying questions: {fr.get('stratifying_questions') or []}",
            "",
        ]
    lines += ["## Convergent nodes (≥3 frames)", ""]
    for c in structural["convergent_nodes"][:15]:
        lines.append(f"- **{c['node']}** — {c['frame_count']} frames: {', '.join(c['frames'])}")
    lines += ["", "## Bridge nodes", ""]
    for b in structural["bridge_nodes"][:15]:
        lines.append(f"- **{b['node']}** — {' ↔ '.join(b['frames'])}")
    lines += ["", "## Gaps", ""]
    for g in structural["gaps"]:
        lines.append(f"- {g['label']}: {g['paths']} paths (thin)")
    lines.append("")
    lines.append("*(Claude narrative synthesizer unavailable — structured template output.)*")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────

def run_brief(question: str, condition: str | None,
              patient_context: dict | None, frame_ids: list[str],
              max_hops: int = 3, keep_top: int = 20,
              path_limit: int = 200, fan_out_workers: int = 1) -> str:
    brief_id = create_brief(question, condition, patient_context, frame_ids)
    log.info("Brief %s created — fanning out %d frames", brief_id[:8], len(frame_ids))

    try:
        frames = load_frames(frame_ids)
        if len(frames) != len(frame_ids):
            missing = set(frame_ids) - {f["id"] for f in frames}
            raise RuntimeError(f"Missing frames in rf_etiology_frames: {missing}")

        frame_runs: list[dict] = []
        futures = {}
        t0 = time.time()

        # Default fan_out_workers=1 to keep the recursive CTE's tmp spill
        # under control at ~278K edges. The Mac Mini runs tight on free disk.
        with ThreadPoolExecutor(max_workers=max(1, min(fan_out_workers, len(frames)))) as pool:
            for fr in frames:
                seeds = list(fr["default_seeds"])
                cond = (condition or "").strip()
                targets = [t.format(condition=cond) for t in fr["target_templates"]
                           if "{condition}" not in t or cond]
                frame_run_id = create_frame_run(brief_id, fr["id"], seeds, targets)
                fut = pool.submit(run_frame_discovery, fr, condition, None,
                                  max_hops, keep_top, path_limit)
                futures[fut] = (fr, frame_run_id)

            for fut in as_completed(futures):
                fr, frame_run_id = futures[fut]
                try:
                    result = fut.result()
                    discovery_run_id = result.get("discovery_run_id")
                    paths_n = len(fetch_paths_for_run(discovery_run_id)) if discovery_run_id else 0
                    status = "empty" if paths_n == 0 else "complete"
                    update_frame_run(frame_run_id,
                                     discovery_run_id=discovery_run_id,
                                     status=status,
                                     paths_found=paths_n)
                    frame_runs.append({"frame_id": fr["id"], "frame": fr,
                                       "discovery_run_id": discovery_run_id,
                                       "paths": paths_n})
                    log.info("  frame %s: %d paths (%.1fs)", fr["id"], paths_n,
                             time.time() - t0)
                except Exception as e:
                    log.error("Frame %s FAILED: %s", fr["id"], e)
                    try:
                        update_frame_run(frame_run_id, status="failed", error=str(e)[:500])
                    except Exception:
                        pass
                    frame_runs.append({"frame_id": fr["id"], "frame": fr,
                                       "discovery_run_id": None, "paths": 0})

        update_brief(brief_id, status="synthesizing",
                     progress_message="Integrating frame outputs…")

        log.info("Structural synthesis…")
        structural = structural_synthesize(brief_id, frame_runs)
        log.info("  convergent=%d bridges=%d gaps=%d patient_variable=%d",
                 len(structural["convergent_nodes"]),
                 len(structural["bridge_nodes"]),
                 len(structural["gaps"]),
                 len(structural["patient_variable_factors"]))

        log.info("Narrative synthesis (Claude)…")
        brief_md = narrative_synthesize(question, condition, patient_context,
                                        frames, structural, brief_id)

        update_brief(brief_id, status="complete",
                     progress_message="Brief ready",
                     structural_synthesis=structural,
                     brief_md=brief_md)
        # completed_at handled by DEFAULT NOW() isn't there — set explicitly
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE rf_etiology_briefs SET completed_at = NOW() WHERE id = %s",
                        (brief_id,))
            conn.commit()

        log.info("Brief %s COMPLETE (%.1fs)", brief_id[:8], time.time() - t0)
        return brief_id

    except Exception as e:
        log.exception("Brief failed")
        try:
            update_brief(brief_id, status="failed", error=str(e)[:500])
        except Exception:
            pass
        raise


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run a why-me brief")
    r.add_argument("--question", required=True)
    r.add_argument("--condition", default=None)
    r.add_argument("--frames", required=True,
                   help="Comma-separated frame IDs")
    r.add_argument("--patient-context", default=None,
                   help="JSON dict of patient context")
    r.add_argument("--max-hops", type=int, default=3)
    r.add_argument("--keep-top", type=int, default=20)
    r.add_argument("--path-limit", type=int, default=200,
                   help="Max candidate paths per frame (default 200). "
                        "Increase carefully — recursive CTE spills to tmp at high values.")
    r.add_argument("--fan-out-workers", type=int, default=1,
                   help="Frames to run in parallel. Default 1 (serial) to keep "
                        "pg tmp spill bounded. Safe to raise to 2–3 if disk is roomy.")

    s = sub.add_parser("show", help="Print an existing brief")
    s.add_argument("--id", required=True)

    l = sub.add_parser("list-frames", help="List available frames")

    args = ap.parse_args()

    if args.cmd == "list-frames":
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, label, description FROM rf_etiology_frames WHERE active ORDER BY id")
            for r in cur.fetchall():
                print(f"  {r['id']:30s} {r['label']}")
                print(f"    {r['description']}")
        return

    if args.cmd == "show":
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT brief_md FROM rf_etiology_briefs WHERE id = %s",
                        (args.id,))
            row = cur.fetchone()
        if not row:
            print(f"No brief with id {args.id}")
            sys.exit(1)
        print(row["brief_md"] or "(no brief content yet)")
        return

    if args.cmd == "run":
        frame_ids = [s.strip() for s in args.frames.split(",") if s.strip()]
        patient_context = json.loads(args.patient_context) if args.patient_context else None
        brief_id = run_brief(args.question, args.condition, patient_context,
                             frame_ids, max_hops=args.max_hops,
                             keep_top=args.keep_top,
                             path_limit=args.path_limit,
                             fan_out_workers=args.fan_out_workers)
        print(f"\nBrief id: {brief_id}")
        print(f"Show with: python scripts/etiology_brief.py show --id {brief_id}\n")


if __name__ == "__main__":
    main()
