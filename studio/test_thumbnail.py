import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from PIL import Image
import numpy as np
import thumbnail as T

class ThumbnailTests(unittest.TestCase):
 def test_crop_keeps_face_inside_its_zone(self):
  face=[[.45,.40,.10,.08]]  # small face in a landscape frame
  x,y,r,b=T.crop_for(1920,1080,face,1080/955,zone=(.06,.78))
  top=(.40-.45*.08)*1080;bottom=(.40+1.25*.08)*1080
  self.assertLessEqual(y,top);self.assertGreaterEqual(b,bottom)
  self.assertLessEqual((bottom-y)/(b-y),.78+1e-6,'face stays above the title band')
 def test_face_cut_by_the_frame_edge_is_not_a_clean_fit(self):
  img=Image.fromarray((np.random.rand(400,300)*255).astype('uint8'))
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'f.jpg';img.save(p)
   s=T.score(p,{'faces':[[-.01,.3,.3,.2]],'rolls':[0]})
   self.assertFalse(s['fits'])
   upright=T.score(p,{'faces':[[.3,.3,.3,.2]],'rolls':[3]})['score'];sideways=T.score(p,{'faces':[[.3,.3,.3,.2]],'rolls':[80]})['score']
   self.assertLess(sideways,upright/3,'sideways faces rank far lower')
 def test_compose_one_to_three_pictures(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'a.jpg';Image.new('RGB',(720,1280),'#468').save(src)
   c={'path':str(src),'faces':[[.4,.3,.2,.12]]}
   for n in (1,2,3):
    out=T.compose([c]*n,Path(d)/f'{n}.jpg','ĐÀN ÔNG','Cần được công nhận','pop')
    self.assertEqual(Image.open(out).size,(1080,1920))
   with self.assertRaises(ValueError):T.compose([c]*4,Path(d)/'4.jpg')

if __name__=='__main__':unittest.main()
