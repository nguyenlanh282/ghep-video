import json, sys, time, urllib.request
from pathlib import Path
P = Path(sys.argv[1]); R = P / 'root'
url = (P / 'serve.log').read_text().split()[0]; base = url.split('/?')[0]; tok = url.split('t=')[1]
def api(n, b=None):
    q = urllib.request.Request(f'{base}/api/{n}', data=json.dumps(b or {}).encode(), headers={'X-Token': tok, 'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(q, timeout=120).read())
def wait():
    while True:
        st = api('state')
        if not st['job']['running']: return st
        time.sleep(1)
looks = {l['id']: l['grade'] for l in api('state')['grade']['looks']}
api('set', {'values': dict(talkVideos=json.dumps([str(R / '1 - mo dau.mp4'), str(R / '2 - noi dung.mp4')]), talkAspects='9:16,16:9', talkShorts=True, talkBroll=False, music='',
                            titleStyle='box', titleEffect='pulse', titleScale=1.2, subScale=1.15, subFont='arial', grade=json.dumps(dict(looks['tuoi-sang'], look='tuoi-sang')))})
api('start', {'task': 'talk-analyze'}); st = wait(); print('analyze', st['job']['status'], st['job']['error'])
pf = Path(api('talkState')['project'] and next((P / 'root/output/.studio-cache/talk').glob('*/project.json')))
d = json.loads(pf.read_text()); t = [w['text'] for w in d['words']]; print(' '.join(t))
for w in d['words']:
    if w['text'] == 'IM': w['text'] = 'im'
d['titles'] = [dict(dong1='LÀM VIDEO THẬT NHANH', dong2='Quay 1 lần, phần mềm lo phần còn lại'), dict(dong1='TỰ CẮT · TỰ PHỤ ĐỀ', dong2='Không cần biết dựng phim'), dict(dong1='VIDEO XỊN TRONG 1 PHÚT', dong2='Bí quyết cho người bận rộn')]
d['title_choice'] = d['titles'][0]
d['caption'] = 'Quay một lần, phần mềm tự cắt chỗ im lặng, tự làm phụ đề và thêm tiêu đề nổi bật. Bạn chỉ việc đăng!'
d['hashtags'] = ['#ghepvideo', '#lamvideo', '#tiktoktips', '#reels', '#edittips']; d['keywords'] = ['phụ đề', 'tiêu đề', 'im lặng']
a = next(i for i, x in enumerate(t) if x.startswith('Bạn')); b = len(t) - 1
d['shorts'] = [dict(first=a, last=b, title='Quay 1 lần là xong', reason='Câu chốt lợi ích rõ ràng, đứng riêng vẫn hiểu', on=True)]
pf.write_text(json.dumps(d, ensure_ascii=False))
api('start', {'task': 'talk-render'}); st = wait(); print('talk render', st['job']['status'], st['job']['error'])
api('set', {'values': dict(audio=str(R / 'loi doc.mp3'), title='MỖI SÁNG 10 PHÚT', subtitle='Thói quen nhỏ, hiệu quả lớn', titleStyle='pop', titleEffect='bounce', subStyle='sweep', fixesText='',
                            matchScenes=False, grade=json.dumps(dict(looks['am-ap'], look='am-ap')))})
api('start', {'task': 'render'}); st = wait(); print('story render', st['job']['status'], st['job']['error'], st['job']['result'])
# for the screenshots: the MiniMax voice panel filled with a sample (no key stored)
api('set', {'values': dict(voiceSource='minimax', ttsText='Mỗi sáng, mình đều dành mười phút để lên kế hoạch cho cả ngày. Việc nhỏ thôi, nhưng giúp mình bình tĩnh và làm được nhiều hơn.',
                            minimaxVoice='moss_audio_giong-cua-ban', grade=json.dumps(dict(looks['dien-anh'], look='dien-anh')))})
print('ok')
