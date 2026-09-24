import unittest
import numpy as np
from renderer import silence_ranges,kept_ranges,mapped_time,face_crop,groups_for,group_end,parse_fixes,apply_fixes,scene_spans,assign_shots,source_start,rotation_shots

class EditingTests(unittest.TestCase):
 def test_silence_keeps_word_padding_and_remaps_later_words(self):
  pcm=np.zeros((4000,2),dtype=np.int16);pcm[1000:2000]=5000;pcm[2500:3500]=5000
  keep=kept_ranges(4,silence_ranges(pcm,1000))
  self.assertAlmostEqual(keep[0][0],.88)
  self.assertAlmostEqual(keep[0][1],2.08)
  self.assertAlmostEqual(mapped_time(2.5,keep),1.32)
  self.assertAlmostEqual(mapped_time(3,keep)-mapped_time(2.5,keep),.5)
 def test_short_speech_pause_is_not_cut(self):
  pcm=np.full((1000,2),5000,dtype=np.int16);pcm[300:600]=0
  self.assertEqual(silence_ranges(pcm,1000),[])
 def test_speech_on_either_stereo_channel_is_preserved(self):
  pcm=np.zeros((1000,2),dtype=np.int16);pcm[:,1]=5000
  self.assertEqual(silence_ranges(pcm,1000),[])
 def test_off_center_face_stays_inside_crop(self):
  box=face_crop(2000,2000,[[.72,.3,.16,.2]])
  self.assertIsNotNone(box)
  x,y,r,b=box
  self.assertLessEqual(x,.72*2000);self.assertGreaterEqual(r,.88*2000)
  self.assertLessEqual(y,.3*2000);self.assertGreaterEqual(b,.5*2000)
  self.assertAlmostEqual((r-x)/(b-y),9/16,places=2)
 def test_widely_separated_faces_skip_photo(self):
  self.assertIsNone(face_crop(2000,1000,[[.05,.2,.2,.3],[.75,.2,.2,.3]]))
 def test_time_before_after_removed_region(self):
  keep=[(1,2),(3,4)]
  self.assertEqual([mapped_time(t,keep) for t in [0,1,2,2.5,3,4,5]],[0,0,1,1,1,2,2])

 def test_sentence_end_stays_on_its_line(self):
  words=[dict(text=t,start=i*.3,end=i*.3+.25) for i,t in enumerate('Có tôi nha, tôi đã từng như vậy nha. Mấy bà biết không,'.split())]
  lines=[' '.join(w['text'] for w in g) for g in groups_for(words)]
  self.assertEqual(lines,['Có tôi nha,','tôi đã từng như vậy nha.','Mấy bà biết không,'])
 def test_long_phrase_is_split_evenly(self):
  words=[dict(text=t,start=i*.3,end=i*.3+.25) for i,t in enumerate('Tụi mình hay nghĩ chồng là trụ cột,'.split())]
  self.assertEqual([len(g) for g in groups_for(words)],[4,4])
 def test_line_holds_until_next_line(self):
  g=[[dict(text='a',start=0,end=1)],[dict(text='b',start=1.4,end=2)],[dict(text='c',start=9,end=10)]]
  self.assertEqual([group_end(g,i,20) for i in range(3)],[1.4,3.5,11.5])
 def test_spelling_fix_keeps_punctuation_and_capital(self):
  fixes=parse_fixes('xòng => sòng\nđận -> đần\n\nrác')
  self.assertEqual(fixes,{'xòng':'sòng','đận':'đần'})
  words=apply_fixes([dict(text='Xòng,'),dict(text='đận.'),dict(text='xòngxòng')],fixes)
  self.assertEqual([w['text'] for w in words],['Sòng,','đần.','xòngxòng'])

 def test_scene_cuts_land_on_phrase_starts_and_merge_short_ones(self):
  ph=[[dict(text='a.',start=.2,end=2)],[dict(text='b.',start=3,end=3.5)],[dict(text='c.',start=3.8,end=6)]]
  spans=scene_spans(ph,8)
  self.assertEqual([(s['start'],s['end']) for s in spans],[(0,3.8),(3.8,8)])
  self.assertEqual(spans[0]['text'],'a. b.')
 def test_matched_scenes_cycle_and_never_repeat_back_to_back(self):
  units=[dict(id=i,d=0,a=0,b=0,source=f'f{i}') for i in (1,2,3)]
  spans=[dict(start=0,end=6,text='x'),dict(start=6,end=8,text='y')]
  shots=assign_shots(spans,{1:[2,3],2:[3]},units,2,8)
  self.assertEqual([s['unit'] for s in shots],[2,3,2,3])
  self.assertEqual([s['matched'] for s in shots],[True,True,True,True])
 def test_repeated_scene_reads_further_into_the_video(self):
  u=dict(d=60,a=10,b=20)
  self.assertEqual([round(source_start(u,2.5,k),2) for k in range(3)],[10,12.5,15])
 def test_rotation_has_no_tiny_last_shot(self):
  self.assertEqual(len(rotation_shots(10.2,2.5)),4)

 def test_one_file_does_not_run_more_than_twice_when_alternatives_exist(self):
  units=[dict(id=i,d=60,a=0,b=10,source='bep' if i<5 else 'com') for i in range(1,7)]
  spans=[dict(start=k*2,end=k*2+2,text=str(k)) for k in range(5)]
  shots=assign_shots(spans,{k+1:[1+k%4,5] for k in range(5)},units,2,10)
  src=[units[s['unit']-1]['source'] for s in shots]
  self.assertEqual(src,['bep','bep','com','bep','bep'])

if __name__=='__main__':unittest.main()
