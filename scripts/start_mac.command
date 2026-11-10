#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${AKCA_PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11+ bulunamadı. Homebrew ile: brew install python@3.12"
  read -r -p "Kapatmak için Enter..."
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("AKÇA Python 3.11 veya üzerini gerektirir. Homebrew: brew install python@3.12")
print("Python", sys.version.split()[0])
PY

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
fi

python - <<'PY'
from pathlib import Path
import secrets
path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
found = False
for i, line in enumerate(lines):
    if line.startswith("AKCA_API_KEY="):
        found = True
        if not line.partition("=")[2].strip():
            lines[i] = "AKCA_API_KEY=" + secrets.token_hex(32)
if not found:
    lines.append("AKCA_API_KEY=" + secrets.token_hex(32))
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Yerel API anahtarı .env dosyasında hazır. Bu dosyayı paylaşmayın veya GitHub'a yüklemeyin.")
PY

akca init
echo ""
echo "AKÇA terminali: http://127.0.0.1:8000/terminal.html"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
if [ -n "$LAN_IP" ]; then
  echo "Aynı Wi-Fi ağındaki iPhone: http://$LAN_IP:8000/terminal.html"
fi
echo "Durdurmak için bu pencerede Ctrl+C."
echo ""
uvicorn akca.api:app --host 0.0.0.0 --port 8000
