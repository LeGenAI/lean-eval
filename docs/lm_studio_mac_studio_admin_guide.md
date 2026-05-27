# Mac Studio 담당자 운영 가이드: LM Studio Lean 모델 서빙 상태 관리

이 문서는 Mac Studio 담당자인 제가 서버 상태를 준비하고 점검할 때 쓰는 운영용
메모입니다. 연구실 멤버에게 공유할 사용자용 문서는 아래 파일입니다.

```text
docs/lm_studio_lab_member_remote_call_guide.md
```

연구실 멤버에게 안내할 base URL은 아래로 고정합니다.

```text
http://192.168.0.43:1234/v1
```

---

## 1. 목표 상태

Mac Studio에서 아래 상태를 유지합니다.

```text
LM Studio server running
server bind: 0.0.0.0
port: 1234
Goedel model: loaded, IDLE, TTL about 1h
BFS model: loaded, IDLE, TTL about 1h
```

모델 ID는 아래와 같이 고정합니다.

```text
goedel-prover-v2-8b
bytedance-seed.bfs-prover-v2-7b
```

---

## 2. Mac Studio IP 확인

연구실 멤버에게 안내할 IP는 현재 아래 주소 기준입니다.

```text
192.168.0.43
```

필요하면 Mac Studio에서 다시 확인합니다.

```bash
ipconfig getifaddr en0
```

유선 Ethernet이면 아래도 확인합니다.

```bash
ipconfig getifaddr en1
```

IP가 바뀌면 멤버용 문서의 URL도 같이 갱신해야 합니다.

---

## 3. LM Studio server 시작

같은 네트워크에서 접근 가능하게 하려면 `127.0.0.1`이 아니라 `0.0.0.0`으로 bind해야
합니다.

```bash
lms server start --port 1234 --bind 0.0.0.0
```

상태 확인:

```bash
lms server status
```

서버를 재시작해야 하면:

```bash
lms server stop
lms server start --port 1234 --bind 0.0.0.0
```

---

## 4. stale model slot 정리

모델을 다시 로드하기 전에는 기존 slot을 먼저 내립니다.

```bash
lms unload bytedance-seed.bfs-prover-v2-7b 2>/dev/null || true
lms unload goedel-prover-v2-8b 2>/dev/null || true
```

`lms ps`에 `:2` 같은 중복 identifier가 보이면 그것도 내립니다.

---

## 5. BFS-Prover-V2-7B 로드

BFS는 tactic-step 모델입니다. 여러 tactic 후보를 병렬로 요청할 수 있으므로
`--parallel 8`로 둡니다.

```bash
lms load bytedance-seed.bfs-prover-v2-7b \
  --gpu max \
  --context-length 2048 \
  --parallel 8 \
  --ttl 3600 \
  --identifier bytedance-seed.bfs-prover-v2-7b \
  -y
```

---

## 6. Goedel-Prover-V2-8B 로드

Goedel은 whole-proof 모델입니다. 긴 proof generation을 수행하므로 기본 운영은
`--parallel 1`로 둡니다.

```bash
lms load goedel-prover-v2-8b \
  --gpu max \
  --context-length 4096 \
  --parallel 1 \
  --ttl 3600 \
  --identifier goedel-prover-v2-8b \
  -y
```

---

## 7. 상태 확인

```bash
lms ps
```

정상 예시:

```text
IDENTIFIER                         STATUS  CONTEXT  PARALLEL  TTL
bytedance-seed.bfs-prover-v2-7b    IDLE    2048     8         1h
goedel-prover-v2-8b                IDLE    4096     1         1h
```

JSON으로 확인:

```bash
lms ps --json
```

API에서 보이는지 확인:

```bash
curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

---

## 8. 한 번에 재시작하는 setup block

필요하면 아래 블록을 그대로 실행합니다.

```bash
set -e

lms server start --port 1234 --bind 0.0.0.0

lms unload bytedance-seed.bfs-prover-v2-7b 2>/dev/null || true
lms unload goedel-prover-v2-8b 2>/dev/null || true

lms load bytedance-seed.bfs-prover-v2-7b \
  --gpu max \
  --context-length 2048 \
  --parallel 8 \
  --ttl 3600 \
  --identifier bytedance-seed.bfs-prover-v2-7b \
  -y

lms load goedel-prover-v2-8b \
  --gpu max \
  --context-length 4096 \
  --parallel 1 \
  --ttl 3600 \
  --identifier goedel-prover-v2-8b \
  -y

lms ps
```

---

## 9. 멤버에게 안내할 문장

서버가 정상 상태라면 연구실 멤버에게 아래처럼 안내하면 됩니다.

```text
Mac Studio LM Studio 서버가 열려 있습니다.
base URL은 http://192.168.0.43:1234/v1 입니다.

Goedel-Prover는 model="goedel-prover-v2-8b"로 /v1/chat/completions를 사용하세요.
BFS-Prover는 model="bytedance-seed.bfs-prover-v2-7b"로 /v1/completions를 사용하세요.

먼저 아래로 접속 확인하시면 됩니다.
curl -s http://192.168.0.43:1234/v1/models | python3 -m json.tool
```

---

## 10. 운영 시 주의사항

1. 멤버들이 쓰는 동안 모델을 reload하지 않습니다.
2. TTL이 만료되면 모델이 내려갈 수 있으므로, 장시간 idle 후에는 `lms ps`를 확인합니다.
3. Goedel은 긴 generation을 수행하므로 queue가 생기기 쉽습니다.
4. BFS는 parallel slot을 많이 쓰므로 동시에 여러 BFS search가 돌면 지연될 수 있습니다.
5. IP가 바뀌면 멤버용 문서와 안내 문구를 갱신합니다.
6. macOS firewall이나 네트워크 변경 후에는 client에서 `/v1/models`가 보이는지 확인합니다.
