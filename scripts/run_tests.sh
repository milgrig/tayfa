#!/bin/bash
# ─────────────────────────────────────────────────────────────
# run_tests.sh — Test runner for Tayfa project
#
# Usage:
#   ./scripts/run_tests.sh              # Run all tests (unit + E2E)
#   ./scripts/run_tests.sh unit         # Run only unit/API tests
#   ./scripts/run_tests.sh e2e          # Run only E2E (Playwright) tests
#   ./scripts/run_tests.sh smoke        # Run only smoke tests (fast E2E)
#   ./scripts/run_tests.sh --install    # Install dependencies + Playwright browsers
#   ./scripts/run_tests.sh --coverage   # Run unit tests with coverage
#   ./scripts/run_tests.sh e2e --headed # Run E2E tests with visible browser
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KOK_DIR="$ROOT_DIR/kok"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Handle --install flag ────────────────────────────────────
if [[ "${1:-}" == "--install" ]]; then
    info "Installing Python dependencies..."
    pip install -r "$KOK_DIR/requirements.txt"
    info "Installing Playwright browsers..."
    python -m playwright install chromium
    info "Dependencies installed successfully."
    exit 0
fi

# ── Determine test mode ──────────────────────────────────────
MODE="${1:-all}"
EXTRA_ARGS=""

# Check for --headed flag in any position
for arg in "$@"; do
    if [[ "$arg" == "--headed" ]]; then
        EXTRA_ARGS="--headed"
    fi
done

# ── Helpers ───────────────────────────────────────────────────
check_playwright() {
    python -c "import playwright" 2>/dev/null || {
        error "Playwright not installed. Run: ./scripts/run_tests.sh --install"
        exit 1
    }
}

# ── Run tests ────────────────────────────────────────────────
echo "=== Running Tayfa Tests ==="

cd "$KOK_DIR"

case "$MODE" in
    unit)
        info "Running UNIT tests only (excluding E2E)..."
        pytest tests/ -m "not e2e" -v --tb=short
        ;;
    e2e)
        check_playwright
        info "Running E2E tests (Playwright)..."
        export TAYFA_TEST_MODE=1
        pytest tests/e2e/ -m "e2e" -v --tb=short $EXTRA_ARGS
        ;;
    smoke)
        check_playwright
        info "Running SMOKE tests (fast E2E)..."
        export TAYFA_TEST_MODE=1
        pytest tests/e2e/ -m "smoke" -v --tb=short $EXTRA_ARGS
        ;;
    --coverage)
        info "Running with coverage..."
        pytest tests/ -m "not e2e" -v --cov=. --cov-report=term-missing --cov-report=html
        echo ""
        info "Coverage HTML report: kok/htmlcov/index.html"
        ;;
    all)
        info "── Phase 1: Unit tests ──"
        pytest tests/ -m "not e2e" -v --tb=short

        echo ""
        info "── Phase 2: E2E tests ──"
        check_playwright
        export TAYFA_TEST_MODE=1
        pytest tests/e2e/ -m "e2e" -v --tb=short $EXTRA_ARGS
        ;;
    *)
        error "Unknown mode: $MODE"
        echo "Usage: ./scripts/run_tests.sh [unit|e2e|smoke|all|--install|--coverage] [--headed]"
        exit 1
        ;;
esac

echo ""
echo "=== Tests completed ==="
