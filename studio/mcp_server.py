"""MCP server for Ghép Video: lets Claude (Claude Code, Claude Desktop…) drive the app that is open on this computer.

  claude mcp add ghep-video -- <python> <this file>

It speaks MCP over stdio (JSON-RPC, one message per line) and talks to the running app through the app's own local
API (address and token from app-dang-mo.json, written by the app at every start). No API key ever passes through
here: the app never hands them out, and the settings tool cannot write them.
"""
import json, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_tools import DATA

APP_FILE = DATA / 'app-dang-mo.json'
PROTOCOL = '2025-06-18'
NOT_OPEN = 'App Ghép Video chưa mở trên máy này. Hãy mở app (biểu tượng Ghép Video) rồi thử lại.'
SECRET = ('minimaxKey', 'pexelsKey', 'pixabayKey', 'updateManifest')

class AppError(Exception): pass

def api(name, body=None, timeout=120):
    try: info = json.loads(APP_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError): raise AppError(NOT_OPEN)
    req = urllib.request.Request(f'http://127.0.0.1:{info["port"]}/api/{name}', data=json.dumps(body or {}).encode(),
                                 headers={'Content-Type': 'application/json', 'X-Token': info['token']})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: out = json.loads(r.read())
    except urllib.error.HTTPError as e: raise AppError(f'App từ chối yêu cầu ({e.code}). Hãy mở lại app.') from None
    except (urllib.error.URLError, ConnectionError, TimeoutError): raise AppError(NOT_OPEN) from None
    if isinstance(out, dict) and out.get('error') and not out.get('settings') and not out.get('meta'): raise AppError(out['error'])
    return out

def name_of(p): return Path(p).name if p else ''

def job_text(job):
    j = dict(job or {})
    return dict(dang_chay=bool(j.get('running')), tac_vu=j.get('task') or '', tien_do=f"{round((j.get('progress') or 0) * 100)}%",
                trang_thai=j.get('status') or '', loi=j.get('error'), ket_qua=j.get('result'))

def started(state):
    """Reply after starting a task: what the app said, and what to call next."""
    j = job_text(state.get('job'))
    if j['loi'] and not j['dang_chay']: raise AppError(j['loi'])
    return dict(j, goi_y='Gọi cho_xong để đợi tác vụ chạy xong.' if j['dang_chay'] else '')

# ---------- tools ----------
def t_trang_thai(a):
    st = api('state'); s = st['settings']
    return dict(phien_ban=st.get('version'), may=st.get('platform'), ai_san_sang=(st.get('ai') or {}).get('ready'), viec=job_text(st['job']),
                ghep_anh=dict(thu_muc_tu_lieu=s.get('mediaFolder'), so_tu_lieu=st.get('mediaCount'), loi_doc=s.get('audio'), nguon_giong=s.get('voiceSource'),
                              khung=s.get('aspect'), lap_video=s.get('loopMedia'), tieu_de=[s.get('title'), s.get('subtitle')]),
                video_chia_se=dict(video_tho=json.loads(s.get('talkVideos') or '[]'), ti_le=s.get('talkAspects')),
                quang_cao=dict(san_pham=s.get('adProduct'), kieu=s.get('adType'), thu_muc_tu_lieu=s.get('adMediaFolder'), khung=s.get('adAspect')),
                thu_muc_luu=s.get('outputFolder'))

def t_cho_xong(a):
    limit = max(5, min(1800, int(a.get('gioi_han_giay') or 600))); end = time.time() + limit; st = api('state')
    while st['job'].get('running') and time.time() < end:
        time.sleep(2); st = api('state')
    j = job_text(st['job'])
    if j['dang_chay']: j['goi_y'] = f'Chưa xong sau {limit} giây; gọi cho_xong lần nữa.'
    return j

def t_dung(a): return job_text(api('cancel').get('job'))

def t_doc_cai_dat(a):
    s = api('state')['settings']
    return {k: v for k, v in sorted(s.items()) if k not in SECRET and not k.endswith('Hint')}

