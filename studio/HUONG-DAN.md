# Ghép Video — chạy trên Mac và Windows

## Cài đặt: 1 file, bấm là cài

Vào **github.com/nguyenlanh282/ghep-video/releases/latest**, tải **1 file** hợp với máy rồi bấm đúp:

- **Windows 10/11:** `GhepVideo-Setup-<phiên bản>.exe` → Next → Install → Finish. Không cần quyền quản trị.
  - Nếu hiện “Windows protected your PC”: **More info → Run anyway** (vì bộ cài chưa ký số).
- **Mac** (chip Apple M1 trở lên): `GhepVideo-<phiên bản>.pkg` → Tiếp tục → Cài đặt.
  - Nếu macOS báo không mở được: **Cài đặt hệ thống → Quyền riêng tư & Bảo mật → Vẫn mở** (vì bộ cài chưa ký số).

Sau khi trình cài xong, một cửa sổ tự mở để tải Python, FFmpeg và mô hình nghe lời đọc (~1,5–2 GB lần đầu, 5–15 phút tuỳ mạng). **Đừng đóng cửa sổ đó**; xong sẽ tự mở app.

Mở app về sau: **Ghép Video** trên Desktop / Start menu (Windows) hoặc trong thư mục Ứng dụng / Launchpad (Mac). Tư liệu để trong `Ghép Video/Video - ảnh` (thư mục người dùng), video xuất ở `Ghép Video/output`.

Gỡ cài đặt: Windows → Settings → Apps → Ghép Video → Uninstall (giữ lại tư liệu và video). Mac → xoá “Ghép Video” trong Ứng dụng và thư mục `~/Ghép Video/studio`.

Cách khác không cần trình cài: file `Cai-dat-Ghep-Video-Mac.command` / `Cai-dat-Ghep-Video-Windows.bat`, hoặc trên Mac dán vào Terminal:
`curl -fsSL https://raw.githubusercontent.com/nguyenlanh282/ghep-video/main/studio/installers/install-mac.sh | zsh`

Cài đặt lưu ở `~/Library/Application Support/GhepVideo/` (Mac) hoặc `%APPDATA%\GhepVideo\` (Windows): Python, FFmpeg, `settings.json` (lựa chọn, key Pexels/Pixabay), `app.log`, bản sao lưu.

## Mang sang máy khác

Trên máy mới chỉ cần làm như mục **Cài đặt: 1 file, bấm là cài**. Tư liệu, video và key của máy cũ không đi theo; chép tư liệu sang thư mục `Ghép Video/Video - ảnh` của máy mới, rồi dán lại key Pexels/Pixabay trong app.

## Cập nhật

- Nút **Phiên bản …** ở **góc trên bên phải** app. App tự kiểm tra mỗi lần mở (nguồn cập nhật có sẵn, không cần điền gì); khi có bản mới, nút chuyển **màu xanh** và ghi “có bản mới”.
- **Cập nhật lên …**: app tải gói, kiểm tra mã SHA-256, sao lưu bản đang dùng, chỉ thay file của app (tư liệu, video đã xuất, cài đặt, key giữ nguyên), cài thêm thư viện nếu bản mới cần, rồi mời **Khởi động lại app**.
- Gói tải về bị lỗi hoặc chứa file ngoài phạm vi app thì bị từ chối và app giữ nguyên bản cũ.
- **↩ Quay lại bản trước**: dùng bản sao lưu gần nhất (giữ 3 bản gần nhất trong thư mục cài đặt, mục `backups/`).

## Phát hành bản mới (cho người quản lý app)

1. Sửa code trong `studio/`, chạy kiểm thử: `python -m unittest test_renderer test_updater`.
2. Tạo gói: `python studio/updater.py 2.2.0 --notes "• Điều thay đổi 1\n• Điều thay đổi 2" --base-url https://<nơi-để-file>/`
   → tạo `dist/GhepVideo-2.2.0.zip` và `dist/latest.json` (có số phiên bản, link, mã SHA-256, ghi chú).
