"""Bounded deterministic OCR memoization by exact pixels and segmentation mode."""
from collections import OrderedDict
from types import SimpleNamespace
import numpy as np

class PixelCache:
    def __init__(self,limit=128,max_bytes=8*1024*1024):
        self.limit=limit;self.max_bytes=max_bytes
        self.entries=OrderedDict();self.bytes=0;self.hits=0;self.misses=0
    def recognize(self,image,psm,recognize):
        image=np.ascontiguousarray(image,dtype=np.uint8)
        key=(image.shape,psm,image.tobytes())
        if self.limit and key in self.entries:
            self.hits+=1;self.entries.move_to_end(key)
            texts,scores=self.entries[key]
        else:
            self.misses+=1
            result=recognize(image,psm)
            texts,scores=tuple(result.txts),tuple(result.scores)
            size=len(key[2])
            if self.limit and size<=self.max_bytes:
                while self.entries and (len(self.entries)>=self.limit or self.bytes+size>self.max_bytes):
                    old,_=self.entries.popitem(last=False);self.bytes-=len(old[2])
                self.entries[key]=(texts,scores);self.bytes+=size
        return SimpleNamespace(txts=list(texts),scores=list(scores))
