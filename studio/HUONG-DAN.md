# Ghép Video — chạy trên Mac và Windows

## Cài đặt (một lần)

**macOS** (chip Apple M1 trở lên, macOS 12+):
1. Bấm đúp `studio/setup-mac.command`. Script cài FFmpeg/Python nếu thiếu (qua Homebrew), thư viện, và tải mô hình AI (~4,5 GB lần đầu).
2. Mở **Ghép Video.app** ở thư mục gốc.

**Windows** (10/11 64-bit, RAM ≥16 GB; nên có card NVIDIA ≥8 GB VRAM, không có vẫn chạy nhưng chậm hơn):
1. Chép cả thư mục dự án sang máy Windows.
2. Bấm đúp `Cai dat (Windows).bat`. Script dùng winget cài Python 3.12, FFmpeg, Ollama; cài thư viện; tải mô hình nghe lời đọc (~1,5 GB), mô hình xem ảnh `qwen3-vl:4b` qua Ollama (~3,3 GB) và bộ nhận diện khuôn mặt; tạo biểu tượng **Ghép Video** trên Desktop.
3. Mở app bằng biểu tượng trên Desktop hoặc `Ghep Video (Windows).bat`. Ollama phải đang chạy (nó tự chạy nền sau khi cài).

Cài đặt lưu ở `~/Library/Application Support/GhepVideo/` (Mac) hoặc `%APPDATA%\GhepVideo\` (Windows): môi trường Python, mô hình, `settings.json` (lựa chọn lần trước, key Pexels/Pixabay) và `app.log`.

## Mang sang máy khác

1. Lấy file `GhepVideo-<phiên bản>.zip` (xem “Phát hành bản mới” bên dưới) rồi chép sang máy mới, hoặc gửi qua Zalo/Drive/USB. File zip chỉ chứa app (~5 MB): không có tư liệu, video, cài đặt hay API key của máy cũ.
2. Giải nén vào nơi bạn muốn (vd `Tài liệu/Ghép Video`).
3. Chạy cài đặt một lần:
   - **Mac:** bấm chuột phải vào `studio/setup-mac.command` → **Mở** → **Mở** (lần đầu macOS cảnh báo file tải từ mạng; script tự gỡ cảnh báo cho cả thư mục app).
   - **Windows:** bấm đúp `Cai dat (Windows).bat`. Nếu hiện “Windows protected your PC”, bấm **More info → Run anyway**.
4. Mở app. Thư mục `Video - ảnh` và `output` tự được tạo trong thư mục app. Dán lại API key Pixabay/Pexels trên máy mới (key không đi theo file zip).

## Cập nhật

- Bấm nút **Phiên bản …** ở góc trên bên phải. Lần đầu, mở “Địa chỉ cập nhật” và dán link `latest.json` được cung cấp, rồi bấm **Lưu địa chỉ**. App tự kiểm tra mỗi lần mở; khi có bản mới, nút chuyển màu xanh và ghi “có bản mới”.
- **Cập nhật lên …**: app tải gói, kiểm tra mã SHA-256, sao lưu bản đang dùng, chỉ thay file của app (tư liệu, video đã xuất, cài đặt, key giữ nguyên), cài thêm thư viện nếu bản mới cần, rồi mời **Khởi động lại app**.
- Gói tải về bị lỗi hoặc chứa file ngoài phạm vi app thì bị từ chối và app giữ nguyên bản cũ.
- **↩ Quay lại bản trước**: dùng bản sao lưu gần nhất (giữ 3 bản gần nhất trong thư mục cài đặt, mục `backups/`).

## Phát hành bản mới (cho người quản lý app)

1. Sửa code trong `studio/`, chạy kiểm thử: `python -m unittest test_renderer test_updater`.
2. Tạo gói: `python studio/updater.py 2.2.0 --notes "• Điều thay đổi 1\n• Điều thay đổi 2" --base-url https://<nơi-để-file>/`
   → tạo `dist/GhepVideo-2.2.0.zip` và `dist/latest.json` (có số phiên bản, link, mã SHA-256, ghi chú).
3. Tải **cả hai file** lên nơi lưu trữ (link phải tải trực tiếp được qua https). Máy nào đã dán link `latest.json` sẽ thấy bản mới.
4. Số phiên bản dạng `2.2.0`: sửa nhỏ tăng số cuối, thêm tính năng tăng số giữa.

