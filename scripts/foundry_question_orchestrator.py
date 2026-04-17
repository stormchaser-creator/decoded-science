"""Sprint H — The question-to-paper orchestrator.

User asks a question (e.g. "Why do cavernous malformations form?").
This script walks it through the full pipeline:

    decompose → check density → acquire if thin → aggregate →
    discover → promote to project → (Foundry autopilot takes over)

Status updates are written to rf_questions so the UI can poll.

Designed to be spawned by Foundry's /api/foundry/ask endpoint:
    python scripts/foundry_question_orchestrator.py --question-id <uuid>

The question row must already exist in rf_questions with status='pending'.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from typing import Any

import psycopg2
import psycopg2.extras

# Claude
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")
DECODED_ROOT = os.environ.get("DECODED_ROOT", "/Users/whit/Projects/Decoded")
PY = f"{DECODED_ROOT}/.venv/bin/python"


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ============================================================================
# STATUS UPDATES
# ============================================================================
def update_status(conn, question_id: str, status: str, msg: str,
                  extra: dict[str, Any] | None = None) -> None:
    """Update rf_questions status + progress_message. Optional extra fields."""
    extra = extra or {}
    fields = ["status = %s", "progress_message = %s", "updated_at = NOW()"]
    values: list[Any] = [status, msg]
    for k, v in extra.items():
        fields.append(f"{k} = %s")
        values.append(v)
    values.append(question_id)
    log.info("[%s] %s: %s", question_id[:8], status, msg)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE rf_questions SET {', '.join(fields)} WHERE id = %s",
            values,
        )
    conn.commit()


def mark_complete(conn, question_id: str, msg: str,
                  extra: dict[str, Any] | None = None) -> None:
    extra = extra or {}
    extra["completed_at"] = "NOW()"
    fields = ["status = 'complete'", "progress_message = %s",
              "updated_at = NOW()", "completed_at = NOW()"]
    values: list[Any] = [msg]
    for k, v in extra.items():
        if v == "NOW()":
            continue
        fields.append(f"{k} = %s")
        values.append(v)
    values.append(question_id)
    log.info("[%s] COMPLETE: %s", question_id[:8], msg)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE rf_questions SET {', '.join(fields)} WHERE id = %s",
            values,
        )
    conn.commit()


def mark_failed(conn, question_id: str, err: str) -> None:
    log.error("[%s] FAILED: %s", question_id[:8], err)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE rf_questions
               SET status = 'failed', error = %s, updated_at = NOW()
               WHERE id = %s""",
            (err, question_id),
        )
    conn.commit()


# ============================================================================
# STEP 1: DECOMPOSE QUESTION
# ============================================================================
DECOMPOSE_SYSTEM = """You are a research question decomposer for a biomedical connectome.
Your job: take a scientific question and extract:
  - seed_entities: 2-5 specific named entities that should be the ENTRY POINTS
    into the connectome. Prefer proper nouns: gene names (CCM1, KRIT1),
    compounds (cortisol), diseases (cerebral cavernous malformation),
    well-known processes (autophagy). NOT phrases like "why" or "how".
  - target_entities: 1-3 entities that are the OUTCOME of interest. If the
    question is "why does X form?" target should be "X formation" or a
    hemorrhage/symptom downstream. If the question is open-ended, leave empty.
  - acquisition_queries: 4-8 targeted PubMed queries that would broaden the
    connectome's knowledge around this question. Each query is a Boolean
    PubMed expression. Include the seed, mechanism keywords (oxidative,
    inflammation, endothelial, etc.), and outcome keywords.
  - notes: one paragraph stating the mechanistic territory this question
    covers and why these seeds/targets are the right entry points.

Return ONLY valid JSON with keys: seed_entities, target_entities,
acquisition_queries, notes."""


