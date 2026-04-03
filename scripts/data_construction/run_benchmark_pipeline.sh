#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MEETING_DIR="${MEETING_DIR:-data/VCSum_selected_batch1/meetings}"
LEVELS="${LEVELS:-L2,L3}"
PIPELINE_ROOT="${PIPELINE_ROOT:-out_vcsum_batch1}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-$PIPELINE_ROOT/Benchmark_QA}"
AUDIT_OUTPUT_DIR="${AUDIT_OUTPUT_DIR:-$PIPELINE_ROOT/benchmark_audit}"
CLEANED_OUTPUT_ROOT="${CLEANED_OUTPUT_ROOT:-$PIPELINE_ROOT/Benchmark_QA_cleaned}"
REWRITE_MODE="${REWRITE_MODE:-llm}"
MAX_WORKERS="${MAX_WORKERS:-6}"
MAX_RETRIES="${MAX_RETRIES:-2}"
MODEL_AUDIT="${MODEL_AUDIT:-gpt-5}"
MODEL_CLEANUP="${MODEL_CLEANUP:-gpt-5}"
POST_AUDIT_MODEL="${POST_AUDIT_MODEL:-gpt-5}"
ACMMM_API_KEYS="${ACMMM_API_KEYS:-${ACMMM_AUDIT_API_KEYS:-}}"
QA_KEY_1="${QA_KEY_1:-}"
QA_KEY_2="${QA_KEY_2:-}"
STAGES="${STAGES:-qa,audit,cleanup}"

if [[ -z "$ACMMM_API_KEYS" ]]; then
  echo "缺少 ACMMM_API_KEYS 或 ACMMM_AUDIT_API_KEYS" >&2
  exit 1
fi

IFS=',' read -r -a API_KEYS_ARR <<< "$ACMMM_API_KEYS"
if [[ -z "$QA_KEY_1" ]]; then
  QA_KEY_1="${API_KEYS_ARR[0]}"
fi
if [[ -z "$QA_KEY_2" ]]; then
  if [[ ${#API_KEYS_ARR[@]} -ge 2 ]]; then
    QA_KEY_2="${API_KEYS_ARR[1]}"
  else
    QA_KEY_2="${API_KEYS_ARR[0]}"
  fi
fi

mkdir -p "$PIPELINE_ROOT" "$AUDIT_OUTPUT_DIR" "$(dirname "$CLEANED_OUTPUT_ROOT")"

has_stage() {
  local stage="$1"
  [[ ",$STAGES," == *",$stage,"* ]]
}

run_qa_parallel() {
  local levels_csv="$1"
  local benchmark_root="$2"
  local meeting_dir="$3"
  IFS=',' read -r -a levels_arr <<< "$levels_csv"

  mkdir -p "$benchmark_root"
  local pids=()
  local idx=0
  for raw_level in "${levels_arr[@]}"; do
    local level
    level="$(echo "$raw_level" | xargs | tr '[:lower:]' '[:upper:]')"
    [[ -z "$level" ]] && continue
    local key="$QA_KEY_1"
    if (( idx % 2 == 1 )); then
      key="$QA_KEY_2"
    fi
    idx=$((idx + 1))
    echo "[QA] 启动层级 $level"
    ACMMM_JUDGE_API_KEY="$key" \
    SOURCE_MEETING_DIR="$meeting_dir" \
    FINAL_OUTPUT_ROOT="$benchmark_root" \
    EVIDENCE_DIR_L1="$PIPELINE_ROOT/L1/Evidence" \
    EVIDENCE_DIR_L2="$PIPELINE_ROOT/L2/Evidence" \
    EVIDENCE_DIR_L3="$PIPELINE_ROOT/L3/Evidence" \
    QA_LEVELS="$level" \
    python -u scripts/data_construction/qa_gen.py --levels "$level" \
      > "$PIPELINE_ROOT/qa_${level}.log" 2>&1 &
    pids+=("$!")
  done

  for pid in "${pids[@]}"; do
    wait "$pid"
  done
}

if has_stage "qa"; then
  run_qa_parallel "$LEVELS" "$BENCHMARK_ROOT" "$MEETING_DIR"
fi

if has_stage "audit"; then
  python -u scripts/data_construction/benchmark_audit.py \
    --benchmark-root "$BENCHMARK_ROOT" \
    --source-root "$MEETING_DIR" \
    --output-dir "$AUDIT_OUTPUT_DIR" \
    --cache-path "$AUDIT_OUTPUT_DIR/audit_cache.jsonl" \
    --api-keys "$ACMMM_API_KEYS" \
    --model "$MODEL_AUDIT" \
    --max-workers "$MAX_WORKERS" \
    --max-retries "$MAX_RETRIES"
fi

if has_stage "cleanup"; then
  python -u scripts/data_construction/benchmark_cleanup.py \
    --benchmark-root "$BENCHMARK_ROOT" \
    --audit-results "$AUDIT_OUTPUT_DIR/audit_results.csv" \
    --source-root "$MEETING_DIR" \
    --output-root "$CLEANED_OUTPUT_ROOT" \
    --rewrite-mode "$REWRITE_MODE" \
    --rewrite-cache-path "$PIPELINE_ROOT/benchmark_cleanup/rewrite_cache.jsonl" \
    --post-audit-cache-path "$PIPELINE_ROOT/benchmark_cleanup/post_audit_cache.jsonl" \
    --api-keys "$ACMMM_API_KEYS" \
    --model "$MODEL_CLEANUP" \
    --post-audit-model "$POST_AUDIT_MODEL" \
    --max-workers "$MAX_WORKERS" \
    --max-retries "$MAX_RETRIES"
fi

echo "Pipeline done."
echo "meeting_dir=$MEETING_DIR"
echo "benchmark_root=$BENCHMARK_ROOT"
echo "audit_output_dir=$AUDIT_OUTPUT_DIR"
echo "cleaned_output_root=$CLEANED_OUTPUT_ROOT"
