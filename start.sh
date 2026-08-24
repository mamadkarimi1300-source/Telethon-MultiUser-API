#!/bin/bash

cd /opt/Telethon-v2-test

.venv/bin/python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8089 &

cd /opt/Telethon-v2-test/frontend

python3 -m http.server 5173 \
  --directory /opt/Telethon-v2-test/frontend/dist \
  --bind 0.0.0.0 &

wait
