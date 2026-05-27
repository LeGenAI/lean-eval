# lean-eval

Lean 특화 언어모델 평가를 위한 최소 실행 repo입니다. 연구실 Mac Studio의 LM Studio 서버에 올라간
Goedel-Prover와 BFS-Prover를 OpenAI-compatible API로 호출하고, 생성된 Lean proof를 `lake exe repl`
기반 verifier로 검증합니다.

Mac Studio API 주소는 아래로 고정해서 사용합니다.

```text
http://192.168.0.43:1234/v1
```

사용 모델 ID는 아래 두 개입니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

## 1. 설치

```bash
git clone https://github.com/LeGenAI/lean-eval.git
cd lean-eval

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Lean verifier까지 실행하려면 `elan`과 `lake`가 필요합니다. 처음 clone한 뒤 한 번만 아래를 실행해
Mathlib/REPL 의존성을 준비해주세요.

```bash
lake update
lake exe cache get
lake build
```

## 2. Mac Studio 서버 접속 확인

같은 네트워크에 연결된 상태에서 아래 명령을 실행합니다.

```bash
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

응답에 아래 두 모델이 보이면 정상입니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

## 3. 환경변수 설정

```bash
cp .env.example .env
set -a
source .env
set +a
```

또는 필요한 값만 직접 export해도 됩니다.

```bash
export EVAL_PANEL=local
export LM_STUDIO_BASE_URL=http://192.168.0.43:1234/v1
export EVAL_GOEDEL_V2_SLUG=goedel-prover-v2-8b
export EVAL_BFS_PROVER_SLUG=bytedance-seed.bfs-prover-v2-7b
export LEAN_VERIFIER=repl
```

## 4. Goedel-Prover 평가 실행 예시

Goedel은 theorem statement에서 전체 proof를 생성하는 chat 모델입니다. 평가 runner에서는 원래
theorem statement를 고정하고, 모델이 생성한 proof body를 붙여 Lean으로 검증합니다.

```bash
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

## 5. BFS-Prover 평가 실행 예시

BFS-Prover는 proof 전체가 아니라 proof state에서 다음 tactic 후보를 만드는 completion 모델입니다.
따라서 tree search controller와 함께 사용합니다.

```bash
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

REPL 검증이 병목이면 아래처럼 pool을 늘릴 수 있습니다. 단, 각 REPL process가 Mathlib 환경을 따로
잡으므로 메모리 여유가 있을 때만 사용하세요.

```bash
export LEAN_REPL_POOL_SIZE=4
```

## 6. 입력 파일 형식

`--control`은 seed/control CSV를 받습니다. `--treatment`는 accepted/generated problem JSONL을 받습니다.
두 입력 모두 최소한 아래 정보가 필요합니다.

```text
benchmark, arm, problem_id, statement, formal_statement 또는 formal_prefix
```

실험 결과를 합칠 때는 아래 key로 dedupe합니다.

```text
(benchmark, arm, problem_id, model)
```

## 7. Mac Studio 담당자용 모델 reload

Mac Studio 담당자는 아래 스크립트로 두 모델을 고정 ID와 TTL 1h로 다시 로드할 수 있습니다.

```bash
scripts/reload_lmstudio_lean_eval_models.sh
```

기본값:

```text
server bind: 0.0.0.0
server port: 1234
Goedel context: 4096, parallel: 1, ttl: 3600
BFS context: 2048, parallel: 8, ttl: 3600
```

상세 안내는 아래 문서를 참고하세요.

- `docs/lm_studio_lab_member_remote_call_guide.md`
- `docs/lm_studio_mac_studio_admin_guide.md`

## 8. 직접 API만 호출해보기

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
