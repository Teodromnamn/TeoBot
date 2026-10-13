import threading,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from result_publisher import ResultPublisher
import test_obs_pipeline as pipeline

class Tests(unittest.TestCase):
 def test_slow_disk_coalesces_and_current_invalidates_immediately(self):
  entered=threading.Event();release=threading.Event();written=[]
  def writer(data):
   if not written:entered.set();release.wait(1)
   written.append(data)
  with TemporaryDirectory() as folder:
   p=ResultPublisher(Path(folder)/'latest.json',writer);pipeline._result_publisher=p
   try:
    v={'value':{'current':111,'maximum':195}}
    pipeline.publish(p.path,'OK',[v,v],100)
    self.assertTrue(entered.wait(1));v['value']['current']=1
    self.assertEqual(p.current()['hp']['current'],111)
    pipeline.publish(p.path,'OK',[{'value':{'current':57,'maximum':195}}]*2,100)
    pipeline.publish(p.path,'GRA_ZMINIMALIZOWANA')
    self.assertIsNone(p.current()['hp']);self.assertEqual(p.snapshot()['resources']['hp']['last_known']['value']['current'],57)
    release.set();self.assertTrue(p.close());self.assertEqual(len(written),2);self.assertFalse(written[-1]['valid'])
   finally:release.set();p.close();pipeline._result_publisher=None
 def test_disk_error_does_not_remove_current_and_expiry_is_enforced(self):
  failed=threading.Event()
  def writer(data):failed.set();raise OSError('disk unavailable')
  p=ResultPublisher('unused.json',writer)
  p.submit({'hp':{'current':111},'resources':{'hp':{'valid':True,'expires_at_unix_ms':0}}})
  self.assertTrue(failed.wait(1));self.assertIsNone(p.current()['hp']);self.assertEqual(p.snapshot()['hp']['current'],111)
  self.assertTrue(p.close());self.assertEqual(p.error,'disk unavailable')
 def test_atomic_file_final_snapshot(self):
  import json
  with TemporaryDirectory() as folder:
   p=ResultPublisher(Path(folder)/'latest.json');p.submit({'valid':False,'hp':None});self.assertTrue(p.close());self.assertFalse(json.loads(p.path.read_text())['valid'])
if __name__=='__main__':unittest.main()
