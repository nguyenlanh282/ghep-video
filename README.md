# Ghép Video

Ứng dụng dựng video dọc 9:16 từ ảnh/video và một file ghi âm, chạy trên **macOS (chip Apple)** và **Windows 10/11**. Mọi xử lý diễn ra trên máy: nhận dạng lời đọc, cắt khoảng lặng, phụ đề karaoke, AI xem ảnh để ghép cảnh khớp lời đọc, cân bằng âm lượng giọng.

## Cài đặt

1. Tải `GhepVideo-<phiên bản>.zip` ở mục **Releases** và giải nén.
2. Chạy cài đặt một lần:
   - **Mac:** chuột phải `studio/setup-mac.command` → Mở.
   - **Windows:** bấm đúp `Cai dat (Windows).bat`.
3. Mở **Ghép Video.app** (Mac) hoặc biểu tượng **Ghép Video** trên Desktop (Windows).

App tự kiểm tra bản mới khi mở; bấm nút **Phiên bản** ở góc trên để cập nhật hoặc quay lại bản trước.

Hướng dẫn đầy đủ: [studio/HUONG-DAN.md](studio/HUONG-DAN.md).

## Phát hành bản mới

```bash
python studio/updater.py 2.2.0 --notes "• Điều thay đổi" --base-url https://github.com/nguyenlanh282/ghep-video/releases/download/v2.2.0
gh release create v2.2.0 dist/GhepVideo-2.2.0.zip dist/latest.json --title "Ghép Video 2.2.0" --notes-file -
```
