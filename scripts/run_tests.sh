#!/bin/bash
# Script for running tests locally
# Usage: ./scripts/run_tests.sh [--coverage]

set -e

cd "$(dirname "$0")/.."

echo "=== Running Tayfa Tests ==="

if [ "$1" == "--coverage" ]; then
    echo "Running with coverage..."
    cd kok
    pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html
    echo ""
    echo "Coverage HTML report: kok/htmlcov/index.html"
else
    cd kok
    pytest tests/ -v
fi

echo ""
echo "=== Tests completed ==="