def t_sua_cai_dat(a):
    values = a.get('cai_dat') or {}
    if not isinstance(values, dict) or not values: raise AppError('Hãy truyền cai_dat là các cặp tên: giá trị (xem doc_cai_dat).')
    known = api('state')['settings']
    bad = [k for k in values if k in SECRET or k.endswith(('KeySet', 'Hint'))]
    if bad: raise AppError('Không đổi được ' + ', '.join(bad) + ' qua AI: API key chỉ dán trong app.')
    unknown = [k for k in values if k not in known]
    if unknown: raise AppError('Không có cài đặt: ' + ', '.join(unknown))
    if 'talkVideos' in values and isinstance(values['talkVideos'], list): values['talkVideos'] = json.dumps(values['talkVideos'], ensure_ascii=False)
    if 'grade' in values and isinstance(values['grade'], dict): values['grade'] = json.dumps(values['grade'], ensure_ascii=False)
    s = api('set', {'values': values})['settings']
    return {k: s.get(k) for k in values}

# Ghép ảnh + lời đọc
def t_dung_ghep_anh(a): return started(api('start', {'task': 'render', 'preview': bool(a.get('xem_thu'))}))
def t_len_timeline(a): return started(api('start', {'task': 'plan'}))

def t_doc_timeline(a):
    t = api('timelineState')
    return dict(do_dai_giay=t.get('duration'), canh=[dict(so=i + 1, bat_dau=s['start'], ket_thuc=s['end'], file=s['name'], la_video=bool(s.get('d')),
                    nguon_tu_giay=s.get('srcStart', 0), loi=s.get('text', ''), khung=s.get('frame'), da_sua=bool(s.get('edited')), thieu_file=bool(s.get('missing')))
                    for i, s in enumerate(t.get('shots') or [])],
                tu_lieu=[dict(file=f['name'], loai=f['kind'], do_dai=f.get('d', 0)) for f in t.get('files') or []],
                goi_y='' if t.get('shots') else 'Chưa có timeline: gọi len_timeline rồi cho_xong.')

def t_sua_timeline(a):
    t = api('timelineState'); shots = t.get('shots') or []; files = {f['name']: f for f in t.get('files') or []}
    if not shots: raise AppError('Chưa có timeline: gọi len_timeline trước.')
    for c in a.get('canh') or []:
        i = int(c.get('so', 0)) - 1
        if not 0 <= i < len(shots): raise AppError(f'Không có cảnh số {i + 1} (có {len(shots)} cảnh).')
        sh = shots[i]
        if c.get('file'):
            f = files.get(name_of(c['file']))
            if not f: raise AppError(f'Không thấy “{c["file"]}” trong thư mục tư liệu.')
            sh.update(file=f['path'], d=f.get('d', 0), srcStart=0, frame=None, matched=False); sh.pop('auto', None)
        if 'nguon_tu_giay' in c: sh['srcStart'] = max(0, float(c['nguon_tu_giay']))
        if 'khung' in c: sh['frame'] = c['khung']; sh.pop('auto', None)
        if 'ket_thuc' in c and i < len(shots) - 1:
            end = float(c['ket_thuc']); sh['end'] = end; shots[i + 1]['start'] = end
        sh['edited'] = True
    clean = [{k: v for k, v in s.items() if k not in ('thumb', 'name', 'missing')} for s in shots]
    api('timelineEdit', {'shots': clean})
    return t_doc_timeline({})

# Video chia sẻ
def t_chon_video_tho(a):
    paths = [str(p) for p in a.get('duong_dan') or []]
    missing = [p for p in paths if not Path(p).is_file()]
    if not paths or missing: raise AppError('Không thấy file: ' + ', '.join(missing) if missing else 'Hãy truyền duong_dan là danh sách file video.')
    s = api('set', {'values': {'talkVideos': json.dumps(paths, ensure_ascii=False)}})['settings']
    return dict(video_tho=json.loads(s.get('talkVideos') or '[]'))

def t_phan_tich_video(a): return started(api('start', {'task': 'talk-analyze'}))
def t_xuat_video_chia_se(a): return started(api('start', {'task': 'talk-render'}))

