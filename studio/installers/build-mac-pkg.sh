#!/bin/zsh
# Build the macOS installer: GhepVideo-<version>.pkg
#   zsh studio/installers/build-mac-pkg.sh <version> <app zip> <output folder>
# The .pkg puts a small "Ghép Video" app in /Applications (shows in Launchpad/Spotlight) that opens the real app in
# ~/Ghép Video, unpacks the app there, then opens Terminal to install Python, FFmpeg and the AI models.
set -eu
VERSION="$1"; ZIP="${2:A}"; OUT="${3:A}"
HERE="${0:A:h}"; ENGINE="${HERE:h}"
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
mkdir -p "$OUT" "$work/root/Applications" "$work/scripts" "$work/resources"

# 1. /Applications/Ghép Video.app: a forwarder to ~/Ghép Video, with the app icon.
# macOS tools (mkbom) expect decomposed Unicode (NFD) in bundle names with Vietnamese letters.
app="$work/root/Applications/$(python3 -c 'import unicodedata;print(unicodedata.normalize("NFD","Ghép Video.app"))' 2>/dev/null || echo "Ghép Video.app")"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$ENGINE/assets/icon.icns" "$app/Contents/Resources/AppIcon.icns"
cat > "$app/Contents/MacOS/GhepVideo" <<'SH'
#!/bin/zsh
TARGET="$HOME/Ghép Video/Ghép Video.app/Contents/MacOS/GhepVideo"
if [ ! -x "$TARGET" ]; then
  osascript -e 'display alert "Không tìm thấy Ghép Video" message "Thư mục ~/Ghép Video đã bị xoá hoặc đổi tên. Hãy chạy lại file cài đặt."'
  exit 1
fi
exec "$TARGET"
SH
chmod 755 "$app/Contents/MacOS/GhepVideo"
plutil -create xml1 "$app/Contents/Info.plist"
for kv in CFBundleExecutable=GhepVideo CFBundleIdentifier=vn.ghepvideo.launcher "CFBundleName=Ghép Video" "CFBundleDisplayName=Ghép Video" \
          CFBundlePackageType=APPL "CFBundleShortVersionString=$VERSION" "CFBundleVersion=$VERSION" CFBundleIconFile=AppIcon LSMinimumSystemVersion=12.0; do
  plutil -insert "${kv%%=*}" -string "${kv#*=}" "$app/Contents/Info.plist"
done

# 2. The app itself travels inside the scripts folder; postinstall unpacks it as the logged-in user.
cp "$ZIP" "$work/scripts/GhepVideo.zip"
cp "$HERE/mac-pkg/postinstall" "$work/scripts/postinstall"; chmod 755 "$work/scripts/postinstall"

# No extended attributes / AppleDouble "._" files in the package.
xattr -cr "$work/root" "$work/scripts" 2>/dev/null || true
export COPYFILE_DISABLE=1
pkgbuild --root "$work/root" --install-location / --scripts "$work/scripts" \
  --identifier vn.ghepvideo.pkg --version "$VERSION" "$work/component.pkg" >/dev/null

# 3. Installer window text (Vietnamese) and the wrapper package; Apple Silicon only.
cat > "$work/resources/welcome.html" <<HTML
<html><body style="font-family:-apple-system;font-size:13px">
<h2>Ghép Video $VERSION</h2>
<p>Dựng video dọc 9:16 từ ảnh, video và lời đọc. Mọi xử lý chạy trên máy của bạn.</p>
<p>Sau khi bấm <b>Cài đặt</b>, một cửa sổ Terminal sẽ mở để tải Python, FFmpeg và mô hình nghe lời đọc (khoảng 1,5 GB lần đầu, 5–15 phút tuỳ mạng). Xong sẽ tự mở app.</p>
<p>AI xem ảnh dùng gói Claude hoặc ChatGPT của bạn (qua Claude Code / Codex).</p>
<p>App và tư liệu nằm trong thư mục <b>Ghép Video</b> ở thư mục người dùng của bạn.</p>
</body></html>
HTML
cat > "$work/resources/conclusion.html" <<HTML
<html><body style="font-family:-apple-system;font-size:13px">
<h2>Đã cài xong phần app</h2>
<p>Cửa sổ Terminal đang tải phần còn lại. <b>Đừng đóng cửa sổ đó</b> cho tới khi app tự mở.</p>
<p>Về sau mở app bằng <b>Ghép Video</b> trong thư mục Ứng dụng hoặc Launchpad. Cập nhật: bấm nút <b>Phiên bản</b> ở góc trên bên phải app.</p>
</body></html>
HTML
cat > "$work/distribution.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>Ghép Video</title>
  <welcome file="welcome.html" mime-type="text/html"/>
  <conclusion file="conclusion.html" mime-type="text/html"/>
  <options customize="never" require-scripts="false" hostArchitectures="arm64"/>
  <volume-check><allowed-os-versions><os-version min="12.0"/></allowed-os-versions></volume-check>
  <choices-outline><line choice="app"/></choices-outline>
  <choice id="app" visible="false"><pkg-ref id="vn.ghepvideo.pkg"/></choice>
  <pkg-ref id="vn.ghepvideo.pkg" version="$VERSION" onConclusion="none">component.pkg</pkg-ref>
</installer-gui-script>
XML
productbuild --distribution "$work/distribution.xml" --resources "$work/resources" --package-path "$work" \
  "$OUT/GhepVideo-$VERSION.pkg" >/dev/null
echo "$OUT/GhepVideo-$VERSION.pkg"
