# Ghép Video

Ứng dụng dựng video dọc 9:16 từ ảnh/video và một file ghi âm, chạy trên **macOS (chip Apple)** và **Windows 10/11**. Mọi xử lý diễn ra trên máy: nhận dạng lời đọc, cắt khoảng lặng, phụ đề karaoke, AI xem ảnh để ghép cảnh khớp lời đọc, cân bằng âm lượng giọng.

## Cài đặt: 1 lần bấm

Tải **1 file** ở mục [Releases](https://github.com/nguyenlanh282/ghep-video/releases/latest) rồi bấm đúp:

- **Mac** (chip Apple): `Cai-dat-Ghep-Video-Mac.command`, hoặc dán vào Terminal:
  `curl -fsSL https://raw.githubusercontent.com/nguyenlanh282/ghep-video/main/studio/installers/install-mac.sh | zsh`
- **Windows 10/11**: `Cai-dat-Ghep-Video-Windows.bat`

File cài tự tải bản mới nhất, cài Python, FFmpeg, thư viện, mô hình AI, tạo biểu tượng và mở app. Cập nhật về sau: bấm nút **Phiên bản** ở góc trên bên phải app.

Hướng dẫn đầy đủ: [studio/HUONG-DAN.md](studio/HUONG-DAN.md).

## Phát hành bản mới

```bash
python studio/updater.py 2.2.0 --notes "• Điều thay đổi" --base-url https://github.com/nguyenlanh282/ghep-video/releases/download/v2.2.0
cp "studio/installers/Cai dat Ghep Video (Mac).command" dist/Cai-dat-Ghep-Video-Mac.command
cp "studio/installers/Cai dat Ghep Video (Windows).bat" dist/Cai-dat-Ghep-Video-Windows.bat
gh release create v2.2.0 dist/GhepVideo-2.2.0.zip dist/latest.json dist/Cai-dat-Ghep-Video-*.* --title "Ghép Video 2.2.0" --notes-file -
```
