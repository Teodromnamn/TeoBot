import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import replay_hp_mp_dataset as replay


class Tests(unittest.TestCase):
    def test_saved_windows_observations_replay_without_engine_and_require_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'data.zip';saved=Path(folder)/'ocr.jsonl'
            rows=[]
            with zipfile.ZipFile(archive,'w') as z:
                for idx in range(2):
                    case=f'case_{idx:05d}'
                    z.writestr(case+'/reading.json',json.dumps({'elapsed_s':idx*.1}))
                    for resource,maximum in [('hp',195),('mp',150)]:
                        for kind in ['top_original','side_bar']:
                            color=(180,0,0) if resource=='mp' else ((0,0,180) if kind=='side_bar' else (0,180,0))
                            image=np.full((10,100,3),color,np.uint8)
                            z.writestr(f'{case}/{resource}_{kind}.png',cv2.imencode('.png',image)[1].tobytes())
                        rows.append({'case':case,'resource':resource,'top':{'raw':[f'{maximum}/{maximum}'],'value':{'current':maximum,'maximum':maximum}},'side':{'raw':str(maximum),'current':maximum}})
            saved.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            argv=['replay',str(archive),'--resilient-verification','--saved-ocr',str(saved)]
            output=io.StringIO()
            with patch('sys.argv',argv),patch.object(replay,'Engine') as engine,contextlib.redirect_stdout(output):
                replay.main();engine.assert_not_called()
            result=json.loads(output.getvalue().splitlines()[-1])['summary']
            self.assertEqual(result['resource_samples'],4)
            self.assertEqual(result['confirmed_resources'],2)
            saved.write_text(json.dumps(rows[0])+'\n')
            with patch('sys.argv',argv),self.assertRaisesRegex(ValueError,'do not match'):
                replay.main()


if __name__=='__main__':unittest.main()
