# Decoded — Cross-Project Connections

## Reach Agent Integration (LIVE, 2026-04-03)
- Reach agent (AutoAIBiz/agents/reach/) generates outreach emails from Decoded's connection discovery
- When Decoded finds high-confidence connections (>=0.70), it inserts into `reach_paper_outreach` with status=`pending_draft`
- Decoded's `decoded.outreach.processor` calls `PaperOutreachGenerator` from Reach to generate emails
- PM2 process: `decoded-outreach` runs hourly via `cron_restart: '0 * * * *'`
- DB tables (all in encoded_human): reach_paper_outreach (2,564 pending, 51 drafted), reach_paper_outreach_cooldowns, reach_paper_outreach_unsubscribes
- Eric reviews drafted emails before sending
- Voice template: `agents/reach/src/prompts/paper_outreach_email.txt`

## Pearl-Decoded Bridge (NOT YET BUILT)
- Planned: batch cron, claims-first approach, Pearl overrides classification
- Architecture: Decoded extracts claims from papers -> Pearl classifies by operation/density
- Key detail: Decoded uses `raw_papers` table (not `papers`) as source
- 27 Altini papers identified as first bridge candidates

## shared-libs/pubmed-tools (WIRED)
- Decoded's discover.py imports from shared-libs/pubmed-tools
- Replaced ~140 lines of XML parsing
- Installed via: "pubmed-tools @ file:///Users/whit/Projects/shared-libs/pubmed-tools" in pyproject.toml
