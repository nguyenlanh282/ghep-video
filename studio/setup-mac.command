#!/bin/zsh
# Cài đặt Ghép Video trên macOS (Apple Silicon). Bấm đúp để chạy; chạy lại bao nhiêu lần cũng được.
set -eu
cd "$(dirname "$0")"
# Files downloaded from the internet are quarantined by macOS; clear that for the whole app folder once.
xattr -dr com.apple.quarantine "$(cd .. && pwd)" 2>/dev/null || true
DATA="$HOME/Library/Application Support/GhepVideo"
VENV="$DATA/venv"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "== Ghép Video · cài đặt cho macOS =="
if [ "$(uname -m)" != "arm64" ]; then
  echo "Máy này không dùng chip Apple (M1 trở lên). Bản macOS cần chip Apple để chạy AI trên máy."; exit 1
fi
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then echo "Cài FFmpeg qua Homebrew…"; brew install ffmpeg
  else echo "Cần FFmpeg. Cài Homebrew (https://brew.sh) rồi chạy: brew install ffmpeg"; exit 1; fi
fi
PY=""
for c in /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,14) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null; then brew install python@3.12; PY=/opt/homebrew/bin/python3.12
  else echo "Cần Python 3.10–3.13. Cài Homebrew rồi chạy: brew install python@3.12"; exit 1; fi
fi

mkdir -p "$DATA"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
echo "Cài thư viện (lần đầu mất vài phút)…"
"$VENV/bin/pip" install -q -r requirements-mac.txt

echo "Tải mô hình AI (lần đầu khoảng 4,5 GB: nghe lời đọc + xem ảnh)…"
"$VENV/bin/python" - <<'PYCODE'
from huggingface_hub import snapshot_download
for repo in ('mlx-community/whisper-medium-mlx','mlx-community/Qwen3-VL-4B-Instruct-4bit'):
    print('  ', repo); snapshot_download(repo)
PYCODE

if [ ! -x face-detect ] && command -v swiftc >/dev/null; then
  echo "Biên dịch bộ nhận diện khuôn mặt…"
  swiftc FaceDetect.swift -o face-detect -framework Vision -framework ImageIO -module-cache-path /tmp/ghepvideo-swift-cache
fi
[ -x face-detect ] || echo "Chú ý: thiếu face-detect (cần Xcode Command Line Tools: xcode-select --install)."

echo ""
echo "Xong. Mở app bằng cách bấm đúp “Ghép Video.app” trong thư mục dự án."
