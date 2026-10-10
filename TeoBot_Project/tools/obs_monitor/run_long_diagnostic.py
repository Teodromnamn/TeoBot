"""Ten-minute live diagnostic; records crops, console, timings and result files.

No input actions. Run from TeoBot_Project with game and OBS running.
"""
import argparse
import json
import subprocess
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path


class Tee:
    def __init__(self, console, log):
        self.console,self.log=console,log
    def write(self,text):
        self.console.write(text);self.log.write(text);self.log.flush()
        return len(text)
    def flush(self):
        self.console.flush();self.log.flush()
    def isatty(self):
        return self.console.isatty()


def artifacts(root):
    paths=list(root.glob('ocr_dataset_*.zip'))+list(root.glob('ocr_conflicts_*.zip'))
    if (root/'obs_fast_results').exists():
        paths+=list((root/'obs_fast_results').iterdir())
    return set(paths)


def bundle(folder,created):
    archive=folder.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(folder.iterdir()):
            if file.is_file():z.write(file,file.name)
        for item in sorted(created):
            if item.is_file():z.write(item,item.name)
            elif item.is_dir():
                for file in sorted(item.rglob('*')):
                    if file.is_file():z.write(file,Path('monitor')/item.name/file.relative_to(item))
    return archive


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=600)
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    args,extra=p.parse_known_args()
    if not 1 <= args.seconds <= 1800:p.error('seconds must be between 1 and 1800')
    root=Path.cwd();before=artifacts(root)
    folder=root/('long_diagnostic_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    folder.mkdir()
    command=['--seconds',str(args.seconds),'--threads','2','--target-fps','10',
        '--resilient-verification','--capture-dataset','--dataset-hz','20',
        '--dataset-limit',str(min(20000,args.seconds*20+100)),
        '--max-age-ms','5000','--slow-age-ms','250','--directory',args.directory,*extra]
    try:
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):revision=None
    meta={'started_at':datetime.now().astimezone().isoformat(),'git_revision':revision,
          'arguments':command,'python':sys.version,'completed':False,
          'note':'Raw crops of every analyzed frame at target 10/s (capture cap 20/s). '
                 'No actions. Saved OCR is not ground truth. PNG writes affect timings. '
                 'Includes calibration screenshots; inspect before publicly sharing.'}
    original_out,original_err,original_argv=sys.stdout,sys.stderr,sys.argv
    error=None
    with (folder/'console.log').open('w',encoding='utf-8') as log:
        sys.stdout=Tee(original_out,log);sys.stderr=Tee(original_err,log)
        try:
            import test_obs_tesseract
            sys.argv=['test_obs_tesseract.py',*command]
            print('TEST 10 MIN: pelne HP/MP do kalibracji, OBS kamera wlaczona. Po kalibracji nacisnij ENTER.',flush=True)
            test_obs_tesseract.main()
            meta['completed']=True
        except KeyboardInterrupt:
            meta['interrupted']=True
            print('Przerwano; pakowanie zapisanych danych.',flush=True)
        except Exception as exc:
            error=exc;meta['error']=repr(exc);traceback.print_exc()
        finally:
            sys.stdout,sys.stderr,sys.argv=original_out,original_err,original_argv
    meta['finished_at']=datetime.now().astimezone().isoformat()
    created=artifacts(root)-before
    meta['artifacts']=[str(x.relative_to(root)) for x in sorted(created)]
    (folder/'run.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    archive=bundle(folder,created)
    print(f'WYSLIJ PACZKE: {archive}',flush=True)
    if error:raise SystemExit(1)


if __name__=='__main__':main()
