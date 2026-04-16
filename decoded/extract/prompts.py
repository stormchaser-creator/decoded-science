"""Extraction prompt templates for the Decoded pipeline.

Uses structured XML output for reliable parsing without requiring
JSON mode (which can fail on long responses).

2026-04-15 update (Pearl audit): Added typed claim triples (subject/predicate/object),
per-claim operation tags, mechanism pathway/context, and paper-level operation tagging.
Subject/predicate/object were 100% NULL before — the prompt now enforces them.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are a precision biomedical literature analyst. Your job is to extract structured information from scientific papers with high accuracy. Be concise, factual, and direct. Only include information explicitly stated in the paper — do not infer or speculate.

THE 8 BIOLOGICAL OPERATIONS (use this taxonomy for all operation fields):
- Reception: sensory input, signal detection, receptor binding, ligand-receptor interactions, ion channels
- Transduction: signal conversion, second messengers, kinase cascades, GPCR signaling, phosphorylation cascades
- Conduction: transmission, propagation, neural conduction, action potentials, gap junctions, axonal transport
- Regulation: homeostasis, feedback loops, circadian rhythms, set points, allostasis, transcription factor control
- Synthesis: protein synthesis, anabolism, biosynthesis, growth, constructive metabolism, mRNA translation
- Defense: immune response, inflammation, apoptosis, DNA repair, antioxidant response, pathogen clearance
- Restoration: recovery, sleep, autophagy, cellular repair, regeneration, tissue healing, mitophagy
- Elimination: detoxification, apoptosis execution, waste removal, proteolysis, autophagy flux, excretion

CLAIM EXTRACTION RULES:
- You MUST fill subject, predicate, and object as separate XML attributes for each claim.
- subject: ONE entity making or experiencing the claim (not a sentence — one noun)
- predicate: ONE verb from this list: activates, inhibits, upregulates, downregulates, is_biomarker_for, predicts, correlates_with, requires, blocks, induces, rescues, is_upstream_of, is_downstream_of, compensates_for
- object: ONE entity being affected (not a list — one noun)
- If you cannot identify a clear subject+predicate+object, do not extract this as a claim.
- operations: comma-separated list of operations this claim touches (use the 8 Operations above). Most claims touch 1; cross-operation claims (touching 2+) are especially valuable.

MECHANISM EXTRACTION RULES:
- One row per step — do not combine multiple effects into one mechanism row.
- upstream: ONE entity (not a list)
- interaction: ONE verb (not "activates|inhibits" — pick the dominant one)
- downstream: ONE entity (not a comma-separated list)
- pathway: the named biological pathway if applicable (e.g., "mTORC1 pathway", "NF-κB cascade")
- context: tissue or disease context if specified (e.g., "hepatocyte", "type 2 diabetes")

Output ONLY the XML block. No prose before or after."""


