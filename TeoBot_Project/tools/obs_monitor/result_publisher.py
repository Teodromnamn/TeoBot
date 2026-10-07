"""Current in-process result plus a single-slot asynchronous diagnostic writer."""
import copy
import json
import threading
import time
from pathlib import Path

class ResultPublisher:
    def __init__(self, path, writer=None):
        self.path=Path(path);self._writer=writer or self._write
        self._condition=threading.Condition();self._latest=None;self._pending=None
        self._closing=False;self.error=None;self.written=0;self.coalesced=0
        self._thread=threading.Thread(target=self._run,name='ocr-result-writer',daemon=True)
        self._thread.start()

    def _write(self, data):
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,indent=2),encoding='utf-8')
        temporary.replace(self.path)

    def snapshot(self):
        with self._condition:return copy.deepcopy(self._latest or {})

    def current(self):
        data=self.snapshot();now=time.time_ns()//1000000
        for name in ('hp','mp'):
            resource=data.get('resources',{}).get(name,{})
            if resource.get('expires_at_unix_ms',0)<=now:
                resource.update(valid=False,value=None,quality='stale')
                data[name]=None
        data['valid']=all(data.get('resources',{}).get(r,{}).get('valid',False) for r in ('hp','mp'))
        return data

    def submit(self, data):
        frozen=copy.deepcopy(data)
        with self._condition:
            if self._closing:raise RuntimeError('Publisher closed')
            self._latest=frozen
            if self._pending is not None:self.coalesced+=1
            self._pending=frozen;self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda:self._pending is not None or self._closing)
                if self._pending is None:return
                data=self._pending;self._pending=None
            try:
                self._writer(data)
                with self._condition:self.written+=1;self.error=None
            except Exception as error:
                with self._condition:self.error=str(error)

    def close(self, timeout=2.):
        with self._condition:self._closing=True;self._condition.notify()
        self._thread.join(timeout)
        return not self._thread.is_alive()
