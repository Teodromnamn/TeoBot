import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import run_observation_diagnostic as observer
import run_long_diagnostic as run
import test_obs_pipeline as pipeline
import test_obs_tesseract as monitor
from check_native_threshold_replay import PublicationCollector


class Tests(unittest.TestCase):
    def exercise(self,fail_log=False):
        with tempfile.TemporaryDirectory() as tmp:
            cwd=Path.cwd();previous=pipeline._result_publisher
            original_open=Path.open;valid_after_log_error=[]
            def open_file(path,*a,**kw):
                if fail_log and path.name=='observation_decisions.jsonl':raise OSError('test log failure')
                return original_open(path,*a,**kw)
            def fake_monitor():
                output=Path('obs_fast_results/test');output.mkdir(parents=True)
                collector=PublicationCollector(output/'latest.json');pipeline._result_publisher=collector
                low={'value':{'current':5,'maximum':100},'source':'side_text','verification':'side_color_supported'}
                for wall,mono,status,reading in [(1000,0,'OK',low),(1100,100,'GRA_ZMINIMALIZOWANA',None),
                                               (1200,200,'OK',low),(2200,1200,'OK',low),(2300,1300,'ZATRZYMANY_PROGRAM',None)]:
                    with patch.object(observer.time,'time_ns',return_value=wall*1_000_000),patch.object(observer.time,'monotonic_ns',return_value=mono*1_000_000):
                        pipeline.publish(collector.path,status,[reading,reading] if reading else None,0 if reading else None)
                    if status=='OK':valid_after_log_error.append(collector.data['valid'])
                (output/'latest.json').write_text(json.dumps(collector.data))
            try:
                os.chdir(tmp)
                with patch.object(observer.sys,'argv',['run_observation_diagnostic.py','--seconds','1','--threshold-unit','current','--hp-threshold','10','--mp-threshold','10']),patch.object(monitor,'main',fake_monitor),patch.object(Path,'open',open_file),contextlib.redirect_stdout(io.StringIO()):
                    observer.main()
                self.assertTrue(all(valid_after_log_error))
                archive=next(Path('.').glob('long_diagnostic_*.zip'))
                with zipfile.ZipFile(archive) as z:
                    summary=json.loads(z.read('monitor/test/observation_summary.json'))
                    self.assertEqual(summary['decisions']['hp']['would_execute'],2)
                    self.assertEqual(summary['decisions']['hp']['cooldown'],1)
                    self.assertEqual(summary['decisions']['hp']['unavailable'],2)
                    if fail_log:self.assertIn('test log failure',summary['log_error'])
                    else:
                        rows=[json.loads(l) for l in z.read('monitor/test/observation_decisions.jsonl').decode().splitlines()]
                        self.assertEqual(len(rows),5)
                        self.assertEqual(rows[1]['decisions']['hp']['decision'],'unavailable')
            finally:os.chdir(cwd);pipeline._result_publisher=previous
    def test_live_hook_and_bundle_without_camera(self):self.exercise()
    def test_diagnostic_failure_does_not_invalidate_ocr(self):self.exercise(True)

if __name__=='__main__':unittest.main()
