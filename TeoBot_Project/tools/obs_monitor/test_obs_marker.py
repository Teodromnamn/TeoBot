"""OBS marker reader for obs_marker.html, Windows, Python 3.10+.

Requires numpy, opencv-python, cv2-enumerate-cameras. No OCR.
Timestamp measures browser rendering -> reception, NOT game capture freshness.
Only one marker should be visible. Do not crop, rotate or mirror it.
"""
import argparse
import binascii
import json
import threading
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


def decode(frame, rect):
    x,y,w,h=rect
    if min(x,y)<0 or x+w>frame.shape[1] or y+h>frame.shape[0]:
        return None
    # Sample each cell away from edges; support translation and moderate scaling.
    data=[]
    for byte in range(8):
        value=0
        for bit in range(8):
            cx=x+int((16+(byte*8+bit+.5)*8)*w/544)
            cy=y+h//2
            pixel=frame[max(y,cy-1):min(y+h,cy+2),max(x,cx-1):min(x+w,cx+2)]
            grey=float(np.mean(pixel))
            if 85 < grey < 170:
                return None
            value=(value<<1)|int(grey>=170)
        data.append(value)
    if data[:2]!=[0x54,0xb7] or binascii.crc_hqx(bytes(data[:6]),0xffff)!=(data[6]<<8|data[7]):
        return None
    return int.from_bytes(bytes(data[2:6]),'big')


class Detector:
    def __init__(self):
        self.rect=None
        self.next_search=0

    def read(self,frame,now):
        if self.rect is not None:
            stamp=decode(frame,self.rect)
            if stamp is not None:
                return stamp
            self.rect=None
        if now<self.next_search:
            return None
        self.next_search=now+.5
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,(135,140,100),(175,255,255))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        matches=[]
        for contour in contours:
            rect=cv2.boundingRect(contour)
            x,y,w,h=rect
            if w<272 or h<16 or h>160 or not 8<=w/h<=40:
                continue
            stamp=decode(frame,rect)
            if stamp is not None:
                matches.append((rect,stamp))
        if len(matches)==1:
            self.rect,stamp=matches[0]
            return stamp
        return None


class Health:
    def __init__(self):
        self.stamp=None
        self.changed=None

    def update(self,stamp,wall_ms,mono,late_ms):
        if stamp is None:
            return 'BRAK_ZNACZNIKA',None
        if stamp!=self.stamp:
            self.stamp=stamp
            self.changed=mono
        age=((wall_ms-stamp+2**31)%2**32)-2**31
        if mono-self.changed>=.5:
            return 'ZATRZYMANY',age
        if age < -50 or age > 60000:
            return 'SPRAWDZ_ZEGAR_LUB_STARY_OBRAZ',age
        return ('OPOZNIONY' if age>late_ms else 'OK'),age


class Camera:
    def __init__(self,args):
        self.args=args
        self.cv=threading.Condition()
        self.stop=threading.Event()
        self.latest=None
        self.error=None
        self.count=0
        self.thread=threading.Thread(target=self.run,daemon=True)

    def run(self):
        cap=None
        try:
            from cv2_enumerate_cameras import enumerate_cameras
            devices=list(enumerate_cameras(cv2.CAP_DSHOW))
            matches=[d for d in devices if d.name.strip().casefold()=='obs virtual camera']
            if len(matches)!=1:
                raise RuntimeError(f'Potrzebna jedna OBS Virtual Camera. Dostepne: {[d.name for d in devices]}')
            device=matches[0]
            cap=cv2.VideoCapture(device.index,device.backend)
            if not cap.isOpened():
                raise RuntimeError('Nie mozna otworzyc kamery OBS')
            for prop,value in [(cv2.CAP_PROP_FRAME_WIDTH,self.args.width),
                               (cv2.CAP_PROP_FRAME_HEIGHT,self.args.height),(cv2.CAP_PROP_FPS,self.args.fps)]:
                cap.set(prop,value)
            while not self.stop.is_set():
                ok,frame=cap.read()
                wall=time.time_ns()//1000000
                mono=time.perf_counter()
                if not ok:
                    raise RuntimeError('Kamera nie zwrocila obrazu')
                with self.cv:
                    self.count+=1
                    self.latest=(self.count,frame,wall,mono)
                    self.cv.notify_all()
        except Exception as error:
            with self.cv:
                self.error=str(error)
                self.cv.notify_all()
        finally:
            if cap is not None:
                cap.release()

    def get(self,seq):
        with self.cv:
            self.cv.wait_for(lambda:self.error or (self.latest is not None and self.latest[0]>seq),timeout=.25)
            if self.error:
                raise RuntimeError(self.error)
            return self.latest if self.latest is not None and self.latest[0]>seq else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--width',type=int,default=1920)
    parser.add_argument('--height',type=int,default=1080)
    parser.add_argument('--fps',type=int,default=60)
    parser.add_argument('--late-ms',type=int,default=250)
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    if min(args.seconds,args.width,args.height,args.fps,args.late_ms)<=0:
        parser.error('Parametry musza byc dodatnie')
    cv2.setNumThreads(1)
    camera=Camera(args)
    detector=Detector()
    health=Health()
    seq=0
    start=time.perf_counter()
    last_print=0
    ages=[]
    costs=[]
    counts=Counter()
    rows=[]
    error=None
    camera.thread.start()
    print('Szukam OBS i znacznika. Test 60 s domyslnie; Ctrl+C konczy.',flush=True)
    try:
        while time.perf_counter()-start<args.seconds:
            item=camera.get(seq)
            now=time.perf_counter()
            age=None
            if item is None:
                status='BRAK_KLATEK'
            else:
                seq,frame,wall,received=item
                stamp=detector.read(frame,now)
                status,age=health.update(stamp,wall,received,args.late_ms)
                costs.append((time.perf_counter()-now)*1000)
                if status in ('OK','OPOZNIONY') and age>=0:
                    ages.append(age)
                if args.preview:
                    preview=cv2.resize(frame,(960,max(1,int(frame.shape[0]*960/frame.shape[1]))))
                    cv2.putText(preview,f'{status} age={age} ms',(10,30),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,255,255),2)
                    cv2.imshow('OBS marker - Q konczy',preview)
                    if cv2.waitKey(1)&255==ord('q'):
                        break
            counts[status]+=1
            if now-last_print>=1:
                print(f'{status}: wiek={age} ms; znacznik={detector.rect}',flush=True)
                rows.append({'elapsed_s':round(now-start,3),'status':status,'age_ms':age,'rect':detector.rect})
                last_print=now
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        error=str(exc)
        print(f'BLAD: {error}')
    finally:
        camera.stop.set()
        camera.thread.join(timeout=1)
        cv2.destroyAllWindows()
        def summary(values):
            return {'median':float(np.median(values)),'p95':float(np.percentile(values,95)),
                    'max':float(max(values))} if values else None
        report={'error':error,'age_ms':summary(ages),'decoder_ms':summary(costs),
                'status_observations':dict(counts),'log':rows,
                'note':'Browser OBS -> camera reception. Does not establish game freshness.'}
        path=Path('obs_marker_results_'+time.strftime('%Y%m%d_%H%M%S')+'.json')
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PODSUMOWANIE:',json.dumps({k:v for k,v in report.items() if k!='log'},indent=2))
        print(f'Zapisano: {path}')
    if error:
        raise SystemExit(1)


if __name__=='__main__':
    main()
