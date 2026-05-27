#!/usr/bin/env bash
set -euo pipefail

# Deterministic LM Studio reload for the Lean evaluation panel.
# This exposes the OpenAI-compatible endpoint on the lab LAN by default:
# http://192.168.0.43:1234/v1, assuming the Mac Studio currently owns that IP.

LMS="${LMS:-$HOME/.lmstudio/bin/lms}"
LMS_SERVER_BIND="${LMS_SERVER_BIND:-0.0.0.0}"
LMS_SERVER_PORT="${LMS_SERVER_PORT:-1234}"

GOEDEL_MODEL="${GOEDEL_MODEL:-goedel-prover-v2-8b}"
GOEDEL_ID="${GOEDEL_ID:-goedel-prover-v2-8b}"
GOEDEL_CONTEXT="${GOEDEL_CONTEXT:-4096}"
GOEDEL_PARALLEL="${GOEDEL_PARALLEL:-1}"

BFS_MODEL="${BFS_MODEL:-bytedance-seed.bfs-prover-v2-7b}"
BFS_ID="${BFS_ID:-bytedance-seed.bfs-prover-v2-7b}"
BFS_CONTEXT="${BFS_CONTEXT:-2048}"
BFS_PARALLEL="${BFS_PARALLEL:-8}"

TTL="${TTL:-3600}"

if [[ ! -x "$LMS" ]]; then
  echo "lms CLI not found at $LMS" >&2
  exit 1
fi

"$LMS" server start --port "$LMS_SERVER_PORT" --bind "$LMS_SERVER_BIND" >/dev/null || true

"$LMS" unload "$GOEDEL_ID" 2>/dev/null || true
"$LMS" unload "$BFS_ID" 2>/dev/null || true

"$LMS" load "$GOEDEL_MODEL" \
  --gpu max \
  --context-length "$GOEDEL_CONTEXT" \
  --parallel "$GOEDEL_PARALLEL" \
  --ttl "$TTL" \
  --identifier "$GOEDEL_ID" \
  -y

"$LMS" load "$BFS_MODEL" \
  --gpu max \
  --context-length "$BFS_CONTEXT" \
  --parallel "$BFS_PARALLEL" \
  --ttl "$TTL" \
  --identifier "$BFS_ID" \
  -y

"$LMS" ps
