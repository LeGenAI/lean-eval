# 연구실 멤버 안내: Mac Studio Lean 모델 평가 파이프라인 사용법

안녕하세요. 연구실에서 같은 네트워크를 쓰고 계신 분들은 Mac Studio를 직접 조작하지
않고도, Mac Studio에 올라가 있는 Lean 특화 모델 2개를 이용해 Lean proof 평가를
실행할 수 있습니다.

평가 코드는 아래 GitHub repo로 분리해두었습니다.

```text
https://github.com/LeGenAI/lean-eval.git
```

Mac Studio의 LM Studio API 주소는 아래로 고정해서 사용해주세요.

```text
http://192.168.0.43:1234/v1
```

사용 가능한 모델 ID는 아래 두 개입니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

모델 파일을 본인 컴퓨터에 다운로드하거나, Mac Studio에 접속해서 모델을 직접 로드할
필요는 없습니다. 본인 컴퓨터에서는 평가 코드만 실행하고, 모델 generation 요청은
Mac Studio의 LM Studio 서버로 보내는 방식입니다.

---

## 1. 평가 repo clone 및 Python 환경 준비

먼저 본인 컴퓨터에서 평가 repo를 clone합니다.

```bash
git clone https://github.com/LeGenAI/lean-eval.git
cd lean-eval
```

Python 가상환경을 만들고 패키지를 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

이미 clone해둔 repo가 있다면 새로 clone하지 말고 최신 코드만 받아오면 됩니다.

```bash
cd lean-eval
git pull --ff-only
source .venv/bin/activate
pip install -e ".[dev]"
```

이후 같은 터미널에서 평가를 실행해주세요. 새 터미널을 열면 다시 아래를 실행해야
합니다.

```bash
cd lean-eval
source .venv/bin/activate
```

설치가 제대로 되었는지 빠르게 확인하려면 아래 테스트를 실행합니다.

```bash
python -m pytest tests/test_run_proof_evaluation_cli.py tests/test_multi_turn_prover.py
```

---

## 2. Lean / Mathlib / REPL 준비

평가 파이프라인은 모델 출력만 저장하는 것이 아니라, 생성된 proof를 Lean으로 실제
검증합니다. 따라서 Lean verifier까지 실행하려면 `elan`, `lake`가 필요합니다.

처음 clone한 뒤 한 번만 아래를 실행해 Mathlib과 Lean REPL 의존성을 준비해주세요.

```bash
lake update
lake exe cache get
lake build
```

평가 코드는 기본적으로 `LEAN_VERIFIER=repl`을 사용합니다. 이는 매 proof마다 Lean을
새로 띄우는 방식이 아니라, `lake exe repl`을 persistent process로 유지하며 검증하는
방식입니다. 첫 시작은 Mathlib 로딩 때문에 느릴 수 있지만, 이후 검증은 훨씬 빠릅니다.

---

## 3. Mac Studio 서버 접속 확인

같은 네트워크에 연결된 상태에서 아래 명령을 실행해주세요.

```bash
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

정상이라면 응답 안에 아래 두 모델 ID가 보여야 합니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

여기서 실패하면 평가 코드 문제가 아니라 네트워크 또는 Mac Studio 서버 상태 문제일
가능성이 큽니다. 이 경우 담당자에게 서버 상태 확인을 요청해주세요.

---

## 4. 환경변수 설정

repo에 포함된 예시 env 파일을 사용하면 됩니다.

```bash
cp .env.example .env
set -a
source .env
set +a
```

핵심 설정은 아래와 같습니다.

```bash
export EVAL_PANEL=local
export LM_STUDIO_BASE_URL=http://192.168.0.43:1234/v1
export EVAL_GOEDEL_V2_SLUG=goedel-prover-v2-8b
export EVAL_BFS_PROVER_SLUG=bytedance-seed.bfs-prover-v2-7b
export LEAN_VERIFIER=repl
```

이 설정은 본인 컴퓨터에서 모델을 로드한다는 뜻이 아닙니다. 본인 컴퓨터의 평가
코드가 Mac Studio의 LM Studio 서버로 요청을 보내도록 지정하는 것입니다.

설정이 현재 shell에 들어갔는지 확인하려면 아래처럼 확인합니다.

```bash
echo "$LM_STUDIO_BASE_URL"
echo "$EVAL_PANEL"
echo "$EVAL_GOEDEL_V2_SLUG"
echo "$EVAL_BFS_PROVER_SLUG"
```

---

## 5. 전체 실행 흐름

실제 평가는 아래 순서로 진행하면 됩니다.

1. `git pull --ff-only`로 평가 코드를 최신화합니다.
2. `.venv`를 켜고 `pip install -e ".[dev]"`로 패키지를 최신 상태로 맞춥니다.
3. `lake build`가 정상인지 확인합니다.
4. `/v1/models`로 Mac Studio 서버와 모델 ID를 확인합니다.
5. `.env`를 source합니다.
6. 작은 cap으로 smoke test를 먼저 돌립니다.
7. 문제가 없으면 전체 평가를 `--resume`과 함께 실행합니다.
8. JSONL row 수와 summary JSON을 확인합니다.

전체 run을 바로 시작하기 전에 1-2 row만 먼저 검증하는 것을 권장합니다.

```bash
mkdir -p outputs

