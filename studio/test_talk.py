"""Video chia sẻ: cut rules, retake safety check, keywords, B-roll picking (no media or AI needed)."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import talk

def words(spec):
    """'Xin|chào|...' with 0.3 s words and 0.05 s gaps; '_' inserts a 1 s pause."""
    out, t = [], 0.0
    for tok in spec.split('|'):
        if tok == '_': t += 1.0; continue
        out.append(dict(text=tok, start=round(t, 2), end=round(t + .3, 2), cut=None)); t += .35
    return out

class TalkTests(unittest.TestCase):
    def test_fillers_and_stutters_are_marked(self):
        w = words('Xin|chào.|Ờ,|hôm|nay|thứ|ba|thứ|ba|bạn|bạn|đăng')
        talk.mark_auto_cuts(w)
        self.assertEqual([x['cut'] for x in w], [None, None, 'am-u', None, None, 'lap', 'lap', None, None, 'lap', None, None])

    def test_pause_and_cut_word_split_the_keep_ranges(self):
        w = words('một|hai|_|ba|bốn|năm')
        w[3]['cut'] = 'tay'  # 'bốn' (the '_' pause is not a word)
        keep = talk.keep_ranges(w, 10)
        self.assertEqual(len(keep), 3, 'split at the pause and around the cut word')
        self.assertLessEqual(keep[0][1], w[2]['start']); self.assertGreaterEqual(keep[1][0], w[1]['end'])
        inside = lambda t: any(a <= t < b for a, b in keep)
        self.assertFalse(inside(1.2), 'middle of the 1 s pause is gone')
        self.assertFalse(inside((w[3]['start'] + w[3]['end']) / 2), 'the cut word is gone')
        for k in (0, 1, 2, 4): self.assertTrue(inside((w[k]['start'] + w[k]['end']) / 2), f'word {k} is kept')

    def test_retake_needs_a_repeat_or_self_correction(self):
        w = words('Hôm|nay|mình|chia|sẻ|về.|Cách|làm|này|giúp|bạn.|Cách|làm|này|giúp|bạn|tiết|kiệm.|Cảm|ơn.')
        s = talk.sentences(w)
        self.assertFalse(talk.is_retake(w, s[0], s[1:]), 'an opening sentence with no repeat is kept')
        self.assertTrue(talk.is_retake(w, s[1], s[2:]), 'a sentence said again right after is a retake')
        w2 = words('Giúp|bạn|tiết|kiệm,|à|không,|để|mình|nói|lại.|Giúp|bạn|tiết|kiệm|thời|gian.')
        s2 = talk.sentences(w2); self.assertTrue(talk.is_retake(w2, s2[0], s2[1:]))

    def test_keywords_mark_every_word_of_a_phrase(self):
        w = words('đăng|vào|khung|giờ|vàng|buổi|tối')
        talk.mark_keywords(w, ['khung giờ vàng'])
        self.assertEqual([x.get('kw', False) for x in w], [False, False, True, True, True, False, False])

    def test_broll_skips_the_opening_and_never_two_in_a_row(self):
        w = words('|'.join(f'câu{i}.' for i in range(12)))
        for x in w: x['end'] = x['start'] + 2  # 2 s phrases
        phrases = talk.phrase_list(w)
        units = [dict(id=k, path=f'/kho/{k}.mp4', d=10, a=0, b=10, text='', source=f'{k}.mp4') for k in (1, 2, 3)]
        picked = talk.pick_broll(phrases, w, {p['id']: [1, 2, 3] for p in phrases}, units, .5)
        ids = [p['phrase'] for p in picked]
        self.assertNotIn(1, ids)
        self.assertTrue(all(b - a >= 2 for a, b in zip(ids, ids[1:])))
        self.assertTrue(all(p['dur'] <= 3.5 for p in picked))

if __name__ == '__main__': unittest.main()