def t_doc_ban_chu(a):
    p = api('talkState').get('project')
    if not p: return dict(goi_y='Chưa có bản chữ: gọi phan_tich_video rồi cho_xong.')
    words = p.get('words') or []; lines = []; cur = []
    for i, w in enumerate(words):
        cur.append(f'{i}:{w["text"]}' + (f'[cắt:{w["cut"]}]' if w.get('cut') else ''))
        if w['text'].endswith(('.', '?', '!')) or len(cur) >= 18: lines.append(' '.join(cur)); cur = []
    if cur: lines.append(' '.join(cur))
    return dict(so_chu=len(words), ban_chu=lines, tieu_de_goi_y=p.get('titles'), tieu_de_chon=p.get('title_choice'), caption=p.get('caption'),
                cach_doc='Mỗi chữ dạng chỉ_số:chữ; [cắt:lý do] là chỗ app sẽ cắt. Dùng cat_chu với chỉ số để cắt hoặc khôi phục.')

def t_cat_chu(a):
    p = api('talkState').get('project')
    if not p: raise AppError('Chưa có bản chữ: gọi phan_tich_video trước.')
    n = len(p.get('words') or []); idx = [int(i) for i in a.get('chi_so') or []]
    if 'tu' in a: idx += list(range(int(a['tu']), int(a.get('den', a['tu'])) + 1))
    idx = sorted({i for i in idx if 0 <= i < n})
    if not idx: raise AppError('Không có chỉ số chữ hợp lệ (đếm từ 0, xem doc_ban_chu).')
    reason = None if a.get('khoi_phuc') else 'tay'
    api('talkEdit', {'cuts': {str(i): reason for i in idx}})
    return dict(da_doi=len(idx), khoi_phuc=bool(a.get('khoi_phuc')), chu=' '.join(p['words'][i]['text'] for i in idx)[:400])

# Video quảng cáo
AD_FIELDS = dict(brief='adBrief', san_pham='adProduct', khach_hang='adAudience', van_de='adProblem', loi_ich='adBenefits', bang_chung='adProof',
                 uu_dai='adOffer', keu_goi='adCta', luu_y='adNotes', kieu='adType', do_dai='adLength', giong_dieu='adEnergy', khung='adAspect', giong='adVoiceSource')

def t_qc_viet_kich_ban(a):
    values = {AD_FIELDS[k]: str(v) for k, v in a.items() if k in AD_FIELDS and v is not None}
    if values: api('set', {'values': values})
    return started(api('start', {'task': 'ad-script'}))

def t_qc_khung_tu_viet(a):
    values = {AD_FIELDS[k]: str(v) for k, v in a.items() if k in AD_FIELDS and v is not None}
    if values: api('set', {'values': values})
    return api('adSkeleton').get('script')

def t_qc_doc_kich_ban(a):
    st = api('adState')
    return dict(kich_ban=st.get('script'), kieu_co_the_chon=[dict(id=t['id'], ten=t['name'], cac_phan=t['parts']) for t in st['meta']['types']],
                tu_lieu=[m['name'] for m in st.get('media') or []], video_da_xuat=st.get('results'))

def t_qc_sua_kich_ban(a):
    script = a.get('kich_ban')
    if not isinstance(script, dict): raise AppError('Truyền kich_ban là cả kịch bản (lấy từ qc_doc_kich_ban rồi sửa).')
    return api('adSave', {'script': script}).get('script')

def t_qc_them_tu_lieu(a):
    paths = [str(p) for p in a.get('duong_dan') or []]
    if not paths: raise AppError('Truyền duong_dan là danh sách ảnh/video.')
    st = api('adAddFiles', {'paths': paths})
    return dict(so_tu_lieu=st.get('mediaCount'), tu_lieu=[m['name'] for m in st.get('media') or []])

def t_qc_xuat(a):
    hooks = [int(i) for i in a.get('hooks') or [0]][:3]
    api('set', {'values': {'adHooks': ','.join(str(i) for i in hooks)}})
    return started(api('start', {'task': 'ad-render', 'preview': bool(a.get('xem_thu'))}))

# Dự án, kết quả
def t_du_an(a): return [dict(loai=p['kind'], id=p['id'], ten=p['name'], cap_nhat=p.get('updated'), chi_tiet=p.get('detail'), da_xuat=p.get('exported')) for p in api('projects').get('projects') or []]

def t_mo_du_an(a):
    out = api('projectOpen', {'kind': a.get('loai'), 'id': a.get('id')})
    return dict(da_mo=True, goi_y='Trang trong app chưa tự chuyển: mở đúng chế độ trong app để xem.')

