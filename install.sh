#!/usr/bin/env bash
# One-line installer (Linux/macOS): checks Git + Python, clones extractor2, runs setup.
set -e
echo "=== Extractor2 setup ==="

if ! command -v git >/dev/null 2>&1; then
  echo "Git not found. Installing..."
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y git
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y git
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --noconfirm git
  elif command -v brew >/dev/null 2>&1; then brew install git
  else echo "Install git manually, then re-run." >&2; exit 1; fi
fi
echo "Git found: $(command -v git)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 not found. Installing..."
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y python3
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y python3
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --noconfirm python
  elif command -v brew >/dev/null 2>&1; then brew install python3
  else echo "Install python3 manually, then re-run." >&2; exit 1; fi
fi
echo "Python found: $(command -v python3)"

DEST="$HOME/extractor2"
if [ -d "$DEST" ]; then
  echo "Already cloned at $DEST — updating..."
  cd "$DEST" && git pull
else
  git clone https://github.com/Santhosh595/extractor2.git "$DEST"
  cd "$DEST"
fi

echo
echo "Next: enter your Telegram bot token and chat id (saved encrypted, password-protected)."
python3 extractor2.py setup

echo
echo "Done. Preview:  python3 extractor2.py run --once --dry-run"
echo "Schedule daily with cron: see README."
