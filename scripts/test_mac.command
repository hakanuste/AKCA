#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then echo "Önce start_mac.command dosyasını çalıştırın."; exit 1; fi
source .venv/bin/activate
python -m compileall -q src
pytest -q
ruff check src tests
