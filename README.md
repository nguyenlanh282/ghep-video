# Ghép Video

Ứng dụng dựng video dọc 9:16 từ ảnh/video và một file ghi âm, chạy trên **macOS (chip Apple)** và **Windows 10/11**. Mọi xử lý diễn ra trên máy: nhận dạng lời đọc, cắt khoảng lặng, phụ đề karaoke, AI xem ảnh để ghép cảnh khớp lời đọc, cân bằng âm lượng giọng.

## Cài đặt: 1 file, bấm là cài

Tải ở mục [Releases](https://github.com/nguyenlanh282/ghep-video/releases/latest):

- **Windows 10/11:** `GhepVideo-Setup-<phiên bản>.exe`
- **Mac** (chip Apple): `GhepVideo-<phiên bản>.pkg`

Bấm đúp, cài như phần mềm thường. Xong trình cài, một cửa sổ tải phần AI (~5 GB lần đầu) rồi tự mở app. Cập nhật về sau: nút **Phiên bản** ở góc trên bên phải app.

Bộ cài chưa ký số nên lần đầu: Windows → *More info → Run anyway*; Mac → *Cài đặt hệ thống → Quyền riêng tư & Bảo mật → Vẫn mở*.

Hướng dẫn đầy đủ: [studio/HUONG-DAN.md](studio/HUONG-DAN.md).

## Phát hành bản mới

```bash
python studio/updater.py 2.2.0 --notes "• Điều thay đổi" --base-url https://github.com/nguyenlanh282/ghep-video/releases/download/v2.2.0
cp "studio/installers/Cai dat Ghep Video (Mac).command" dist/Cai-dat-Ghep-Video-Mac.command
cp "studio/installers/Cai dat Ghep Video (Windows).bat" dist/Cai-dat-Ghep-Video-Windows.bat
gh release create v2.2.0 dist/GhepVideo-2.2.0.zip dist/latest.json dist/Cai-dat-Ghep-Video-*.* --title "Ghép Video 2.2.0" --notes-file -
# GitHub Actions (.github/workflows/installers.yml) then builds, tests and attaches the .exe and .pkg installers.
```