3. Đăng lên GitHub (lệnh trong `README.md`). GitHub Actions tự đóng gói `.exe` + `.pkg`, cài thử trên Windows/Mac thật, chạy bài thử dựng video, rồi gắn 2 bộ cài vào bản phát hành (~40–60 phút). Mọi máy đang dùng app sẽ thấy nút cập nhật chuyển xanh.
4. Số phiên bản dạng `2.2.0`: sửa nhỏ tăng số cuối, thêm tính năng tăng số giữa.

## Sử dụng

1. Chọn thư mục có ảnh và video (đọc các file ngay trong thư mục, không quét thư mục con).
2. Bấm **Phân tích & đặt tên** (lần đầu, hoặc khi thêm file mới). AI chạy trên máy xem từng ảnh, tách video thành các đoạn cảnh và mô tả từng đoạn, đổi tên file theo nội dung (vd `Gia đình ăn cơm cùng nhau.mp4`) và ghi chú vào `_ghi-chu-tu-lieu.md` trong thư mục tư liệu. Tên gốc được lưu lại; nút **Trả lại tên gốc** trong Danh sách tư liệu sẽ khôi phục.
3. Chọn file ghi âm. Chỉnh **Âm lượng giọng đọc** (50–300%, nút − / +). **Tự cân bằng giọng đọc** (mặc định bật) đưa giọng về −14 LUFS, mức chuẩn mạng xã hội; file ghi âm mẫu gốc chỉ −40 LUFS nên trước đây nghe rất nhỏ. Có bộ chặn đỉnh −1 dB để không rè.
4. Chọn nhạc nền nếu cần; nghe nhạc riêng hoặc nghe cùng lời đọc. Thanh âm lượng chỉ thay đổi nhạc nền, không làm nhỏ lời đọc.
5. Chỉnh hai dòng tiêu đề, chọn mẫu tiêu đề và kiểu phụ đề độc lập. Nếu máy nghe sai chữ nào, ghi vào ô **Sửa chữ nhận dạng sai** (mỗi dòng `chữ sai => chữ đúng`); lần xuất sau sẽ dùng chữ đúng.
6. Chọn thư mục lưu, độ phân giải (mặc định **1080p**) và nhịp đổi cảnh 1,5–5 giây (kéo thanh trượt hoặc bấm − / +).
7. Bấm **Dựng thử 20 giây** để kiểm tra lựa chọn, hoặc **Xuất toàn bộ video**.

8. **Ảnh bìa** (mục 06, dưới khung xem trước): bấm **Tìm hình rõ mặt**. App lấy khung hình từ chính các cảnh video vừa xuất (hình gốc, không dính phụ đề) và chấm điểm: có mặt, mặt to, nét, đủ sáng, không nghiêng, vừa khung 9:16 (hình có mặt sát mép được ghi “Mặt sát mép”). Bấm để chọn 1–3 hình (số trên hình là thứ tự; 1 hình tràn khung, 2 hình trên/dưới, 3 hình 1 trên 2 dưới). Bấm hình đã chọn để bỏ; đã đủ 3 mà bấm hình khác thì hình số 3 được thay. **Tải ảnh lên** để dùng ảnh riêng. Bật/tắt chữ tiêu đề, rồi **Lưu ảnh bìa**: file `…-anh-bia.jpg` (1080×1920) lưu cạnh video.

Kết quả gồm MP4, phụ đề SRT và JSON lưu lựa chọn của lần dựng. Tên file có thời gian và mã riêng, không ghi đè tư liệu gốc. Có nút dừng khi đang xuất.

## Video chia sẻ (tab ở đầu app)

Biến 1 video thô quay người nói (chưa cắt, có ậm ừ, im lặng, nói vấp, nói lại) thành video hoàn thiện.

