#!/bin/sh
set -e

echo "Iniciando Dashboard Full (Next.js SSR + FastAPI)..."

cleanup() {
  echo "Parando serviços..."
  kill $FASTAPI_PID $NEXTJS_PID 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}

trap cleanup TERM INT

# 1) Iniciar FastAPI
echo "Subindo FastAPI (porta 8000)..."
uvicorn dashboard_api:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!
sleep 3

if ! kill -0 $FASTAPI_PID 2>/dev/null; then
  echo "ERRO: FastAPI falhou ao iniciar"
  exit 1
fi

# 2) Iniciar Next SSR
echo "Subindo Next.js (porta 3000)..."
cd /app/next-app
PORT=3000 node server.js &
NEXTJS_PID=$!
sleep 3

if ! kill -0 $NEXTJS_PID 2>/dev/null; then
  echo "ERRO: Next.js falhou ao iniciar"
  kill $FASTAPI_PID 2>/dev/null || true
  exit 1
fi

echo "Dashboard pronto! Next: :3000 | FastAPI: :8000"

# Monitorar processos
while true
do
  if ! kill -0 $FASTAPI_PID 2>/dev/null; then
    echo "FastAPI parou inesperadamente"
    exit 1
  fi
  if ! kill -0 $NEXTJS_PID 2>/dev/null; then
    echo "Next.js parou inesperadamente"
    exit 1
  fi
  sleep 10
done