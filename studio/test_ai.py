"""Picture-AI providers with stand-in Claude Code / Codex CLIs (no account, no network needed)."""
import json, os, stat, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import platform_tools as pt

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]; prompt = sys.stdin.read()
open(sys.argv[0] + '.log', 'w').write(json.dumps({'args': args, 'prompt': prompt}))
if 'LOGGED_OUT' in prompt: sys.stderr.write('Invalid API key · Please run /login'); sys.exit(1)
print(json.dumps({'type': 'result', 'is_error': False, 'result': '```json\n{"mo_ta": "Ảnh thử từ Claude"}\n```'}))
'''
FAKE_CODEX = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]; prompt = sys.stdin.read()
open(sys.argv[0] + '.log', 'w').write(json.dumps({'args': args, 'prompt': prompt}))
out = args[args.index('-o') + 1]
open(out, 'w', encoding='utf-8').write('{"mo_ta": "Ảnh thử từ ChatGPT"}')
'''

@unittest.skipIf(os.name == 'nt', 'stand-in CLIs are POSIX scripts')
class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name, body in (('claude', FAKE_CLAUDE), ('codex', FAKE_CODEX)):
            f = self.tmp / name; f.write_text(body); f.chmod(f.stat().st_mode | stat.S_IEXEC)
        self.img = self.tmp / 'ảnh thử.jpg'; self.img.write_bytes(b'\xff\xd8\xff')
        self.env = dict(os.environ)
        os.environ['PATH'] = f'{self.tmp}{os.pathsep}{os.environ["PATH"]}'
        self.orig_local = pt.local_ai_available

    def tearDown(self):
        os.environ.clear(); os.environ.update(self.env); pt.local_ai_available = self.orig_local

    def log(self, name): return json.loads((self.tmp / f'{name}.log').read_text())

    def test_claude_gets_prompt_on_stdin_and_image_path(self):
        os.environ['GHEPVIDEO_AI'] = 'claude'
        answer = pt.vlm_ask('Mô tả "hình" này\ncó xuống dòng', [self.img])
        self.assertIn('Ảnh thử từ Claude', answer)
        call = self.log('claude')
        self.assertIn('-p', call['args']); self.assertIn('Read', call['args'])
        self.assertIn(str(self.img.resolve().parent), call['args'], 'image folder is allowed with --add-dir')
        self.assertIn(str(self.img.resolve()), call['prompt']); self.assertIn('"hình"', call['prompt'])

    def test_codex_gets_images_and_reads_answer_file(self):
        os.environ['GHEPVIDEO_AI'] = 'codex'
        self.assertIn('Ảnh thử từ ChatGPT', pt.vlm_ask('Mô tả', [self.img, self.img]))
        args = self.log('codex')['args']
        self.assertEqual(args[:2], ['exec', '--skip-git-repo-check'])
        self.assertLess(args.index('-'), args.index('--image'), 'prompt marker comes before the image list')
        self.assertEqual(args.count(str(self.img.resolve())), 2)

    def test_signed_out_account_gives_a_clear_message(self):
        os.environ['GHEPVIDEO_AI'] = 'claude'
        with self.assertRaises(RuntimeError) as err: pt.vlm_ask('LOGGED_OUT', [self.img])
        self.assertIn('chưa đăng nhập', str(err.exception))

    def test_auto_prefers_local_then_claude_then_codex(self):
        os.environ['GHEPVIDEO_AI'] = 'auto'
        pt.local_ai_available = lambda: True; self.assertEqual(pt.ai_provider(), 'local')
        pt.local_ai_available = lambda: False; self.assertEqual(pt.ai_provider(), 'claude')
        (self.tmp / 'claude').unlink()
        real = pt.cli_path
        try:
            pt.cli_path = lambda n: None if n == 'claude' else real(n)
            self.assertEqual(pt.ai_provider(), 'codex')
            pt.cli_path = lambda n: None
            self.assertIsNone(pt.ai_provider())
            with self.assertRaises(RuntimeError) as err: pt.vlm_ready()
            self.assertIn('Claude Code hoặc Codex', str(err.exception))
        finally: pt.cli_path = real

if __name__ == '__main__': unittest.main()