def build_extraction_prompt(
    title: str,
    abstract: str | None,
    full_text: str | None = None,
    sections: dict | None = None,
) -> str:
    """Build the extraction prompt for a single paper."""

    # Decide content to include
    content_parts = [f"TITLE: {title}"]

    if abstract:
        content_parts.append(f"\nABSTRACT:\n{abstract}")

    # Include sections if available (more structured than full text)
    # Results section gets the most space — that's where the science lives
    _section_limits = {
        "introduction": 3000,
        "methods": 5000,
        "results": 8000,
        "discussion": 4000,
        "conclusion": 2000,
    }
    if sections:
        for key in ["introduction", "methods", "results", "discussion", "conclusion"]:
            if key in sections:
                text = sections[key]
                limit = _section_limits.get(key, 3000)
                if len(text) > limit:
                    text = text[:limit] + "\n... [TRUNCATED — original section was " + str(len(text)) + " chars]"
                content_parts.append(f"\n{key.upper()}:\n{text}")
    elif full_text:
        # Fall back to first 12000 chars of full text
        ft = full_text[:12000]
        if len(full_text) > 12000:
            ft += "\n... [TRUNCATED — original text was " + str(len(full_text)) + " chars]"
        content_parts.append(f"\nFULL TEXT (excerpt):\n{ft}")

    paper_content = "\n".join(content_parts)

    return f"""Extract structured information from this scientific paper.

---PAPER---
{paper_content}
---END PAPER---

Respond with ONLY this XML block (fill in all fields; use "unknown" if not determinable):

<extraction>
  <study_design><!-- one of: rct, cohort, case_control, cross_sectional, meta_analysis, systematic_review, case_report, case_series, in_vitro, animal, computational, review, editorial, unknown --></study_design>
  <sample_size><!-- integer or null --></sample_size>
  <population><!-- brief description of study subjects/model, or null --></population>
  <intervention><!-- main intervention/treatment/exposure, or null --></intervention>
  <comparator><!-- control/comparison group, or null --></comparator>
  <primary_outcome><!-- primary endpoint or measured outcome, or null --></primary_outcome>
  <secondary_outcomes><!-- comma-separated list, or empty --></secondary_outcomes>
  <key_findings>
    <finding><!-- 1st key finding (1-2 sentences) --></finding>
    <finding><!-- 2nd key finding (1-2 sentences) --></finding>
    <finding><!-- 3rd key finding if applicable --></finding>
  </key_findings>
  <entities>
    <!-- Up to 15 key biological entities (genes, proteins, diseases, drugs, pathways, cell types) -->
    <!-- confidence: 0.9+ = explicitly named, 0.7-0.89 = clearly implied, 0.5-0.69 = inferred, <0.5 = uncertain -->
    <entity type="gene|protein|disease|drug|pathway|cell_type|organism|biomarker" confidence="0.0-1.0"><!-- name --></entity>
  </entities>
  <claims>
    <!-- Up to 10 key scientific claims made in the paper. REQUIRED: fill subject, predicate, object attributes.
         subject="ONE entity" predicate="ONE verb from controlled list" object="ONE entity"
         operations="comma-separated list of 1-3 operations from the 8 Operations taxonomy"
         Cross-operation claims (operations spanning 2+ entries) are especially valuable — tag them accurately. -->
    <claim type="causal|associative|null|mechanistic|descriptive" strength="strong|moderate|weak" confidence="0.0-1.0"
           subject="entity-name" predicate="activates|inhibits|upregulates|downregulates|is_biomarker_for|predicts|correlates_with|requires|blocks|induces|rescues|is_upstream_of|is_downstream_of|compensates_for" object="entity-name"
           operations="Operation1,Operation2">
      <text><!-- claim text (one sentence, complete and human-readable) --></text>
    </claim>
  </claims>
  <mechanisms>
    <!-- Up to 5 biological mechanisms. ONE upstream, ONE interaction, ONE downstream per mechanism. -->
    <!-- confidence: 0.9+ = fully described, 0.7-0.89 = partially described, <0.7 = inferred -->
    <mechanism confidence="0.0-1.0">
      <description><!-- brief mechanism description --></description>
      <upstream><!-- ONE upstream entity/trigger --></upstream>
      <downstream><!-- ONE downstream entity/effect --></downstream>
      <interaction><!-- activates|inhibits|phosphorylates|ubiquitinates|transcribes|translates|cleaves|recruits|releases|sequesters|stabilizes|degrades|regulates|binds|other --></interaction>
      <pathway><!-- named pathway if applicable, e.g. "mTORC1 pathway", or null --></pathway>
      <context><!-- tissue/disease context if specified, e.g. "hepatocyte", or null --></context>
    </mechanism>
  </mechanisms>
  <methods>
    <!-- Up to 8 key methods/techniques used -->
    <method category="sequencing|imaging|assay|computational|clinical|behavioral|other"><!-- method name --></method>
  </methods>
  <limitations>
    <!-- Up to 5 limitations mentioned or implied -->
    <limitation><!-- limitation text --></limitation>
  </limitations>
  <funding><!-- funding source(s), or null --></funding>
  <conflicts><!-- conflicts of interest statement, or null --></conflicts>
  <operation>
    <!-- Primary biological operation this paper investigates (from the 8 Operations taxonomy) -->
    <primary><!-- Reception|Transduction|Conduction|Regulation|Synthesis|Defense|Restoration|Elimination --></primary>
    <secondary><!-- comma-separated secondary operations if paper spans multiple, or empty --></secondary>
    <confidence><!-- 0.0-1.0 confidence in this assignment --></confidence>
    <reasoning><!-- one sentence explaining why this operation was assigned --></reasoning>
  </operation>
</extraction>"""
