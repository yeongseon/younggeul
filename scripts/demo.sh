#!/usr/bin/env bash
# younggeul v0.1 demo — end-to-end pipeline showcase
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="${REPO_ROOT}/core/src:${REPO_ROOT}/apps/kr-seoul-apartment/src:${PYTHONPATH:-}"

echo "=== Younggeul v0.1 Demo ==="

DEMO_DIR="${DEMO_DIR:-./demo_output}"
mkdir -p "$DEMO_DIR"

echo "[1/6] Ingesting fixture data..."
python3 -m younggeul_app_kr_seoul_apartment.cli ingest --output-dir "$DEMO_DIR/pipeline"

echo "[2/6] Publishing snapshot..."
python3 -m younggeul_app_kr_seoul_apartment.cli snapshot publish --data-dir "$DEMO_DIR/pipeline" --snapshot-dir "$DEMO_DIR/snapshots"

echo "[3/6] Running baseline forecast..."
python3 -m younggeul_app_kr_seoul_apartment.cli baseline --snapshot-dir "$DEMO_DIR/snapshots" --output-dir "$DEMO_DIR/baseline"

echo "[4/6] Running simulation (2 rounds)..."
python3 -m younggeul_app_kr_seoul_apartment.cli simulate --query "서울 강남구 아파트 시장 전망" --max-rounds 2 --output-dir "$DEMO_DIR/simulation"

echo "[5/6] Displaying simulation report..."
REPORT_FILE=$(ls -t "$DEMO_DIR/simulation"/simulation_report_*.md 2>/dev/null | head -1)
if [ -n "$REPORT_FILE" ]; then
    python3 -m younggeul_app_kr_seoul_apartment.cli report --report-file "$REPORT_FILE"
fi

echo "[6/6] Running evaluation suite..."
python3 -m younggeul_app_kr_seoul_apartment.cli eval --output-dir "$DEMO_DIR/eval" || echo "  (eval completed with warnings)"

echo ""
echo "=== Demo Complete ==="
echo "Output directory: $DEMO_DIR"
echo ""
echo "Artifacts:"
find "$DEMO_DIR" -type f | sort | sed 's/^/  /'