python scripts/run_proof_evaluation.py \
  --benchmark miniF2F \
  --control path/to/minif2f_control.csv \
  --treatment path/to/minif2f_treatment.jsonl \
  --output outputs/smoke_goedel.jsonl \
  --summary outputs/smoke_goedel_summary.json \
  --models Goedel-Prover-V2-8B \
  --K 1 \
  --T-max 1 \
  --control-cap 1 \
  --treatment-cap 1 \
  --model-timeout 60 \
  --lean-timeout 60 \
  --max-tokens 1024 \
  --resume
```

smoke test에서 확인할 것은 세 가지입니다.

- Mac Studio 모델 호출이 되는지
- Lean REPL verifier가 시작되는지
- output JSONL과 summary JSON이 생성되는지

---

## 6. 평가 방식 요약

평가 단위는 `(benchmark, arm, problem_id, model)`입니다.

각 row마다 모델이 Lean proof를 생성하고, evaluator가 Lean verifier로 검증합니다.
최종 pass 여부는 모델의 self-report가 아니라 Lean 검증 결과로 결정합니다.

### Goedel-Prover

Goedel-Prover는 theorem statement에서 proof 전체를 생성하는 모델입니다.

- endpoint: `/v1/chat/completions`
- model: `goedel-prover-v2-8b`
- 기본 사용: `--models Goedel-Prover-V2-8B`
- 평가 방식: K개의 독립 attempt를 실행하고, 각 attempt에서 최대 `T_max`번 verifier
  feedback을 반영해 refine합니다.

우리 실험에서 주로 사용한 설정은 아래입니다.

```text
K=3
T_max=2
model_timeout=60
lean_timeout=60
GOEDEL_MAX_TOKENS=3072
GOEDEL_PROMPT_STYLE=goedel_v1
```

### BFS-Prover

BFS-Prover는 proof 전체를 한 번에 생성하는 모델이 아니라, Lean proof state에서 다음
tactic 후보를 생성하는 step prover입니다.

- endpoint: `/v1/completions`
- model: `bytedance-seed.bfs-prover-v2-7b`
- 기본 사용: `--models BFS-Prover-V2-7B`
- 평가 방식: evaluator가 proof search tree를 관리하고, BFS 모델은 각 proof state에서
  tactic 후보를 제안합니다. 각 tactic은 Lean으로 검증됩니다.

대표 설정은 아래입니다.

```text
K=3
S_max=6
n_per_step=8
bfs_tree_search=true
bfs_tree_max_nodes=64
model_timeout=60
lean_timeout=60
```

---

## 7. 입력 파일 형식

평가 runner는 control CSV와 treatment JSONL을 받습니다.

```text
--control path/to/control.csv
--treatment path/to/treatment.jsonl
```

각 row에는 최소한 아래 정보가 있어야 합니다.

```text
benchmark
arm
problem_id
statement
formal_statement 또는 formal_prefix
```

`formal_statement` 또는 `formal_prefix`는 Lean theorem statement입니다. evaluator는
모델이 생성한 proof를 이 statement에 붙여 Lean으로 검증합니다. 즉, 모델이 theorem
statement를 임의로 바꿔 pass하는 것을 방지합니다.

결과를 합칠 때는 아래 key로 dedupe하는 것을 권장합니다.

```text
(benchmark, arm, problem_id, model)
```

---

## 8. Goedel-Prover 평가 실행 예시

아래는 miniF2F를 Goedel로 평가하는 예시입니다. 실제 파일 경로는 본인이 가진
control/treatment 파일 위치에 맞게 바꿔주세요.

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

`--resume`는 이미 output JSONL에 기록된 `(problem_id, model)` cell을 다시 실행하지
않도록 해줍니다. 긴 평가를 중간에 재시작할 때는 가능하면 항상 붙여주세요.

ProofNet을 평가할 때는 `--benchmark ProofNet`으로 바꾸고 파일 경로만 해당 데이터로
교체하면 됩니다.

---

## 9. BFS-Prover 평가 실행 예시

아래는 miniF2F를 BFS tree search로 평가하는 예시입니다.

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

BFS는 Lean 검증량이 많기 때문에 `LEAN_REPL_POOL_SIZE=4`처럼 REPL pool을 늘리면
빨라질 수 있습니다. 다만 각 REPL process가 Mathlib 환경을 따로 잡기 때문에, 메모리
여유가 없으면 1 또는 2로 낮춰주세요.

---

## 10. 실행 중 진행률 확인

긴 run을 돌리는 동안에는 output JSONL이 append되는지 확인하면 됩니다.

```bash
wc -l outputs/minif2f_goedel.jsonl
tail -n 1 outputs/minif2f_goedel.jsonl | python3 -m json.tool | less
```

최근 append 시각은 아래처럼 확인할 수 있습니다.

```bash
stat -f "%Sm %N" outputs/minif2f_goedel.jsonl
```

모델 쪽이 응답 중인지 확인하려면 별도 터미널에서 `/v1/models`를 다시 확인합니다.

```bash
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

