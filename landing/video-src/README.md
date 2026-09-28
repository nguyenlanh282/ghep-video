# Video giới thiệu Ghép Video

Scripts that build the intro video on the landing page (16:9) and the TikTok cut (9:16). Media are not kept here.

1. Make neutral demo media in a work folder (`root/`: two numbered talking clips, `Video - ảnh/`, `loi doc.mp3`),
   run the app from a clean `git archive` copy with an isolated HOME, then `drive.py <work>` to analyse and export demos.
2. `node shoot.mjs <app-url> <token> <work>/shots` takes the app screenshots.
3. Narration: one Edge TTS clip per line of `lines.txt` (`vi-VN-NamMinhNeural`) into `vo/s1.mp3…`; scene lengths = max(base, voice + 1 s) in `durs.json`.
4. `python music.py <seconds> music.wav`; `ORIENT=h|v VOICE=… DURS=… python promo.py icon.png out.mp4`; `python mix.py out.mp4 final.mp4 -16`.
