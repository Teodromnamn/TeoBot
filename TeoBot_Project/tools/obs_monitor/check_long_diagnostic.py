import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import run_long_diagnostic as run
import test_obs_tesseract as monitor


class Tests(unittest.TestCase):
    def test_run_bundles_log_results_and_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd()
            os.chdir(tmp)
            try:
                def fake_main():
                    print('ENTER: calibration prompt',end='',flush=True)
                    result=Path('obs_fast_results/run');result.mkdir(parents=True)
                    (result/'summary.json').write_text('{}')
                    with zipfile.ZipFile('ocr_dataset_test.zip','w') as z:z.writestr('labels.csv','case,hp_current\n')
                with patch.object(run.sys,'argv',['run_long_diagnostic.py','--seconds','600']),patch.object(monitor,'main',fake_main),contextlib.redirect_stdout(io.StringIO()):
                    run.main()
                archive=next(Path('.').glob('long_diagnostic_*.zip'))
                with zipfile.ZipFile(archive) as z:
                    self.assertIn('ENTER: calibration prompt',z.read('console.log').decode())
                    self.assertIn('ocr_dataset_test.zip',z.namelist())
                    self.assertIn('monitor/run/summary.json',z.namelist())
                    self.assertTrue(json.loads(z.read('run.json'))['completed'])
            finally:os.chdir(previous)

    def test_existing_artifacts_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ocr_dataset_old.zip';p.write_bytes(b'old')
            before=run.artifacts(Path(tmp))
            q=Path(tmp)/'ocr_dataset_new.zip';q.write_bytes(b'new')
            self.assertEqual(run.artifacts(Path(tmp))-before,{q})


if __name__=='__main__':unittest.main()