row 수가 오랫동안 늘지 않으면 다음 중 하나일 수 있습니다.

- 현재 row의 model generation이 길게 걸리는 중
- Lean verifier가 timeout을 기다리는 중
- Mac Studio 모델 queue에 들어간 상태
- local Lean REPL이 죽었거나 Mathlib 환경 준비가 안 된 상태

이 경우 같은 output에 새 process를 바로 붙이지 말고, 기존 process가 살아있는지 먼저
확인해주세요.

---

## 11. 출력 파일 확인

평가가 끝나면 두 종류의 파일이 생성됩니다.

```text
outputs/minif2f_goedel.jsonl
outputs/minif2f_goedel_summary.json
```

JSONL은 row별 상세 기록입니다. 각 row에는 attempts, turns, Lean diagnostics,
최종 pass 여부가 들어갑니다.

summary JSON은 benchmark/model/arm별 pass rate와 bootstrap CI를 요약합니다.
간단히 확인하려면 아래처럼 볼 수 있습니다.

```bash
python3 -m json.tool outputs/minif2f_goedel_summary.json | less
```

JSONL row 수를 확인하려면:

```bash
wc -l outputs/minif2f_goedel.jsonl
```

pass row만 빠르게 세려면:

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

---

## 12. 병렬 실행과 shard 주의사항

여러 process를 동시에 실행할 수는 있지만, 같은 JSONL 파일에 여러 process가 동시에
쓰기 시작하면 결과가 깨질 수 있습니다.

병렬로 나눠 돌릴 때는 output 파일을 shard별로 분리해주세요.

```text
outputs/minif2f_goedel_front.jsonl
outputs/minif2f_goedel_back.jsonl
```

이후 결과를 합칠 때는 아래 key로 dedupe합니다.

```text
(benchmark, arm, problem_id, model)
```

Mac Studio 서버는 여러 사람이 공유하므로 큰 batch run을 시작하기 전에는 담당자나
다른 사용자와 충돌하지 않는지 확인해주세요.

중요한 원칙은 아래입니다.

- 같은 JSONL 파일에는 writer를 하나만 둡니다.
- 병렬 실행은 shard별 JSONL을 분리합니다.
- 중단 후 재시작할 때는 `--resume`을 사용합니다.
- 합칠 때는 `(benchmark, arm, problem_id, model)` 기준으로 dedupe합니다.
- 빈 candidate나 모델 호출 실패 row는 summary만 보지 말고 JSONL 상세를 확인합니다.

---

## 13. 모델만 직접 호출해보기

평가 파이프라인과 별개로 API 연결만 확인하고 싶다면 아래 예시를 사용할 수 있습니다.

### Goedel-Prover 직접 호출

Goedel은 `/v1/chat/completions`를 사용합니다.

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

### BFS-Prover 직접 호출

BFS는 `/v1/completions`를 사용합니다.

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

직접 호출 결과는 참고용입니다. 실제 성공 여부는 반드시 Lean verifier 결과로 판단해야
합니다.

---

## 14. 문제가 생겼을 때

### `/v1/models`가 응답하지 않는 경우

가능한 원인:

- 현재 컴퓨터가 Mac Studio와 같은 네트워크에 있지 않음
- Mac Studio IP가 바뀜
- LM Studio server가 꺼져 있음
- server가 LAN이 아니라 localhost 전용으로 열려 있음
- macOS firewall이 요청을 막고 있음

이 경우 담당자에게 서버 상태 확인을 요청해주세요.

### 모델 ID가 없다고 나오는 경우

model string이 정확한지 확인해주세요.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

오타가 없는데도 안 되면, Mac Studio에서 TTL 만료로 모델이 내려갔을 수 있습니다.
담당자에게 다시 로드를 요청해주세요.

### 요청이 느리거나 queued 상태인 경우

가능한 원인:

- 다른 사람이 이미 큰 run을 돌리는 중
- Goedel이 긴 generation을 처리하는 중
- BFS search가 많은 tactic candidate를 동시에 요청하는 중

이 경우 현재 큰 batch run이 돌고 있는지 확인하고, 서로 시간을 나눠 쓰는 것이
좋습니다.

### Lean REPL 시작이 실패하는 경우

아래를 다시 실행해보세요.

```bash
lake update
lake exe cache get
lake build
```

그래도 안 되면 `elan` 설치 여부와 `lean-toolchain` 버전이 맞는지 확인해야 합니다.
