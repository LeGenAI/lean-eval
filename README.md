# lean-eval

`lean-eval` is a lightweight evaluation pipeline for Lean-specialized language
models. It calls OpenAI-compatible model servers, verifies generated Lean proofs
with Lean 4, and writes per-problem JSONL plus aggregate summary JSON files.

The default local-lab configuration targets an LM Studio server on a Mac Studio:

```text
http://192.168.0.43:1234/v1
```

Default model identifiers:

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

Goedel-Prover is used as a whole-proof chat model. BFS-Prover is used as a
tactic-step completion model controlled by a Lean proof-search loop.

## Installation

```bash
git clone https://github.com/LeGenAI/lean-eval.git
cd lean-eval

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The verifier uses Lean 4, Mathlib, and the Lean REPL. After cloning, prepare the
Lean environment once:

```bash
lake update
lake exe cache get
lake build
```

## Server Check

Check that the Mac Studio LM Studio server is reachable:

```bash
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

The response should include:

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

## Environment

Use the included example environment file:

```bash
cp .env.example .env
set -a
source .env
set +a
```

Equivalent manual settings:

```bash
export EVAL_PANEL=local
export LM_STUDIO_BASE_URL=http://192.168.0.43:1234/v1
export EVAL_GOEDEL_V2_SLUG=goedel-prover-v2-8b
export EVAL_BFS_PROVER_SLUG=bytedance-seed.bfs-prover-v2-7b
export LEAN_VERIFIER=repl
```

`LEAN_VERIFIER=repl` keeps a persistent `lake exe repl` process alive and reuses
the loaded Mathlib environment across proof checks. This is much faster than
spawning a fresh Lean process for every candidate proof.

## Evaluation Protocol

The evaluation unit is:

```text
(benchmark, arm, problem_id, model)
```

For each row, the model generates a Lean proof candidate. The evaluator then
checks the candidate with Lean. A row is counted as passing only if Lean verifies
the proof; model self-reporting is ignored.

Goedel-Prover:

- endpoint: `/v1/chat/completions`
- runner model label: `Goedel-Prover-V2-8B`
- protocol: `K` independent attempts, each with up to `T_max` verifier-feedback
  refinement turns

BFS-Prover:

- endpoint: `/v1/completions`
- runner model label: `BFS-Prover-V2-7B`
- protocol: tree search over Lean proof states, where the model proposes tactic
  candidates and Lean validates each step

## Input Files

The runner consumes a control CSV and a treatment JSONL:

```text
--control path/to/control.csv
--treatment path/to/treatment.jsonl
```

Rows should provide at least:

```text
benchmark
arm
problem_id
statement
formal_statement or formal_prefix
```

`formal_statement` / `formal_prefix` should contain the target Lean theorem.
For Goedel-style whole-proof models, the evaluator can splice the generated
proof body onto the original theorem statement before verification, preventing a
model from changing the target theorem and receiving credit for a different
claim.

When merging shard outputs, deduplicate by:

```text
(benchmark, arm, problem_id, model)
```

## Run Goedel-Prover

```bash
mkdir -p outputs

python scripts/run_proof_evaluation.py \
  --benchmark miniF2F \
  --control path/to/minif2f_control.csv \
  --treatment path/to/minif2f_treatment.jsonl \
  --output outputs/minif2f_goedel.jsonl \
  --summary outputs/minif2f_goedel_summary.json \
  --models Goedel-Prover-V2-8B \
  --K 3 \
  --T-max 2 \
  --n-parallel 1 \
  --model-timeout 60 \
  --lean-timeout 60 \
  --max-tokens 3072 \
  --resume
```

Recommended Goedel defaults for the local LM Studio setup:

```text
K=3
T_max=2
GOEDEL_PROMPT_STYLE=goedel_v1
GOEDEL_MAX_TOKENS=3072
model_timeout=60
lean_timeout=60
```

## Run BFS-Prover

```bash
mkdir -p outputs

export LEAN_REPL_POOL_SIZE=4

python scripts/run_proof_evaluation.py \
  --benchmark miniF2F \
  --control path/to/minif2f_control.csv \
  --treatment path/to/minif2f_treatment.jsonl \
  --output outputs/minif2f_bfs.jsonl \
  --summary outputs/minif2f_bfs_summary.json \
  --models BFS-Prover-V2-7B \
  --K 3 \
  --S-max 6 \
  --n-per-step 8 \
  --bfs-tree-search \
  --bfs-tree-max-nodes 64 \
  --model-timeout 60 \
  --lean-timeout 60 \
  --resume
```

BFS performs many Lean checks. Increasing `LEAN_REPL_POOL_SIZE` can improve
throughput on machines with enough memory.

## Outputs

The runner writes:

```text
outputs/<run>.jsonl
outputs/<run>_summary.json
```

The JSONL file stores per-row details, including attempts, turns, verifier
diagnostics, elapsed times, and `pass_at_k`.

The summary JSON stores benchmark/model/arm pass rates and bootstrap confidence
intervals.

Quick checks:

```bash
wc -l outputs/minif2f_goedel.jsonl
python3 -m json.tool outputs/minif2f_goedel_summary.json | less
```

Count passing rows:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("outputs/minif2f_goedel.jsonl")
rows = [json.loads(line) for line in path.open() if line.strip()]
print("rows:", len(rows))
print("pass:", sum(bool(r.get("pass_at_k")) for r in rows))
PY
```

## Parallel Runs and Shards

Do not let multiple processes write to the same JSONL file at the same time.
For parallel evaluation, write separate shard outputs:

```text
outputs/minif2f_goedel_front.jsonl
outputs/minif2f_goedel_back.jsonl
```

Merge later using the dedupe key:

```text
(benchmark, arm, problem_id, model)
```

## Mac Studio Model Reload

The Mac Studio administrator can reload both LM Studio models with fixed IDs and
an idle TTL of one hour:

```bash
scripts/reload_lmstudio_lean_eval_models.sh
```

Defaults:

```text
server bind: 0.0.0.0
server port: 1234
Goedel context: 4096, parallel: 1, ttl: 3600
BFS context: 2048, parallel: 8, ttl: 3600
```

## Additional Guides

- Korean lab-member guide: `docs/lm_studio_lab_member_remote_call_guide.md`
- Mac Studio administrator guide: `docs/lm_studio_mac_studio_admin_guide.md`

## Direct API Smoke Tests

Goedel:

```bash
curl http://192.168.0.43:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "goedel-prover-v2-8b",
    "messages": [
      {"role": "system", "content": ""},
      {"role": "user", "content": "Complete the following Lean 4 code:\n\n```lean4\nimport Mathlib\n\nexample : 1 + 1 = 2 := by sorry\n```"}
    ],
    "temperature": 0,
    "max_tokens": 1024
  }'
```

BFS:

```bash
curl http://192.168.0.43:1234/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bytedance-seed.bfs-prover-v2-7b",
    "prompt": "⊢ 1 + 1 = 2:::",
    "temperature": 0.7,
    "max_tokens": 256,
    "stop": [":::", "\n\n"]
  }'
```