def decompose_question(question_text: str) -> dict[str, Any]:
    """Use Claude Haiku to decompose. Falls back to a rule-based decomposer
    if Anthropic SDK is unavailable or the API fails."""
    if HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            client = Anthropic()
            msg = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system=DECOMPOSE_SYSTEM,
                messages=[{"role": "user", "content": question_text}],
            )
            text = msg.content[0].text.strip()
            # Strip any ``` wrapping
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip().rstrip("`").strip()
            return json.loads(text)
        except Exception as e:
            log.warning("Claude decomposition failed, falling back: %s", e)

    # Fallback: extract obvious named entities + generic query expansion
    words = question_text.split()
    seeds = [w.strip("?.,") for w in words if (w[0].isupper() and len(w) > 2) or w.isupper()]
    return {
        "seed_entities": seeds[:5] or [question_text.strip("?.,")[:80]],
        "target_entities": [],
        "acquisition_queries": [question_text],
        "notes": "Rule-based fallback decomposition (no Claude available)",
    }


# ============================================================================
# STEP 2: DENSITY CHECK
# ============================================================================
DENSITY_THRESHOLD_EDGES = 10      # seed with <10 edges is "thin"
DENSITY_THRESHOLD_PAPERS = 20     # seed topic with <20 papers is "thin"


def check_density(conn, seeds: list[str]) -> dict[str, Any]:
    """For each seed, return edge count, paper count, and whether
    it's islanded/thin."""
    result = {"seeds": {}, "islanded": [], "any_thin": False}
    with conn.cursor() as cur:
        for seed in seeds:
            # Edge count for entities matching this seed (by canonical name or alias)
            cur.execute(
                """SELECT COUNT(DISTINCT e.id) AS n
                   FROM entity_edges e
                   WHERE lower(e.source_entity_name) = lower(%s)
                      OR lower(e.target_entity_name) = lower(%s)""",
                (seed, seed),
            )
            edges = cur.fetchone()["n"]

            # Paper count for this seed (rough — title/abstract match)
            cur.execute(
                """SELECT COUNT(*) AS n FROM raw_papers
                   WHERE lower(title) LIKE %s OR lower(abstract) LIKE %s""",
                (f"%{seed.lower()}%", f"%{seed.lower()}%"),
            )
            papers = cur.fetchone()["n"]

            thin = edges < DENSITY_THRESHOLD_EDGES or papers < DENSITY_THRESHOLD_PAPERS
            result["seeds"][seed] = {
                "edges": edges, "papers": papers, "thin": thin,
            }
            if thin:
                result["islanded"].append(seed)
                result["any_thin"] = True
    return result


