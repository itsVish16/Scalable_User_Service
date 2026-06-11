#!/bin/bash
# =============================================================================
# Scalable User Service — Multi-Worker Benchmark Suite
# =============================================================================
# Runs systematic benchmarks across different uvicorn worker configurations
# and collects results into a single output file.
#
# Usage: bash bench_runner.sh
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_FILE="$PROJECT_DIR/bench_results.txt"
HOST="http://localhost:8000"

# Common env vars — local Docker infra, no rate limiting, no email
export DATABASE_URL="postgresql+asyncpg://userservice:userservice@localhost:5432/userservice"
export REDIS_URL="redis://localhost:6379/0"
export ENABLE_RATE_LIMITING=false
export EMAIL_DELIVERY_ENABLED=false
export DEBUG=true

# Clear previous results
echo "========================================" > "$RESULTS_FILE"
echo "  BENCHMARK RESULTS — $(date)" >> "$RESULTS_FILE"
echo "  Machine: $(uname -m) $(sysctl -n hw.memsize 2>/dev/null | awk '{print $0/1073741824 " GB RAM"}' 2>/dev/null || echo 'unknown')" >> "$RESULTS_FILE"
echo "  CPUs: $(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 'unknown')" >> "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"

wait_for_server() {
    local retries=0
    while ! curl -sf "$HOST/health/live" > /dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -gt 30 ]; then
            echo "ERROR: Server failed to start"
            return 1
        fi
        sleep 1
    done
    echo "Server is up"
}

kill_server() {
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 2
}

run_bench() {
    local label="$1"
    local workers="$2"
    local loop_flag="$3"
    local mode="$4"
    local users="$5"
    local duration="$6"

    echo ""
    echo "=== $label ==="
    echo ""

    kill_server

    # Start server
    if [ "$loop_flag" = "uvloop" ]; then
        uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$workers" --loop uvloop &
    else
        uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$workers" &
    fi
    local server_pid=$!

    wait_for_server

    # Warmup — 5 seconds with 5 users
    echo "Warming up..."
    LOAD_TEST_MODE="$mode" uv run locust -f locustfile.py --host "$HOST" \
        --users 5 --spawn-rate 5 --run-time 5s --headless --only-summary \
        > /dev/null 2>&1 || true
    sleep 1

    # Actual benchmark
    echo "Running: $label ($users users, ${duration})"
    echo "" >> "$RESULTS_FILE"
    echo "--- $label ---" >> "$RESULTS_FILE"
    echo "Workers: $workers | Loop: $loop_flag | Mode: $mode | Users: $users | Duration: $duration" >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"

    LOAD_TEST_MODE="$mode" uv run locust -f locustfile.py --host "$HOST" \
        --users "$users" --spawn-rate "$users" --run-time "$duration" \
        --headless --only-summary 2>&1 | tail -30 >> "$RESULTS_FILE"

    # Grab cache metrics
    echo "" >> "$RESULTS_FILE"
    echo "Prometheus Cache Metrics:" >> "$RESULTS_FILE"
    curl -s "$HOST/metrics" 2>/dev/null | grep "^cache_operations_total" >> "$RESULTS_FILE" || echo "  (none)" >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"

    kill_server
    echo "Done: $label"
}

# =============================================================================
# BENCHMARK SUITE
# =============================================================================

cd "$PROJECT_DIR"

echo "Starting benchmark suite..."
echo "Results will be saved to: $RESULTS_FILE"
echo ""

# --- Test 1: Worker Scaling (steady, 50 users, 60s each) ---
run_bench "1 Worker (default loop)"    1 "default"  "steady" 50  "60s"
run_bench "2 Workers (default loop)"   2 "default"  "steady" 50  "60s"
run_bench "4 Workers (default loop)"   4 "default"  "steady" 50  "60s"

# --- Test 2: uvloop comparison (4 workers) ---
run_bench "4 Workers (uvloop)"         4 "uvloop"   "steady" 50  "60s"

# --- Test 3: DB-only benchmark (4 workers, uvloop) ---
run_bench "DB Bench (4w, uvloop)"      4 "uvloop"   "db"     50  "30s"

# --- Test 4: Spike test (4 workers, uvloop, 200 users) ---
run_bench "Spike 200u (4w, uvloop)"    4 "uvloop"   "spike"  200 "30s"

# --- Test 5: The Big One — 500 user soak (4 workers, uvloop, 5 min) ---
run_bench "Soak 500u (4w, uvloop)"     4 "uvloop"   "steady" 500 "300s"

echo ""
echo "========================================"
echo "  ALL BENCHMARKS COMPLETE"
echo "  Results saved to: $RESULTS_FILE"
echo "========================================"
echo ""
cat "$RESULTS_FILE"