def t_ket_qua(a):
    st = api('state'); talk = api('talkState'); ads = api('adState')
    return dict(video_moi_nhat=st['job'].get('result'), video_chia_se=[e['name'] for e in talk.get('exports') or []], thu_muc_video_chia_se=talk.get('exportFolder'),
                video_quang_cao=[r['path'] for r in ads.get('results') or []], thu_muc_luu=st['settings'].get('outputFolder'))

obj = lambda props=None, req=None: dict(type='object', properties=props or {}, **({'required': req} if req else {}))
TOOLS = [
    ('trang_thai', 'Tình trạng app Ghép Video đang mở: việc đang chạy, tiến độ, lỗi, tư liệu đã chọn ở 3 chế độ.', obj(), t_trang_thai),
    ('cho_xong', 'Đợi việc đang chạy (dựng, phân tích, viết kịch bản…) xong rồi trả kết quả.', obj(dict(gioi_han_giay=dict(type='integer', description='Đợi tối đa (giây), mặc định 600'))), t_cho_xong),
    ('dung_viec', 'Dừng việc đang chạy.', obj(), t_dung),
    ('doc_cai_dat', 'Đọc toàn bộ cài đặt (không có API key).', obj(), t_doc_cai_dat),
    ('sua_cai_dat', 'Đổi cài đặt theo tên trong doc_cai_dat, vd {"cai_dat":{"aspect":"16:9","loopMedia":true,"audio":"/đường/dẫn/loi-doc.mp3"}}. Không đổi được API key.',
     obj(dict(cai_dat=dict(type='object')), ['cai_dat']), t_sua_cai_dat),
    ('dung_ghep_anh', 'Ghép ảnh + lời đọc: dựng video từ thư mục tư liệu và file lời đọc đã chọn. xem_thu=true chỉ dựng 20 giây đầu.', obj(dict(xem_thu=dict(type='boolean'))), t_dung_ghep_anh),
    ('len_timeline', 'Ghép ảnh + lời đọc: chia cảnh theo lời đọc (chưa xuất), để xem và sửa từng cảnh.', obj(), t_len_timeline),
    ('doc_timeline', 'Ghép ảnh + lời đọc: đọc các cảnh trên timeline và danh sách tư liệu.', obj(), t_doc_timeline),
    ('sua_timeline', 'Ghép ảnh + lời đọc: sửa cảnh theo số (từ 1): đổi file, giây bắt đầu của video nguồn, giây kết thúc cảnh, khung {zoom,cx,cy} (null = tự động).',
     obj(dict(canh=dict(type='array', items=obj(dict(so=dict(type='integer'), file=dict(type='string'), nguon_tu_giay=dict(type='number'), ket_thuc=dict(type='number'), khung=dict(type=['object', 'null'])), ['so']))), ['canh']), t_sua_timeline),
    ('chon_video_tho', 'Video chia sẻ: chọn 1 hoặc nhiều video thô (đường dẫn đầy đủ), ghép theo thứ tự.', obj(dict(duong_dan=dict(type='array', items=dict(type='string'))), ['duong_dan']), t_chon_video_tho),
    ('phan_tich_video', 'Video chia sẻ: nghe video thô, làm bản chữ, tự đánh dấu chỗ cắt (im lặng, ậm ừ, nói vấp).', obj(), t_phan_tich_video),
    ('doc_ban_chu', 'Video chia sẻ: đọc bản chữ có chỉ số từng chữ và chỗ sẽ cắt.', obj(), t_doc_ban_chu),
    ('cat_chu', 'Video chia sẻ: cắt (hoặc khoi_phuc=true để giữ lại) các chữ theo chỉ số: chi_so=[...] hoặc tu..den.',
     obj(dict(chi_so=dict(type='array', items=dict(type='integer')), tu=dict(type='integer'), den=dict(type='integer'), khoi_phuc=dict(type='boolean'))), t_cat_chu),
    ('xuat_video_chia_se', 'Video chia sẻ: xuất video hoàn thiện theo bản chữ đã sửa.', obj(), t_xuat_video_chia_se),
    ('qc_viet_kich_ban', 'Video quảng cáo: điền brief / thông tin sản phẩm (tuỳ chọn) rồi để AI viết kịch bản. kieu: san-pham, van-de, truoc-sau, tinh-nang, liet-ke, huong-dan, cam-nhan, nhieu-nguoi, sang-lap; do_dai: 15/30/45/60; giong_dieu: thuong/soi-noi/rat-soi-noi; khung: 9:16/1:1/16:9.',
     obj({k: dict(type='string') for k in AD_FIELDS}), t_qc_viet_kich_ban),
    ('qc_khung_tu_viet', 'Video quảng cáo: tạo khung kịch bản trống theo kiểu đã chọn để tự điền (không cần AI).', obj({k: dict(type='string') for k in AD_FIELDS}), t_qc_khung_tu_viet),
    ('qc_doc_kich_ban', 'Video quảng cáo: đọc kịch bản hiện tại (hook, các phần, kêu gọi, điều cần kiểm tra), tư liệu và video đã xuất.', obj(), t_qc_doc_kich_ban),
    ('qc_sua_kich_ban', 'Video quảng cáo: thay cả kịch bản (lấy từ qc_doc_kich_ban, sửa rồi gửi lại).', obj(dict(kich_ban=dict(type='object')), ['kich_ban']), t_qc_sua_kich_ban),
    ('qc_them_tu_lieu', 'Video quảng cáo: chép ảnh/video sản phẩm (đường dẫn đầy đủ) vào tư liệu quảng cáo.', obj(dict(duong_dan=dict(type='array', items=dict(type='string'))), ['duong_dan']), t_qc_them_tu_lieu),
    ('qc_xuat', 'Video quảng cáo: xuất mỗi hook một video. hooks = số thứ tự hook (từ 0), tối đa 3; xem_thu=true chỉ dựng 20 giây của hook đầu.',
     obj(dict(hooks=dict(type='array', items=dict(type='integer')), xem_thu=dict(type='boolean'))), t_qc_xuat),
    ('du_an', 'Danh sách dự án đã làm (cả 3 chế độ đều tự lưu).', obj(), t_du_an),
    ('mo_du_an', 'Mở lại một dự án (loai, id lấy từ du_an).', obj(dict(loai=dict(type='string'), id=dict(type='string')), ['loai', 'id']), t_mo_du_an),
    ('ket_qua', 'Các video đã xuất gần nhất và nơi lưu.', obj(), t_ket_qua),
]
BY_NAME = {t[0]: t for t in TOOLS}
INSTRUCTIONS = ('Điều khiển app Ghép Video đang mở trên máy. App phải đang mở. Dựng, phân tích, viết kịch bản là việc chạy nền: '
                'gọi xong thì gọi cho_xong để đợi kết quả, đừng báo "đã xong" trước khi cho_xong báo hết chạy và không lỗi. '
                'Trả lời người dùng bằng tiếng Việt thường. Không xin hay nhận API key: key chỉ dán trong app.')