1. **Chọn video thô** → bấm **✨ Phân tích video**. App ghi lại lời nói rồi:
   - tự đánh dấu cắt: im lặng/ngắt quãng, “ờ, ừm, à”, nói vấp (“thứ ba thứ ba”), câu nói hỏng rồi nói lại (AI tìm, app kiểm tra lại: chỉ cắt khi câu sau lặp lại nội dung hoặc có “à không / nói lại”);
   - AI (Claude/ChatGPT) soát chính tả phụ đề, gợi ý 3 tiêu đề, viết caption + hashtag, chọn từ khoá, gợi ý clip ngắn 20–90 giây, chọn cảnh trám từ **kho trám** (thư mục đã Phân tích) và/hoặc trên mạng.
2. **Sửa bằng chữ** (cột giữa): chữ bị gạch là chỗ sẽ cắt, màu theo lý do. Bấm chữ để nghe đoạn đó; bấm chữ bị gạch để khôi phục; bôi đen rồi **Delete** (hoặc ✂) để cắt thêm. 🎬 là cảnh trám: bấm để bật/tắt. Chọn tiêu đề, sửa caption/hashtag/từ khoá, chọn clip ngắn. Mọi sửa đổi tự lưu.
3. **Xem trước** (cột phải) phát bản thô và nhảy qua các chỗ cắt, để nghe câu có liền mạch không.
4. **Xuất video**: chọn tỉ lệ 9:16 / 1:1 / 16:9; zoom nhẹ ở vết cắt, khử ồn, tô màu từ khoá, xuất thêm clip ngắn. Kết quả nằm trong thư mục `<tên video> - hoàn thiện <thời gian>` (trong thư mục lưu): các MP4, phụ đề SRT, `caption-hashtag.txt`.

Ghi chú: video quay dọc khi xuất 16:9 giữ trọn người nói ở giữa trên nền mờ. Không có Claude/ChatGPT vẫn cắt và làm phụ đề được, nhưng không có soát chính tả, tiêu đề gợi ý, cảnh trám, clip ngắn.

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
- **AI xem ảnh** (mục 01, “AI xem ảnh”) dùng gói của bạn: **Tự động** (Claude nếu có, không thì ChatGPT) · **Claude** · **ChatGPT**.
  - **Claude**: gói Claude Pro/Max qua **Claude Code** (cài theo code.claude.com/docs/en/setup, gõ `claude` và đăng nhập 1 lần). App gọi bản Sonnet.
  - **ChatGPT**: gói ChatGPT qua **Codex** (developers.openai.com/codex/cli, rồi `codex login`).
  - Ảnh thu nhỏ (768 px) được gửi lên Anthropic/OpenAI và tính vào hạn mức gói; mỗi ảnh/đoạn cảnh khoảng 10 giây.
  - Không có gói nào: vẫn dựng video, phụ đề, giọng đọc, ảnh bìa bình thường; chỉ phần đặt tên và ghép cảnh theo nội dung ảnh không chạy.
- Lời đọc được nhận dạng bằng mô hình tiếng nói chạy trên máy; tên riêng và từ khó nên thêm vào ô Sửa chữ nhận dạng sai (sửa cả chữ in trên video lẫn SRT). Sửa tay file SRT thì không cập nhật chữ đã in vào MP4.
- Phụ đề karaoke: mỗi câu hiện trọn trên một hàng cố định, chữ không di chuyển, chỉ chữ đang đọc đổi màu. Câu kết thúc ở dấu câu; câu dài được chia đều thành các dòng gần bằng nhau. Câu cũ giữ lại đến khi câu mới bắt đầu (tối đa 1,5 giây) để không bị nháy.
- Nhạc nền ngắn được lặp trong video xuất. Mặc định ảnh/video phủ kín khung dọc. Ảnh và video được nhận diện khuôn mặt để chọn vùng cắt. Ảnh không giữ được tất cả khuôn mặt sẽ bị bỏ qua; video ngang không giữ được mặt thì dùng nền mờ cho cảnh đó (kiểm tra mặt ở giữa mỗi cảnh). Tắt “Ảnh đầy khung, giữ trọn mặt” để trở lại chế độ nền mờ.
- Thư mục dự án là thư mục chứa `Ghép Video.app` / `Ghep Video (Windows).bat`, nên có thể sao chép hay đổi tên cả thư mục. Đường dẫn đã chọn không còn tồn tại thì app tự quay về thư mục mặc định của dự án.
- Nhạc nền chưa được cung cấp sẵn; chọn file nhạc của bạn.
- Dữ liệu được xử lý tại máy. Chỉ khi bật Tìm ảnh miễn phí, app mới gửi từ khoá tìm kiếm tiếng Anh tới nguồn ảnh đã chọn và tải ảnh về.

