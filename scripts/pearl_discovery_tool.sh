#!/usr/bin/env bash
# Sprint B6 — Pearl-callable Discovery tool.
#
# Thin wrapper around scripts/discovery.py so Pearl's run_command tool can
# invoke Discovery without knowing Python/venv details. Also registers a
# standard output format that Pearl can parse into her hypothesis workflow.
#
# Usage:
#   ./scripts/pearl_discovery_tool.sh run <seed> [--target <target>] [--max-hops N]
#   ./scripts/pearl_discovery_tool.sh brief <run_id_prefix>
#   ./scripts/pearl_discovery_tool.sh list
#   ./scripts/pearl_discovery_tool.sh summary <run_id_prefix>
#
# Examples:
#   ./scripts/pearl_discovery_tool.sh run Cortisol --target Longevity
#   ./scripts/pearl_discovery_tool.sh run AMPK --max-hops 3
#   ./scripts/pearl_discovery_tool.sh brief 17454278

set -euo pipefail

DECODED_ROOT="/Users/whit/Projects/Decoded"
PY="$DECODED_ROOT/.venv/bin/python"
DISC="$DECODED_ROOT/scripts/discovery.py"

cmd="${1:-}"
shift || true

case "$cmd" in
    run)
        if [ $# -lt 1 ]; then
            echo "Usage: $0 run <seed> [--target X] [--max-hops N] [--min-cross-ops N]" >&2
            exit 1
        fi
        seed="$1"
        shift
        # Pass remaining args through to discovery.py
        exec "$PY" "$DISC" run --seed "$seed" "$@"
        ;;
    brief)
        if [ $# -lt 1 ]; then
            echo "Usage: $0 brief <run_id_prefix> [--path-rank N] [--output FILE]" >&2
            exit 1
        fi
        exec "$PY" "$DISC" brief --run-id "$@"
        ;;
    list)
        exec "$PY" "$DISC" list
        ;;
    summary)
        if [ $# -lt 1 ]; then
            echo "Usage: $0 summary <run_id_prefix>" >&2
            exit 1
        fi
        exec "$PY" "$DISC" show --run-id "$1"
        ;;
    init)
        exec "$PY" "$DISC" init-schema
        ;;
    *)
        cat <<EOF
Decoded Discovery — Pearl-callable wrapper

Subcommands:
  run <seed> [--target X] [--max-hops N] [--min-cross-ops N] [--keep-top N]
      Run a new discovery from a seed entity toward an optional target.
      Returns run_id and top paths.

  brief <run_id_prefix> [--path-rank N] [--output FILE]
      Generate a hypothesis brief from a completed run. Path rank 1 (default)
      uses the highest-scoring path.

  summary <run_id_prefix>
      Show a completed run's metadata and top-10 paths.

  list
      List the 20 most recent discovery runs.

  init
      Initialize discovery schema (pearl_discovery_runs, pearl_path_scores,
      pearl_hypothesis_briefs).

Examples:
  $0 run Cortisol --target Longevity --max-hops 5 --min-cross-ops 2
  $0 run "Aging" --max-hops 3 --keep-top 10
  $0 brief 17454278
EOF
        ;;
esac
