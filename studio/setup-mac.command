#!/bin/zsh
# Cài đặt Ghép Video trên macOS (chip Apple M1 trở lên). Không cần Homebrew hay Python có sẵn.
# Tự cài: Python 3.12 (qua uv), FFmpeg, thư viện, mô hình AI (~4,5 GB lần đầu). Chạy lại bao nhiêu lần cũng được.
# Dùng: bấm đúp, hoặc  zsh setup-mac.command [--no-open]
set -eu
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
DATA="$HOME/Library/Application Support/GhepVideo"
BIN="$DATA/bin"
VENV="$DATA/venv"
export UV_PYTHON_INSTALL_DIR="$DATA/python"
mkdir -p "$BIN"
# Files downloaded from the internet are quarantined by macOS; clear that for the whole app folder once.
xattr -dr com.apple.quarantine "$ROOT" 2>/dev/null || true

step() { print -P "\n%B▶ $1%b" }
fail() { print -P "\n%F{red}✗ $1%f"; print "Chụp màn hình cửa sổ này gửi người hỗ trợ."; exit 1 }

print -P "%B== Ghép Video · cài đặt cho macOS ==%b"
[ "$(uname -m)" = "arm64" ] || fail "Máy này không dùng chip Apple (M1 trở lên). Bản macOS cần chip Apple để chạy AI trên máy."

step "1/5 FFmpeg (xử lý video)"
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then echo "Đã có sẵn: $(command -v ffmpeg)"
elif [ -x "$BIN/ffmpeg" ] && [ -x "$BIN/ffprobe" ]; then echo "Đã có sẵn trong thư mục cài đặt."
else
  tmp=$(mktemp -d)
  for tool in ffmpeg ffprobe; do
    echo "Đang tải $tool…"
    curl -fL --progress-bar -o "$tmp/$tool.zip" "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$tool.zip" || fail "Không tải được $tool. Kiểm tra mạng rồi chạy lại."
    unzip -oq "$tmp/$tool.zip" -d "$BIN"
  done
  chmod +x "$BIN/ffmpeg" "$BIN/ffprobe"; xattr -c "$BIN/ffmpeg" "$BIN/ffprobe" 2>/dev/null || true
  rm -rf "$tmp"
fi

step "2/5 Python 3.12"
UV="$BIN/uv"
if [ ! -x "$UV" ]; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/uv.tar.gz" "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz" || fail "Không tải được uv (bộ cài Python)."
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp" && cp "$tmp"/uv-*/uv "$UV" && chmod +x "$UV"; rm -rf "$tmp"
fi
[ -x "$VENV/bin/python" ] || "$UV" venv --seed --python 3.12 "$VENV" || fail "Không tạo được môi trường Python."

step "3/5 Thư viện (lần đầu mất vài phút)"
"$UV" pip install --python "$VENV/bin/python" -q -r requirements-mac.txt || fail "Cài thư viện chưa được."

step "4/5 Mô hình AI: nghe lời đọc + xem ảnh (lần đầu ~4,5 GB)"
"$VENV/bin/python" - <<'PYCODE' || fail "Tải mô hình chưa xong. Kiểm tra mạng rồi chạy lại (phần đã tải được giữ lại)."
from huggingface_hub import snapshot_download
for repo in ('mlx-community/whisper-medium-mlx','mlx-community/Qwen3-VL-4B-Instruct-4bit'):
    print('  ', repo); snapshot_download(repo)
PYCODE

step "5/5 Bộ nhận diện khuôn mặt"
if [ -f face-detect ]; then chmod +x face-detect; xattr -c face-detect 2>/dev/null || true; echo "Sẵn sàng."
elif command -v swiftc >/dev/null; then swiftc FaceDetect.swift -o face-detect -framework Vision -framework ImageIO -module-cache-path /tmp/ghepvideo-swift-cache
else fail "Thiếu face-detect trong gói cài đặt."; fi

print -P "\n%F{green}%B✓ Cài đặt xong.%b%f"
if [[ "${1:-}" != "--no-open" ]]; then echo "Đang mở Ghép Video…"; open "$ROOT/Ghép Video.app"; fi