## Sử dụng

1. Chọn thư mục có ảnh và video (đọc các file ngay trong thư mục, không quét thư mục con).
2. Bấm **Phân tích & đặt tên** (lần đầu, hoặc khi thêm file mới). AI chạy trên máy xem từng ảnh, tách video thành các đoạn cảnh và mô tả từng đoạn, đổi tên file theo nội dung (vd `Gia đình ăn cơm cùng nhau.mp4`) và ghi chú vào `_ghi-chu-tu-lieu.md` trong thư mục tư liệu. Tên gốc được lưu lại; nút **Trả lại tên gốc** trong Danh sách tư liệu sẽ khôi phục.
3. Chọn file ghi âm. Chỉnh **Âm lượng giọng đọc** (50–300%, nút − / +). **Tự cân bằng giọng đọc** (mặc định bật) đưa giọng về −14 LUFS, mức chuẩn mạng xã hội; file ghi âm mẫu gốc chỉ −40 LUFS nên trước đây nghe rất nhỏ. Có bộ chặn đỉnh −1 dB để không rè.
4. Chọn nhạc nền nếu cần; nghe nhạc riêng hoặc nghe cùng lời đọc. Thanh âm lượng chỉ thay đổi nhạc nền, không làm nhỏ lời đọc.
5. Chỉnh hai dòng tiêu đề, chọn mẫu tiêu đề và kiểu phụ đề độc lập. Nếu máy nghe sai chữ nào, ghi vào ô **Sửa chữ nhận dạng sai** (mỗi dòng `chữ sai => chữ đúng`); lần xuất sau sẽ dùng chữ đúng.
6. Chọn thư mục lưu, độ phân giải (mặc định **1080p**) và nhịp đổi cảnh 1,5–5 giây (kéo thanh trượt hoặc bấm − / +).
7. Bấm **Dựng thử 20 giây** để kiểm tra lựa chọn, hoặc **Xuất toàn bộ video**.

Kết quả gồm MP4, phụ đề SRT và JSON lưu lựa chọn của lần dựng. Tên file có thời gian và mã riêng, không ghi đè tư liệu gốc. Có nút dừng khi đang xuất.

## Ghi chú

- Khung xem mẫu chữ sử dụng tư liệu mẫu đi kèm. Nút Dựng thử tạo video thật từ những file đang chọn.
- **Ghép cảnh khớp lời đọc** (bật khi đã phân tích): mỗi câu đọc được gắn các đoạn cảnh có nội dung phù hợp nhất; cảnh đổi đúng lúc sang câu mới. Một câu dài đi qua nhiều cảnh; một file không chạy quá 2 cảnh liên tiếp khi còn cảnh khác phù hợp. Kế hoạch ghép từng cảnh được lưu trong file JSON cạnh video (`scenePlan`). Chưa phân tích thì bộ dựng luân phiên ảnh/video như cũ.
- **Tìm ảnh miễn phí cho câu chưa có cảnh hợp** (công tắc, mặc định tắt): AI kiểm tra từng câu xem cảnh tốt nhất có thật sự hợp không; câu chưa hợp được tìm ảnh bằng 2 cụm từ tiếng Anh, AI xem lại và chỉ giữ ảnh đúng ý (loại ảnh cũ, đen trắng, người nổi tiếng, có chữ/logo). Không có ảnh đạt thì giữ cảnh của bạn. Nguồn:
  - **Pixabay**: ảnh và video miễn phí (Pixabay Content License, không bắt buộc ghi nguồn), cần API key miễn phí tại pixabay.com/api/docs sau khi đăng ký tài khoản.
  - **Openverse**: ảnh CC0/public domain, không cần key, nhưng kho ảnh đời thường ít.
  - **Pexels**: ảnh và video dọc chất lượng cao, cần API key miễn phí (pexels.com/api). Key Pexels/Pixabay lưu trong app, chỉ truyền qua biến môi trường, không ghi vào file JSON.
  - Chưa dán key cho nguồn đã chọn thì app tự dùng Openverse.
  - Pinterest không hỗ trợ: ảnh trên đó thuộc bản quyền của nhiều người đăng, không phải kho miễn phí, và Pinterest không cho tải tự động.
  - Nguồn ảnh đã dùng ghi trong file `.nguon-anh.txt` cạnh video. Ảnh tải về lưu ở `output/.studio-cache/stock/`.
