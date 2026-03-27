"""Extraction prompt templates for the Decoded pipeline.

Uses structured XML output for reliable parsing without requiring
JSON mode (which can fail on long responses).
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are a precision biomedical literature analyst. Your job is to extract structured information from scientific papers with high accuracy. Be concise, factual, and direct. Only include information explicitly stated in the paper — do not infer or speculate.

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
    if sections:
        for key in ["introduction", "methods", "results", "discussion", "conclusion"]:
            if key in sections:
                text = sections[key]
                # Truncate very long sections
                if len(text) > 3000:
                    text = text[:3000] + "... [truncated]"
                content_parts.append(f"\n{key.upper()}:\n{text}")
    elif full_text:
        # Fall back to first 6000 chars of full text
        ft = full_text[:6000]
        if len(full_text) > 6000:
            ft += "... [truncated]"
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
    <entity type="gene|protein|disease|drug|pathway|cell_type|organism|biomarker"><!-- name --></entity>
  </entities>
  <claims>
    <!-- Up to 10 key scientific claims made in the paper -->
    <claim type="causal|associative|null|mechanistic|descriptive" strength="strong|moderate|weak">
      <!-- claim text (one sentence) -->
    </claim>
  </claims>
  <mechanisms>
    <!-- Up to 5 biological mechanisms described -->
    <mechanism>
      <description><!-- brief mechanism description --></description>
      <upstream><!-- upstream entity/trigger, or null --></upstream>
      <downstream><!-- downstream entity/effect, or null --></downstream>
      <interaction><!-- activates|inhibits|binds|regulates|phosphorylates|cleaves|other --></interaction>
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
</extraction>"""
