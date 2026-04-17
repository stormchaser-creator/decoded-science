#!/usr/bin/env bash
# Continuous aggregation loop — runs the connectome refresh every AGG_INTERVAL
# seconds. Keeps paper_claim_triples / canonical_entities stats /
# entity_edges in sync with the continuously-updating claims + mechanisms
# streams from decoded-extract.
#
# Designed to run under PM2:
#   pm2 start scripts/aggregate_loop.sh --name decoded-aggregate --cwd /Users/whit/Projects/Decoded
#   pm2 save
#
# Tune via env: AGG_INTERVAL (seconds, default 600 = 10 min)

set -u
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
AGG_INTERVAL="${AGG_INTERVAL:-600}"
LOG_PREFIX="[aggregate]"

echo "$LOG_PREFIX starting. interval=${AGG_INTERVAL}s cwd=$(pwd)"

while true; do
    START=$(date +%s)
    echo ""
    echo "$LOG_PREFIX ==== $(date -Iseconds) ===="

    echo "$LOG_PREFIX harvest_claims_to_triples.py"
    $PY scripts/harvest_claims_to_triples.py 2>&1 | tail -6

    echo "$LOG_PREFIX harvest_mechanisms_to_triples.py"
    $PY scripts/harvest_mechanisms_to_triples.py 2>&1 | tail -6

    echo "$LOG_PREFIX normalize_entities.py"
    $PY scripts/normalize_entities.py 2>&1 | tail -6

    echo "$LOG_PREFIX expand_entity_mentions.py --only-new"
    $PY scripts/expand_entity_mentions.py --only-new 2>&1 | tail -6

    echo "$LOG_PREFIX build_entity_edges.py"
    $PY scripts/build_entity_edges.py --min-support 1 2>&1 | tail -8

    END=$(date +%s)
    DUR=$((END - START))
    SLEEP=$((AGG_INTERVAL - DUR))
    if [ "$SLEEP" -lt 30 ]; then SLEEP=30; fi
    echo "$LOG_PREFIX cycle done in ${DUR}s, sleeping ${SLEEP}s"
    sleep "$SLEEP"
done