## Mã nguồn

- `app/main.py`: app chạy trên cả hai hệ. Mở cửa sổ (pywebview) và phục vụ giao diện qua máy chủ nội bộ `127.0.0.1` có mã bảo vệ; chạy dựng/phân tích thành tiến trình riêng. `python main.py --browser` mở giao diện trong trình duyệt (dùng khi cửa sổ app lỗi).
- `app/ui/`: giao diện HTML/CSS/JS (`index.html`, `style.css`, `app.js`) và video mẫu trong `assets/`.
- `platform_tools.py`: mọi phần khác nhau giữa Mac và Windows: FFmpeg, font, nhận dạng lời (mlx-whisper / faster-whisper), nhận diện mặt (Apple Vision / OpenCV YuNet), AI xem ảnh qua Claude Code / Codex (gói của khách).
- `renderer.py`: dựng video, vẽ karaoke, trộn âm thanh, dựng theo kế hoạch cảnh.
- `analyzer.py`: phân tích ảnh/video, đổi tên, ghi chú, chọn cảnh cho từng câu, tìm ảnh miễn phí.
- `FaceDetect.swift` → `face-detect`: bộ nhận diện mặt Apple Vision (Mac).
- `setup-mac.command`, `setup-windows.ps1`, `requirements-*.txt`: cài đặt.
- `talk.py`: Video chia sẻ (phân tích, cắt, xuất nhiều tỉ lệ và clip ngắn); giao diện `app/ui/talk.html` + `talk.js`.
- `thumbnail.py`: tìm khung hình làm ảnh bìa và ghép 1–3 hình kèm tiêu đề.
- `updater.py`: tạo gói phát hành, kiểm tra và cài bản mới, sao lưu / quay lại bản trước. `VERSION`: số phiên bản; `update.json`: link `latest.json` mặc định cho các máy mới.
- `installers/`: bộ cài 1 file (`ghepvideo.iss` → .exe, `build-mac-pkg.sh` → .pkg, và bản script `.command`/`.bat`); `assets/`: biểu tượng app; `smoke_test.py`: bài thử dựng video + AI trên máy vừa cài; `.github/workflows/installers.yml`: quy trình đóng gói và thử tự động.
- `test_renderer.py`, `test_updater.py`, `test_thumbnail.py`, `test_ai.py`, `test_talk.py`: kiểm thử (`python -m unittest test_renderer test_updater test_thumbnail`).
- Bản cũ chỉ chạy trên Mac: `Ghép Video (bản cũ).app`, mã `VideoStudio.swift`, biên dịch bằng `build.command`. Giữ lại để dự phòng; bản mới đã có đủ chức năng.

## Cắt khoảng im lặng

Mặc định bật: bỏ các đoạn yên lặng từ 0,35 giây, giữ đệm trước/sau lời nói để không cắt sát âm tiết. Phụ đề karaoke được đổi sang thời gian mới sau khi cắt; nhạc nền được trộn sau bước này. File ghi âm gốc không thay đổi. Có thể tắt trong giao diện.
