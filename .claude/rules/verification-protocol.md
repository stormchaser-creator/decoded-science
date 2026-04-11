# Verification Protocol — MANDATORY BEFORE DECLARING DONE

> **Why this exists:** Eric is the one who discovers every bug. Every hour he spends finding something an agent should have caught is an hour wasted. The pattern is clear: agents write code, say "done," but never actually USE the thing they built. This protocol ends that pattern.
>
> "The code looks right" is not done. **Done means it works.** You've touched it. You've seen it run. You've seen the data flow through it.

---

## The Rule

**Before any task is declared complete, the agent MUST verify it end-to-end as a user would.** Not by reading the code. Not by reasoning about the code. By actually exercising it.

If you cannot verify something, say so explicitly. "I wrote this but could not verify X because Y" is acceptable. "Done" when you didn't verify is not.

---

## Step 1: Build / Import Verification

If any code was changed:

```bash
# Syntax / import check
cd /Users/whit/Projects/Decoded
python -m py_compile [changed_file.py]
python -c "from decoded.[module] import [Class]"

# FastAPI startup check (catches route registration errors)
cd /Users/whit/Projects/Decoded && python -c "from decoded.api.main import app; print('API OK')"
```

**If imports fail, fix them. Do not declare done with broken imports.**

---

## Step 2: Smoke Test As a Real User

Choose the relevant checks based on what was built:

### Pipeline Stage

```bash
# Run the specific stage with a real paper
cd /Users/whit/Projects/Decoded
python -m decoded.[stage] --limit 1 --verbose

# Check that output was written
psql -h Whits-Mac-mini.local -d encoded_human -c \
  "SELECT COUNT(*) FROM [output_table] WHERE created_at > NOW() - INTERVAL '5 minutes';"
```

- Did it process at least 1 item?
- Did it write output to the expected table?
- Are there errors in the log?

### API Route

```bash
# Start the API if not running
cd /Users/whit/Projects/Decoded && uvicorn decoded.api.main:app --port 8000 &
sleep 3

# Hit the endpoint
curl -s http://localhost:8000/[endpoint] | python3 -m json.tool
```

- Returns 200?
- Response has real data, not empty arrays or null?

### PM2 Process

```bash
pm2 start [process-name]
sleep 10
pm2 list | grep [process-name]  # Should show "online"
pm2 logs [process-name] --lines 20
```

- Online after 10 seconds (not crash-looping)?
- Logs show activity, not crash stack traces?

### Database Migration / New Table

```bash
# Decoded uses encoded_human DB on Mac Mini — NOT localhost
psql -h Whits-Mac-mini.local -d encoded_human -c "\d [table_name]"
psql -h Whits-Mac-mini.local -d encoded_human -c "SELECT COUNT(*) FROM [table_name];"
```

- Table exists on the Mac Mini?
- Has expected columns?

### Intelligence Brief / Extraction

```bash
# Run on 1 paper manually
python -m decoded.critique.brief_generator --paper-id [id] --dry-run
psql -h Whits-Mac-mini.local -d encoded_human -c \
  "SELECT id, title FROM intelligence_briefs ORDER BY created_at DESC LIMIT 1;"
```

- Brief was created?
- Content is populated (not null/empty)?

### Author Outreach Pipeline

```bash
psql -h Whits-Mac-mini.local -d encoded_human -c \
  "SELECT status, COUNT(*) FROM reach_paper_outreach GROUP BY status;"
pm2 logs decoded-outreach --lines 20
```

- Process is running?
- Status counts are moving (pending→drafted)?

### Neo4j Graph

```bash
# Quick node count
cypher-shell -u neo4j "MATCH (n) RETURN count(n) AS total"
# Or check a specific relationship was created
cypher-shell -u neo4j "MATCH ()-[r:CONNECTS_TO]->() RETURN count(r) AS total"
```

- Node/relationship counts match expected output?

---

## Step 3: Verify the Data Path End-to-End

The Decoded pipeline is 8 stages. Each stage consumes the previous stage's output. Verify the full path:

```
raw_papers → paper_extractions → paper_connections → intelligence_briefs
```

```bash
psql -h Whits-Mac-mini.local -d encoded_human -c "
  SELECT
    (SELECT COUNT(*) FROM raw_papers WHERE status = 'processed') as ingested,
    (SELECT COUNT(*) FROM paper_extractions) as extracted,
    (SELECT COUNT(*) FROM paper_connections) as connected,
    (SELECT COUNT(*) FROM intelligence_briefs) as briefs;
"
```

If counts are zero or stalled at a stage, that stage is broken.

---

## Step 4: Try to Break It (60 Seconds)

Spend 60 seconds actively trying to make it fail:

- **No papers:** What happens if `raw_papers` is empty or all papers are already processed?
- **Wrong DB host:** This project uses `Whits-Mac-mini.local`, not `localhost`. Did you hard-code localhost anywhere?
- **Missing full text:** What happens when `full_text` is NULL? Does extraction fail gracefully?
- **API key missing:** What happens if `ANTHROPIC_API_KEY` isn't set? Clear error or silent failure?
- **Large paper:** What happens with a 100-page full text that exceeds Claude's context window?
- **Neo4j offline:** What happens if Neo4j isn't running when the graph stage fires?
- **Outreach cooldown:** Does the cooldown table prevent re-emailing the same author?

You don't need to fix every edge case. But if you find a crash, fix it.

---

## Step 5: Report Honestly

When you say a task is done, include:

```
**Verified:**
- [ ] Imports/build pass
- [ ] [Specific stage/route] tested: [command used] → [result seen]
- [ ] Data path: [input count] → [stage output count] → [downstream count]
- [ ] Attempted to break: [what you tried, what happened]
```

If you couldn't verify something, say exactly why:

> "Could not verify the Neo4j graph sync because Neo4j wasn't running in this environment. Eric should run `pm2 logs decoded-graph --lines 30` to confirm after next pipeline run."

**Do not say "done" when you mean "written." They are not the same thing.**

---

## Common Failure Patterns to Watch For

These are the bugs Eric keeps finding — the ones agents miss:

1. **Wrong DB host** — code connects to `localhost:5432` but production is `Whits-Mac-mini.local:5432`
2. **Stage produces 0 rows** — SQL WHERE clause too restrictive, or upstream stage hasn't run yet
3. **Silent failure in async** — extraction fails on one paper, bare `except: pass`, loop continues, nothing logged
4. **PM2 crash loop** — process starts then dies in <5s; looks "done" if you don't wait
5. **Full text NULL** — code assumes `full_text` is always populated but 67% of papers are abstract-only
6. **API returns 200 but empty** — route handler has a bug in the query, returns `{"data": []}` silently
7. **Neo4j out of sync** — SQL table updated but graph sync not triggered; counts diverge
8. **Outreach duplicates** — cooldown table not checked, same author contacted multiple times
9. **Model context exceeded** — long paper causes Claude API to return an error that isn't handled
