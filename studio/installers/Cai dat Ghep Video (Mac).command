#!/bin/zsh
# Cài Ghép Video bằng 1 lần bấm (macOS, chip Apple M1 trở lên).
# Tải bản mới nhất từ GitHub → kiểm tra SHA-256 → đặt vào ~/Ghép Video → cài Python, FFmpeg, thư viện, mô hình AI → mở app.
# Cũng chạy được bằng 1 lệnh trong Terminal (không bị macOS chặn):
#   curl -fsSL https://raw.githubusercontent.com/nguyenlanh282/ghep-video/main/studio/installers/install-mac.sh | zsh
set -eu
MANIFEST="${GHEPVIDEO_MANIFEST:-https://github.com/nguyenlanh282/ghep-video/releases/latest/download/latest.json}"
DEST="${GHEPVIDEO_DIR:-$HOME/Ghép Video}"
fail() { print -P "\n%F{red}✗ $1%f"; print "Chụp màn hình cửa sổ này gửi người hỗ trợ."; exit 1 }

print -P "%B== Cài đặt Ghép Video ==%b"
[ "$(uname -m)" = "arm64" ] || fail "Máy này không dùng chip Apple (M1 trở lên). Ghép Video cho Mac cần chip Apple."
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

print "Đang tìm bản mới nhất…"
curl -fsSL -o "$tmp/latest.json" "$MANIFEST" || fail "Không kết nối được máy chủ cập nhật. Kiểm tra mạng rồi chạy lại."
ver=$(plutil -extract version raw -o - "$tmp/latest.json");url=$(plutil -extract url raw -o - "$tmp/latest.json");sha=$(plutil -extract sha256 raw -o - "$tmp/latest.json")
case "$url" in http*|file:*) ;; *) url="${MANIFEST%/*}/$url";; esac

print "Đang tải Ghép Video $ver…"
curl -fL --progress-bar -o "$tmp/app.zip" "$url" || fail "Tải gói cài đặt chưa được."
[ "$(shasum -a 256 "$tmp/app.zip" | cut -d' ' -f1)" = "$sha" ] || fail "Gói tải về bị lỗi (sai mã SHA-256). Hãy chạy lại."

print "Đang đặt app vào: $DEST"
mkdir -p "$DEST"
# Only app files are in the zip: an existing install keeps its media, output and settings.
unzip -oq "$tmp/app.zip" -d "$DEST"
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
chmod +x "$DEST/studio/setup-mac.command" "$DEST/Ghép Video.app/Contents/MacOS/GhepVideo" "$DEST/studio/face-detect" 2>/dev/null || true
mkdir -p "$HOME/Applications" && ln -sfn "$DEST/Ghép Video.app" "$HOME/Applications/Ghép Video.app"

zsh "$DEST/studio/setup-mac.command" "$@"