# ============================================================================
# STEP 3: ACQUIRE LITERATURE
# ============================================================================
def run_acquisition(question_id: str, queries: list[str],
                    per_query_limit: int = 500) -> list[str]:
    """Spawn one ingest worker per query. Waits synchronously (best-effort)."""
    run_ids: list[str] = []
    processes: list[tuple[subprocess.Popen, str]] = []

    for q in queries[:6]:  # cap at 6 parallel queries
        cmd = [
            PY, "-m", "decoded.ingest.worker",
            "--ring", "ring_1",
            "--domain", f"foundry-ask-{question_id[:8]}",
            "--query", q,
            "--limit", str(per_query_limit),
        ]
        log_path = os.path.join(DECODED_ROOT, "logs",
                                f"foundry-ask-{question_id[:8]}-{len(processes)}.log")
        with open(log_path, "w") as f:
            p = subprocess.Popen(
                cmd, cwd=DECODED_ROOT, stdout=f, stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        processes.append((p, q))

    # Wait for all
    new_papers = 0
    for p, q in processes:
        try:
            p.wait(timeout=1200)  # 20 min cap
        except subprocess.TimeoutExpired:
            p.kill()
            log.warning("Acquisition timeout for query: %s", q[:80])
    return run_ids, new_papers


# ============================================================================
# STEP 4: AGGREGATE (wait for decoded-aggregate to cycle)
# ============================================================================
def wait_for_aggregation(conn, question_id: str, papers_before: int,
                         max_wait_sec: int = 900) -> int:
    """Wait for decoded-extract + decoded-aggregate to cycle through the
    newly ingested papers. Polls paper_claim_triples count every 30s.
    Returns the number of new triples added.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM paper_claim_triples")
        triples_start = cur.fetchone()["n"]

    log.info("Waiting for extraction + aggregation (triples=%s now)…", triples_start)
    t0 = time.time()
    last_triples = triples_start
    stable_count = 0
    while time.time() - t0 < max_wait_sec:
        time.sleep(45)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM paper_claim_triples")
            triples_now = cur.fetchone()["n"]
        delta = triples_now - last_triples
        log.info("  triples=%s (+%s in last 45s, +%s total)",
                 triples_now, delta, triples_now - triples_start)
        update_status(conn, question_id, "aggregating",
                      f"Processing literature: {triples_now - triples_start} new triples")
        if delta < 20:
            stable_count += 1
            if stable_count >= 3:
                log.info("Triple growth stabilized — aggregation settled")
                break
        else:
            stable_count = 0
        last_triples = triples_now

    return last_triples - triples_start


# ============================================================================
# STEP 5: DISCOVERY RUN
# ============================================================================
def run_discovery(seeds: list[str], targets: list[str] | None,
                  topic: str, max_hops: int = 4, keep_top: int = 15) -> str:
    """Spawn scripts/discovery.py run and return the new run_id."""
    # Snapshot max created_at
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(MAX(created_at)::text, '1970-01-01') AS t
                   FROM pearl_discovery_runs"""
            )
            prev = cur.fetchone()["t"]
    finally:
        conn.close()

    cmd = [
        PY, f"{DECODED_ROOT}/scripts/discovery.py", "run",
        "--seed", seeds[0],
    ]
    for s in seeds[1:]:
        cmd.extend(["--seed", s])
    for t in (targets or []):
        cmd.extend(["--target", t])
    cmd.extend([
        "--topic", topic,
        "--max-hops", str(max_hops),
        "--keep-top", str(keep_top),
        "--min-cross-ops", "1",
    ])

    log.info("Discovery: %s", " ".join(cmd[2:]))
    subprocess.run(cmd, cwd=DECODED_ROOT, check=False,
                   env={**os.environ, "PYTHONUNBUFFERED": "1"})

    # Find the new run
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text AS id, paths_scored FROM pearl_discovery_runs
                   WHERE created_at > %s::timestamptz
                   ORDER BY created_at DESC LIMIT 1""",
                (prev,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return row["id"] if row else ""


# ============================================================================
# STEP 6: PROMOTE TOP PATH → Foundry project
# ============================================================================
def promote_top_path(run_id: str, question_text: str) -> dict[str, str] | None:
    """Generate brief, then promote to rf_project. Uses discovery.py brief
    + a direct SQL promote (same logic as /api/discovery/runs/[id]/promote)."""
    # Generate brief first
    subprocess.run(
        [PY, f"{DECODED_ROOT}/scripts/discovery.py", "brief",
         "--run-id", run_id, "--path-rank", "1"],
        cwd=DECODED_ROOT, check=False,
    )
    # Now load the brief + top path and create rf_project
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pearl_discovery_runs WHERE id = %s", (run_id,))
            run = cur.fetchone()
            if not run or not run.get("hypothesis_brief_id"):
                return None
            cur.execute(
                """SELECT * FROM pearl_path_scores WHERE run_id = %s AND rank = 1""",
                (run_id,),
            )
            path = cur.fetchone()
            cur.execute(
                """SELECT * FROM pearl_hypothesis_briefs WHERE id = %s""",
                (run["hypothesis_brief_id"],),
            )
            brief = cur.fetchone()
            if not path or not brief:
                return None

            names = path["path_entity_names"]
            title = f"{question_text.rstrip('?.')} — {names[0]} → {names[-1]}"
            thesis = brief.get("thesis_statement") or ""

            research_plan = {
                "source": {
                    "type": "foundry_question",
                    "question": question_text,
                    "discovery_run_id": run_id,
                    "path_id": str(path["id"]),
                    "brief_id": str(brief["id"]),
                },
                "convergence_chain": names,
                "predicates": path["path_predicates"],
                "operations": path["path_operations"],
                "support_counts": path["path_support_counts"],
                "scoring": {
                    "composite": float(path["composite_score"]),
                    "novelty": float(path["novelty_score"]),
                    "coherence": float(path["coherence_score"]),
                    "plausibility": float(path["plausibility_score"]),
                },
                "mechanistic_narrative": brief.get("mechanistic_narrative"),
                "gaps": brief.get("gaps"),
                "falsification_criteria": brief.get("falsification_criteria"),
            }
            cur.execute(
                """INSERT INTO rf_projects
                     (title, thesis, convergence_chain, research_plan, status)
                   VALUES (%s, %s, %s::jsonb, %s::jsonb, 'HYPOTHESIS')
                   RETURNING id""",
                (title, thesis, json.dumps(names), json.dumps(research_plan)),
            )
            project_id = cur.fetchone()["id"]

            # Import evidence (union of supporting papers across edges)
            evidence_ids: set[str] = set()
            for i in range(len(path["path_predicates"])):
                cur.execute(
                    """SELECT supporting_paper_ids FROM entity_edges
                       WHERE lower(source_entity_name) = lower(%s)
                         AND lower(target_entity_name) = lower(%s)
                         AND predicate_type = %s LIMIT 1""",
                    (names[i], names[i + 1], path["path_predicates"][i]),
                )
                r = cur.fetchone()
                if r and r.get("supporting_paper_ids"):
                    val = r["supporting_paper_ids"]
                    if isinstance(val, str) and val.startswith("{"):
                        for u in val[1:-1].split(","):
                            u = u.strip()
                            if u:
                                evidence_ids.add(u)
                    elif isinstance(val, list):
                        for u in val:
                            evidence_ids.add(str(u))

            if evidence_ids:
                cur.execute(
                    """SELECT id, source, external_id, title, pub_year, abstract,
                              doi, pmc_id, authors, mesh_terms
                       FROM raw_papers WHERE id = ANY(%s::uuid[])""",
                    (list(evidence_ids),),
                )
                papers = cur.fetchall()
                for p in papers:
                    authors = p["authors"] if isinstance(p["authors"], list) else []
                    authors_arr = [
                        a if isinstance(a, str) else (a.get("name") or str(a))
                        for a in authors
                    ]
                    mesh = p["mesh_terms"] if isinstance(p["mesh_terms"], list) else []
                    pmid = str(p["external_id"]) if p["source"] == "pubmed" else None
                    try:
                        cur.execute(
                            """INSERT INTO rf_evidence
                                 (project_id, source, external_id, title, year,
                                  abstract, doi, pmid, pmc_id, authors, mesh_terms,
                                  included, epistemic_tier, notes)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                       TRUE, 2,
                                       'From Foundry question ' || %s)
                               ON CONFLICT (project_id, source, external_id) DO NOTHING""",
                            (project_id, p["source"], p["external_id"], p["title"],
                             p["pub_year"], p["abstract"], p["doi"], pmid,
                             p["pmc_id"], authors_arr, [str(m) for m in mesh],
                             run_id[:8]),
                        )
                    except Exception as ev_err:
                        log.warning("Evidence insert skipped: %s", ev_err)
                        conn.rollback()
        conn.commit()
        return {"project_id": str(project_id), "brief_id": str(brief["id"])}
    finally:
        conn.close()


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================
def orchestrate(question_id: str) -> None:
    conn = db_connect()
    try:
        # Load question
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM rf_questions WHERE id = %s", (question_id,))
            q = cur.fetchone()
        if not q:
            log.error("No question with id %s", question_id)
            return
        qtext = q["question_text"]
        log.info("[%s] question: %s", question_id[:8], qtext)

        # ───── 1. DECOMPOSE ─────
        update_status(conn, question_id, "decomposing",
                      "Decomposing question into seed + target entities…")
        decomp = decompose_question(qtext)
        seeds = decomp.get("seed_entities", [])
        targets = decomp.get("target_entities", []) or None
        queries = decomp.get("acquisition_queries", [])
        notes = decomp.get("notes", "")
        log.info("Seeds: %s", seeds)
        log.info("Targets: %s", targets)
        update_status(conn, question_id, "decomposing",
                      f"Seeds: {', '.join(seeds)}",
                      {
                          "seed_entities": seeds,
                          "target_entities": targets or [],
                          "acquisition_queries": queries,
                          "decomposition_notes": notes,
                      })

        # ───── 2. DENSITY CHECK ─────
        update_status(conn, question_id, "checking_density",
                      "Measuring connectome coverage for these seeds…")
        density = check_density(conn, seeds)
        update_status(conn, question_id, "checking_density",
                      f"Density: {density['islanded']} are thin"
                      if density["islanded"]
                      else "Connectome has strong coverage",
                      {"density_before": json.dumps(density)})

        # ───── 3. ACQUIRE (if thin) ─────
        papers_before = 0
        if density["any_thin"] and queries:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM raw_papers")
                papers_before = cur.fetchone()["n"]
            update_status(conn, question_id, "acquiring",
                          f"Acquiring literature: {len(queries)} targeted PubMed queries…")
            try:
                run_acquisition(question_id, queries, per_query_limit=500)
            except Exception as e:
                log.warning("Acquisition partial failure: %s", e)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM raw_papers")
                papers_after = cur.fetchone()["n"]
            new_papers = papers_after - papers_before
            update_status(conn, question_id, "acquiring",
                          f"Ingested {new_papers} new papers",
                          {"acquisition_papers": new_papers})

            # ───── 4. AGGREGATE ─────
            update_status(conn, question_id, "aggregating",
                          "Processing new literature (extract + normalize + edges)…")
            triples_added = wait_for_aggregation(conn, question_id, papers_before)
            log.info("Aggregation added %d new triples", triples_added)
        else:
            update_status(conn, question_id, "skipped_acquisition",
                          "Connectome already has enough coverage; skipping acquisition")

        # ───── 5. DISCOVERY ─────
        update_status(conn, question_id, "discovering",
                      f"Traversing connectome from {seeds[0]}…")
        run_id = run_discovery(seeds, targets, topic=qtext,
                               max_hops=4, keep_top=15)
        if not run_id:
            mark_failed(conn, question_id, "Discovery produced no paths")
            return
        with conn.cursor() as cur:
            cur.execute("SELECT paths_scored FROM pearl_discovery_runs WHERE id = %s", (run_id,))
            paths_row = cur.fetchone()
        paths_n = paths_row["paths_scored"] if paths_row else 0
        update_status(conn, question_id, "discovering",
                      f"Discovery found {paths_n} ranked paths",
                      {"discovery_run_id": run_id})

        if paths_n == 0:
            mark_failed(conn, question_id,
                        "Discovery returned 0 paths — connectome still insufficient")
            return

        # ───── 6. PROMOTE ─────
        update_status(conn, question_id, "promoting",
                      "Promoting top path to Foundry project with evidence…")
        prom = promote_top_path(run_id, qtext)
        if not prom:
            mark_failed(conn, question_id,
                        "Promotion failed — could not synthesize brief or create project")
            return

        # ───── 7. COMPLETE ─────
        mark_complete(conn, question_id,
                      f"Paper draft ready. Project {prom['project_id'][:8]} created.",
                      {"project_id": prom["project_id"],
                       "brief_id": prom["brief_id"]})

    except Exception as e:
        log.exception("Orchestrator crashed")
        mark_failed(conn, question_id, f"{type(e).__name__}: {e}")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question-id", required=True)
    args = ap.parse_args()
    orchestrate(args.question_id)


if __name__ == "__main__":
    main()
