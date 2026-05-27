# 연구실 멤버 안내: Mac Studio의 Lean 모델 원격 호출하기

안녕하세요. 연구실에서 같은 네트워크를 쓰고 계신 분들은 Mac Studio를 직접
조작하지 않고도, Mac Studio에 올라가 있는 Lean 특화 모델 2개를 API로 호출하실 수
있습니다.

여러분이 사용하실 API 주소는 아래입니다.

```text
http://192.168.0.43:1234/v1
```

사용 가능한 모델 ID는 아래 두 개입니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

모델 파일을 따로 다운로드하거나 Mac Studio에 접속해서 모델을 직접 로드하실 필요는
없습니다. 본인 컴퓨터에서 위 API 주소로 요청만 보내시면 됩니다.

---

## 1. 먼저 접속 확인하기

본인 컴퓨터에서 아래 명령을 실행해주세요.

```bash
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

정상이라면 응답 안에 아래 두 모델 ID가 보여야 합니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

여기서 실패하면 코드 문제가 아니라 네트워크 또는 Mac Studio 서버 상태 문제일
가능성이 큽니다. 이 경우 담당자에게 서버 상태 확인을 요청해주세요.

---

## 2. 어떤 모델을 써야 하나요?

| 목적 | 모델 ID | endpoint |
|---|---|---|
| Lean theorem statement에서 proof 전체 생성 | `goedel-prover-v2-8b` | `/v1/chat/completions` |
| Lean proof state에서 다음 tactic 후보 생성 | `bytedance-seed.bfs-prover-v2-7b` | `/v1/completions` |

간단히 말하면:

- Goedel은 “전체 Lean proof를 생성하는 모델”입니다.
- BFS는 “다음 tactic 후보를 생성하는 step prover”입니다.

따라서 Goedel은 chat endpoint를 쓰고, BFS는 completions endpoint를 씁니다.

---

## 3. 평가 코드에서 사용할 환경변수

우리 평가 repo나 Python script에서 사용하실 경우, 터미널에 아래처럼 설정하시면
됩니다.

```bash
export LM_STUDIO_BASE_URL=http://192.168.0.43:1234/v1
export EVAL_PANEL=local

export EVAL_GOEDEL_V2_SLUG=goedel-prover-v2-8b
export EVAL_BFS_PROVER_SLUG=bytedance-seed.bfs-prover-v2-7b
```

이 설정은 본인 컴퓨터에서 모델을 로드한다는 뜻이 아닙니다. 본인 컴퓨터의 코드가
Mac Studio의 LM Studio 서버로 요청을 보내도록 주소를 지정하는 것입니다.

---

## 4. Goedel-Prover 호출 예시

Goedel-Prover는 Lean theorem statement를 보고 proof 전체를 생성하는 모델입니다.
OpenAI 호환 API의 `/v1/chat/completions` endpoint를 사용합니다.

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

주의하실 점:

- Goedel 출력에는 proof plan이나 설명이 같이 섞일 수 있습니다.
- 모델 출력은 Lean 검증 전까지 정답으로 보면 안 됩니다.
- 평가 pipeline에서는 fenced Lean code만 추출하고, 원래 theorem statement에 proof
  body를 붙인 뒤 Lean으로 다시 검증합니다.

---

## 5. BFS-Prover 호출 예시

BFS-Prover는 proof 전체를 한 번에 생성하는 모델이 아닙니다. Lean proof state를 보고
다음 tactic 후보를 생성하는 tactic-step 모델입니다.

따라서 `/v1/chat/completions`가 아니라 `/v1/completions`를 사용합니다.

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

주의하실 점:

- BFS의 raw output은 보통 tactic 후보일 뿐입니다.
- 실제 성공 여부는 그 tactic을 Lean proof에 넣고 Lean verifier로 확인해야 합니다.
- BFS는 보통 단독 호출보다는 search controller와 함께 쓰는 것이 맞습니다.

---

## 6. Python에서 호출하기

OpenAI Python client를 사용하면 됩니다.

```bash
pip install openai
```

### Goedel-Prover

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://192.168.0.43:1234/v1",
    api_key="lm-studio",
)

resp = client.chat.completions.create(
    model="goedel-prover-v2-8b",
    messages=[
        {"role": "system", "content": ""},
        {
            "role": "user",
            "content": "Complete the following Lean 4 code:\n\n```lean4\nimport Mathlib\n\nexample : 1 + 1 = 2 := by sorry\n```",
        },
    ],
    temperature=0,
    max_tokens=1024,
)

print(resp.choices[0].message.content)
```

### BFS-Prover

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://192.168.0.43:1234/v1",
    api_key="lm-studio",
)

resp = client.completions.create(
    model="bytedance-seed.bfs-prover-v2-7b",
    prompt="⊢ 1 + 1 = 2:::",
    temperature=0.7,
    max_tokens=256,
    stop=[":::", "\n\n"],
)

print(resp.choices[0].text)
```

---

## 7. 같이 사용할 때 주의사항

여러 명이 같은 Mac Studio 서버를 공유하므로 아래 사항을 지켜주세요.

1. 모델 ID는 그대로 사용해주세요.
2. Goedel은 `/v1/chat/completions`로 호출해주세요.
3. BFS는 `/v1/completions`로 호출해주세요.
4. 모델 출력은 Lean 검증 전까지 정답으로 취급하지 말아주세요.
5. 큰 batch run을 여러 명이 동시에 돌리면 queue가 생길 수 있습니다.
6. Goedel은 긴 generation을 수행하므로 특히 queue가 생기기 쉽습니다.
7. 실험 결과를 합칠 때는 아래 key로 dedupe하는 것을 권장합니다.

```text
(benchmark, arm, problem_id, model)
```

---

## 8. 문제가 생겼을 때

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
- Goedel이 긴 요청을 처리하는 중
- BFS search가 많은 tactic candidate를 동시에 요청하는 중

이 경우 현재 큰 batch run이 돌고 있는지 확인하고, 서로 시간을 나눠 쓰는 것이
좋습니다.