- Bộ phân tích dùng mô hình Qwen3-VL 4B chạy trên máy (Mac: MLX; Windows: Ollama). Trên Mac M1 Pro khoảng 2 phút cho 8 file; file đã phân tích được nhớ, lần sau chỉ xem file mới.
- Lời đọc được nhận dạng bằng mô hình tiếng nói chạy trên máy; tên riêng và từ khó nên thêm vào ô Sửa chữ nhận dạng sai (sửa cả chữ in trên video lẫn SRT). Sửa tay file SRT thì không cập nhật chữ đã in vào MP4.
- Phụ đề karaoke: mỗi câu hiện trọn trên một hàng cố định, chữ không di chuyển, chỉ chữ đang đọc đổi màu. Câu kết thúc ở dấu câu; câu dài được chia đều thành các dòng gần bằng nhau. Câu cũ giữ lại đến khi câu mới bắt đầu (tối đa 1,5 giây) để không bị nháy.
- Nhạc nền ngắn được lặp trong video xuất. Mặc định ảnh/video phủ kín khung dọc. Ảnh và video được nhận diện khuôn mặt để chọn vùng cắt. Ảnh không giữ được tất cả khuôn mặt sẽ bị bỏ qua; video ngang không giữ được mặt thì dùng nền mờ cho cảnh đó (kiểm tra mặt ở giữa mỗi cảnh). Tắt “Ảnh đầy khung, giữ trọn mặt” để trở lại chế độ nền mờ.
- Thư mục dự án là thư mục chứa `Ghép Video.app` / `Ghep Video (Windows).bat`, nên có thể sao chép hay đổi tên cả thư mục. Đường dẫn đã chọn không còn tồn tại thì app tự quay về thư mục mặc định của dự án.
- Nhạc nền chưa được cung cấp sẵn; chọn file nhạc của bạn.
- Dữ liệu được xử lý tại máy. Chỉ khi bật Tìm ảnh miễn phí, app mới gửi từ khoá tìm kiếm tiếng Anh tới nguồn ảnh đã chọn và tải ảnh về.

## Mã nguồn

- `app/main.py`: app chạy trên cả hai hệ. Mở cửa sổ (pywebview) và phục vụ giao diện qua máy chủ nội bộ `127.0.0.1` có mã bảo vệ; chạy dựng/phân tích thành tiến trình riêng. `python main.py --browser` mở giao diện trong trình duyệt (dùng khi cửa sổ app lỗi).
- `app/ui/`: giao diện HTML/CSS/JS (`index.html`, `style.css`, `app.js`) và video mẫu trong `assets/`.
- `platform_tools.py`: mọi phần khác nhau giữa Mac và Windows: FFmpeg, font, nhận dạng lời (mlx-whisper / faster-whisper), nhận diện mặt (Apple Vision / OpenCV YuNet), mô hình xem ảnh (MLX / Ollama).
- `renderer.py`: dựng video, vẽ karaoke, trộn âm thanh, dựng theo kế hoạch cảnh.
- `analyzer.py`: phân tích ảnh/video, đổi tên, ghi chú, chọn cảnh cho từng câu, tìm ảnh miễn phí.
- `FaceDetect.swift` → `face-detect`: bộ nhận diện mặt Apple Vision (Mac).
- `setup-mac.command`, `setup-windows.ps1`, `requirements-*.txt`: cài đặt.
- `updater.py`: tạo gói phát hành, kiểm tra và cài bản mới, sao lưu / quay lại bản trước. `VERSION`: số phiên bản; `update.json`: link `latest.json` mặc định cho các máy mới.
- `test_renderer.py`, `test_updater.py`: kiểm thử (`python -m unittest test_renderer test_updater`).
- Bản cũ chỉ chạy trên Mac: `Ghép Video (bản cũ).app`, mã `VideoStudio.swift`, biên dịch bằng `build.command`. Giữ lại để dự phòng; bản mới đã có đủ chức năng.

## Cắt khoảng im lặng

Mặc định bật: bỏ các đoạn yên lặng từ 0,35 giây, giữ đệm trước/sau lời nói để không cắt sát âm tiết. Phụ đề karaoke được đổi sang thời gian mới sau khi cắt; nhạc nền được trộn sau bước này. File ghi âm gốc không thay đổi. Có thể tắt trong giao diện.
