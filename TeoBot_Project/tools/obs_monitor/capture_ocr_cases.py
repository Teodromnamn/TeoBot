"""Capture bounded diagnostic crops, without changing live OCR decisions.
Writes only HP/MP bars, not the full desktop. Run from TeoBot_Project.
"""
import json
import time
import zipfile
from pathlib import Path

import cv2
from benchmark_hp_mp import crop_bar,prepare
import test_obs_tesseract as live


class DiagnosticAnalyzer(live.Analyzer):
    output=None

    def __init__(self,engine,rectangles):
        super().__init__(engine,rectangles)
        self.baseline=[None,None]
        self.saved=0
        self.last_save=-100
        self.last_normal=-100

    def analyze(self,frame):
        result=super().analyze(frame)
        now=time.perf_counter()
        reasons=[]
        for i,r in enumerate(result['readings']):
            value=r['value']
            if value is None:
                reasons.append(['HP','MP'][i]+'_unreadable')
            elif self.baseline[i] is None:
                self.baseline[i]=value['maximum']
            elif value['maximum']!=self.baseline[i]:
                # Diagnostic trigger only. Never overwrite/correct OCR values.
                reasons.append(['HP','MP'][i]+'_maximum_differs_from_initial')
        normal=not reasons and now-self.last_normal>=10
        if self.saved<100 and now-self.last_save>=.5 and (reasons or normal):
            case=self.output/f'case_{self.saved:03d}'
            case.mkdir()
            for name,rect in zip(['hp','mp'],self.rectangles):
                original=crop_bar(frame,rect)
                prepared=prepare(original,'dynamic')
                for suffix,image in [('original',original),('prepared',prepared),('binary',live.binary(prepared))]:
                    cv2.imencode('.png',image)[1].tofile(case/f'{name}_{suffix}.png')
            (case/'reading.json').write_text(json.dumps({'reasons':reasons or ['periodic_reference'],
                    'readings':result['readings'],'rectangles':self.rectangles,
                    'initial_maximum_observed':self.baseline,
                    'note':'Initial maximum is diagnostic context, NOT ground truth.'},indent=2),encoding='utf-8')
            self.saved+=1;self.last_save=now
            if normal:self.last_normal=now
        return result


def main():
    folder=Path('ocr_cases_'+time.strftime('%Y%m%d_%H%M%S'))
    folder.mkdir()
    DiagnosticAnalyzer.output=folder
    original=live.Analyzer
    live.Analyzer=DiagnosticAnalyzer
    try:
        live.main()
    finally:
        live.Analyzer=original
        archive=folder.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(folder.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(folder))
        print(f'Wyslij paczke wycinkow: {archive}')
        print('To test diagnostyczny: zapis PNG dodaje koszt i nie zmienia sposobu OCR.')


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Przerwano.')
