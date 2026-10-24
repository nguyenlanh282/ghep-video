"""Video quảng cáo: script shape, the frame to fill in, knowledge search, segment timing (no AI, no media)."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ads, renderer

class AdsTests(unittest.TestCase):
    def test_every_kind_of_ad_has_a_frame_to_fill_in(self):
        for kind, (name, when, parts) in ads.AD_TYPES.items():
            s = ads.skeleton(kind, 30, dict(adCta='Nhắn Zalo'))
            self.assertEqual([p['vai'] for p in s['phan']], [p[0] for p in parts], name)
            self.assertEqual(len(s['hooks']), 3); self.assertEqual(s['cta']['chu'], 'Nhắn Zalo'); self.assertEqual(len(s['luu_y']), len(parts))

    def test_script_from_anywhere_becomes_well_formed(self):
        s = ads.clean(dict(kieu='la', hooks=[dict(loi=' Bón  hoài\nkhông lớn? ', chu='x' * 99), 'rác'] + [dict(loi=str(i)) for i in range(9)],
                           phan=[dict(vai='Vấn đề', loi='a'), 7], cta='rác', hashtags=['#a', '', 3]), 'liet-ke', 45)
        self.assertEqual((s['kieu'], s['giay']), ('liet-ke', 45))
        self.assertEqual(s['hooks'][0]['loi'], 'Bón hoài không lớn?'); self.assertEqual(len(s['hooks'][0]['chu']), 60); self.assertEqual(len(s['hooks']), 6)
        self.assertEqual(len(s['phan']), 1); self.assertEqual(s['cta'], dict(loi='', chu='', hinh='')); self.assertEqual(s['hashtags'], ['#a', '3'])
        self.assertEqual(ads.clean(None)['phan'], [])

    def test_versions_share_the_body_and_differ_in_the_hook(self):
        s = ads.clean(dict(hooks=[dict(loi='Hook một', chu='MỘT'), dict(loi='Hook hai', chu='HAI')], phan=[dict(vai='A', loi='thân bài', chu='ý'), dict(vai='B', loi='', chu='bỏ')],
                           cta=dict(loi='nhắn tin', chu='Nhắn ngay')))
        a, b = ads.spoken(s, 0), ads.spoken(s, 1)
        self.assertEqual([p['role'] for p in a], ['hook', 'part', 'cta']); self.assertEqual(a[1:], b[1:]); self.assertNotEqual(a[0], b[0])
        self.assertEqual(ads.title_lines('Đất chai rễ không ăn phân'), ('ĐẤT CHAI RỄ', 'không ăn phân')); self.assertEqual(ads.title_lines('Bón hoài không lớn'), ('BÓN HOÀI KHÔNG LỚN', ''))

    def test_knowledge_prefers_notes_about_the_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / '.obsidian').mkdir(); (root / 'wiki').mkdir()
            (root / 'wiki/organic-pro.md').write_text('# Organic Pro\n\nOrganic Pro cải tạo đất, tạo môi trường cho rễ mới.\n\nKhông đọc tên chất.', encoding='utf-8')
            (root / 'wiki/khac.md').write_text('Chuyện giá cả thị trường tuần này, không liên quan.', encoding='utf-8')
            (root / '.obsidian/organic-pro.md').write_text('Organic Pro ' * 50, encoding='utf-8')
            got = ads.knowledge(root, dict(adProduct='Organic Pro', adProblem='đất chai', adBenefits='cải tạo đất'))
            self.assertEqual([k['file'] for k in got], [str(Path('wiki/organic-pro.md'))]); self.assertIn('rễ mới', got[0]['text'])
            self.assertEqual(ads.knowledge(root / 'khong-co', dict(adProduct='Organic Pro')), [])
        q = ads.question(dict(adProduct='Organic Pro', adOffer='mua 3 tặng 1'), 'truoc-sau', 30, got, 'thuong')
        self.assertIn('Trước / Sau', q); self.assertIn('mua 3 tặng 1', q); self.assertIn('organic-pro.md', q); self.assertIn('108 chữ', q)

    def test_each_part_gets_its_stretch_of_the_voice(self):
        segs = [dict(role='hook', loi='a b c'), dict(role='part', loi='a b c d e f'), dict(role='cta', loi='a b c')]
        words = [dict(start=i * .5, end=i * .5 + .4, text='w') for i in range(12)]
        self.assertEqual(renderer.ad_times(segs, words, 6.0), [(0, 1.5), (1.5, 4.5), (4.5, 6.0)])            # a recording: by word count
        self.assertEqual(renderer.ad_times([dict(s, dur=d) for s, d in zip(segs, (2, 3, 1.5))], words, 6.4), [(0, 2.0), (2.0, 5.0), (5.0, 6.4)])  # synthesised: exact
        self.assertEqual(renderer.ad_times([], words, 6), [])

    def test_on_screen_line_fits_the_frame(self):
        for text, cta in (('Đất chai → rễ không ăn phân', False), ('Mua 3 chai tặng 1 PH Pro · Nhắn Zalo 0828 351 994 để kỹ sư tư vấn riêng cho vườn', True)):
            for W, S in ((720, 720), (1920, 1080)):
                self.assertLessEqual(renderer.make_super(text, W, S, cta).width, W)

    def test_lively_voice_is_asked_for_in_words_and_in_the_voice_settings(self):
        import tts, json, urllib.request
        self.assertIn('hào hứng', ads.question(dict(adProduct='X'), 'van-de', 30, [], 'soi-noi')); self.assertIn('điềm đạm', ads.question(dict(adProduct='X'), 'van-de', 30, [], 'thuong'))
        sent = []
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return json.dumps(dict(base_resp=dict(status_code=0), data=dict(audio='00ff'))).encode()
        real = urllib.request.urlopen; urllib.request.urlopen = lambda req, timeout=0: (sent.append(json.loads(req.data)), Reply())[1]
        try:
            tts.synthesize('Xin chào', dict(voice='v', model='speech-2.8-hd', speed=1.06, pitch=1, emotion='happy'), 'k')
            tts.synthesize('Xin chào', dict(voice='v', model='speech-2.8-hd', speed=1), 'k')
        finally: urllib.request.urlopen = real
        self.assertEqual((sent[0]['voice_setting']['emotion'], sent[0]['voice_setting']['pitch'], sent[0]['voice_setting']['speed']), ('happy', 1, 1.06))
        self.assertNotIn('emotion', sent[1]['voice_setting']); self.assertEqual(sent[1]['voice_setting']['pitch'], 0)

    def test_product_ad_reads_the_brief_and_the_pictures(self):
        q = ads.question(dict(adBrief='Amino chai 1 lít cho vườn sầu riêng. Cây suy kiệt sau thu hoạch.'), 'san-pham', 30, [], 'soi-noi', '- a.jpg: chai Amino trên bàn', 2)
        for want in ('BRIEF / NỘI DUNG MẪU', 'cây suy kiệt'.capitalize()[:4], 'Có 2 ảnh sản phẩm', 'chai Amino trên bàn', 'Bước 2: hook lấy từ nỗi đau', '"phan_tich"'): self.assertIn(want, q)
        self.assertNotIn('Bước 2: hook', ads.question(dict(adProduct='X'), 'van-de', 30, []))
        self.assertEqual([p['vai'] for p in ads.skeleton('san-pham', 30, {})['phan']], ['Công dụng', 'Lợi ích'])
        u = ads.clean(dict(phan_tich=dict(san_pham='AMINO PLUS – phân bón axit amin', noi_dau=['lá vàng', ''], loi_ich='không phải danh sách')))['phan_tich']
        self.assertEqual((u['noi_dau'], u['loi_ich'], u['cong_dung']), (['lá vàng'], [], []))
        self.assertEqual(ads.short_name(u['san_pham']), 'AMINO PLUS'); self.assertEqual(ads.short_name('Organic Pro (1 lít)'), 'Organic Pro')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'media'; root.mkdir()
            from PIL import Image
            for i in range(6): Image.new('RGB', (1600, 900), (40 * i, 90, 120)).save(root / f'anh {i}.jpg')
            (root / '_phan-tich.json').write_text('{"files": {"anh 0.jpg": {"mo_ta": "chai trên bàn gỗ"}}}', encoding='utf-8')
            pics, media = ads.look_at(root, Path(tmp) / 'cache')
            self.assertEqual(len(pics), 4); self.assertIn('chai trên bàn gỗ', media)
            self.assertLessEqual(max(Image.open(pics[0]).size), 768)
            self.assertEqual(ads.look_at(Path(tmp) / 'khong-co', Path(tmp)), ([], ''))

    def test_minimax_failure_reads_the_whole_ad_with_edge(self):
        import tts, os, subprocess
        from platform_tools import FFMPEG
        calls = []
        def mp3(tag):
            with tempfile.TemporaryDirectory() as t:
                f = Path(t) / 'a.mp3'; subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=d=0.5', str(f)], check=True); return f.read_bytes()
        def fail(text, job, key): calls.append(('minimax', text)); raise RuntimeError('MiniMax báo lỗi 2053 (insufficient credit)')
        def edge(text, voice, speed, pitch): calls.append(('edge', text)); return mp3('e')
        real = (tts.synthesize, tts.edge_synthesize, os.environ.get('MINIMAX_API_KEY')); tts.synthesize, tts.edge_synthesize = fail, edge; os.environ['MINIMAX_API_KEY'] = 'x'
        try:
            with tempfile.TemporaryDirectory() as tmp:
                job = dict(adVoiceSource='minimax', ttsFallback=True, minimaxVoice='v', adEnergy='soi-noi')
                parts = [dict(role='hook', loi='Một'), dict(role='part', loi='Hai'), dict(role='cta', loi='Ba')]
                ads.voice_for(parts, job, Path(tmp))
                self.assertEqual([c for c in calls if c[0] == 'edge'], [('edge', 'Một'), ('edge', 'Hai'), ('edge', 'Ba')])
                self.assertIn('2053', job['voiceNote']); self.assertEqual(job['adVoiceSource'], 'edge')
                self.assertTrue(all(p['dur'] > 0 for p in parts))
                with self.assertRaises(RuntimeError): ads.voice_for([dict(role='hook', loi='Bốn')], dict(adVoiceSource='minimax', ttsFallback=False, minimaxVoice='v'), Path(tmp))
        finally:
            tts.synthesize, tts.edge_synthesize = real[0], real[1]
            if real[2] is None: os.environ.pop('MINIMAX_API_KEY', None)
            else: os.environ['MINIMAX_API_KEY'] = real[2]

if __name__ == '__main__': unittest.main()