def handle(msg):
    method, mid = msg.get('method'), msg.get('id')
    if method == 'initialize':
        ver = (msg.get('params') or {}).get('protocolVersion') or PROTOCOL
        return dict(protocolVersion=ver, capabilities=dict(tools={}), serverInfo=dict(name='ghep-video', version='1.0'), instructions=INSTRUCTIONS)
    if method == 'ping': return {}
    if method == 'tools/list': return dict(tools=[dict(name=n, description=d, inputSchema=s) for n, d, s, _ in TOOLS])
    if method == 'tools/call':
        p = msg.get('params') or {}; tool = BY_NAME.get(p.get('name'))
        if not tool: raise LookupError(f'Không có công cụ {p.get("name")}')
        try: out = tool[3](p.get('arguments') or {}); err = False
        except AppError as e: out = str(e); err = True
        except Exception as e: out = f'Lỗi: {e}'; err = True
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=1)
        return dict(content=[dict(type='text', text=text)], isError=err)
    if mid is None: return None   # notifications (initialized, cancelled…)
    raise LookupError(f'Không hỗ trợ {method}')

def main():
    for line in sys.stdin.buffer:
        try: msg = json.loads(line.decode('utf-8'))
        except ValueError: continue
        try: result = handle(msg); reply = None if msg.get('id') is None else dict(jsonrpc='2.0', id=msg['id'], result=result)
        except LookupError as e: reply = dict(jsonrpc='2.0', id=msg.get('id'), error=dict(code=-32601, message=str(e)))
        if reply is not None:
            sys.stdout.buffer.write((json.dumps(reply, ensure_ascii=False) + '\n').encode('utf-8')); sys.stdout.buffer.flush()

if __name__ == '__main__': main()
