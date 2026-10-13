"""Tibia Battle List: OCR names and approximate visual HP percentages."""
from dataclasses import dataclass, field
import re
import cv2
import numpy as np
from PIL import Image
from game.status_bar_detector import _as_rgb, _get_reader, _ocr_rect


@dataclass
class BattleListReading:
    rect: tuple | None
    entries: list = field(default_factory=list)
    status: str = "not_found"
    annotated_image: Image.Image | None = None


def _text(reader, rgb):
    if hasattr(reader, "readtext"):
        return reader.readtext(rgb, detail=1, paragraph=False)
    result = reader(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if result.boxes is None:
        return []
    return list(zip(result.boxes, result.txts, result.scores))


def detect_battle_list(image, *, reader=None, draw_boxes=True):
    rgb = _as_rgb(image)
    ih, iw = rgb.shape[:2]
    reader = reader if reader is not None else _get_reader()
    enlarged = cv2.resize(rgb, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    words = [(np.asarray(box)/2, text, score) for box,text,score in _text(reader, enlarged)]
    headers = [(box, text, score) for box, text, score in words
               if "battlelist" in re.sub(r"[^a-z]", "", text.lower())]
    annotated = rgb.copy()
    if not headers:
        return BattleListReading(None, status="header_not_found", annotated_image=Image.fromarray(annotated))
    box, _, _ = max(headers, key=lambda item: item[2])
    tx, ty, tw, th = _ocr_rect(box, iw, ih)
    edges = cv2.Canny(rgb, 25, 70)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 20, minLineLength=max(20, th*2), maxLineGap=4)
    vertical = [] if lines is None else [l for l in lines.reshape(-1, 4)
        if abs(int(l[0])-int(l[2])) <= 1 and min(l[1], l[3]) <= ty+th
        and max(l[1], l[3]) >= ty+2*th]
    lefts = [int(l[0]) for l in vertical if tx-3*th <= l[0] <= tx]
    rights = [int(l[0]) for l in vertical if tx+tw < l[0] < tx+24*th]
    if not rights and iw-tx < 24*th:
        rights = [iw-2]
    if not lefts or not rights:
        return BattleListReading(None, status="panel_edges_not_found", annotated_image=Image.fromarray(annotated))
    left, right = max(lefts), min(rights)
    # Scrollbar is an internal edge: prefer the outside edge of its narrow strip.
    near = [x for x in rights if right <= x <= right+2*th]
    right = max(near)
    top = max(0, ty-3)
    bottom = None
    for y in range(ty+2*th, min(ih-1, ty+int(ih*.65))):
        band = edges[max(0,y-1):y+2, left:right+1]
        coverage = np.any(band, axis=0)
        if coverage.mean() > .80 and coverage[:max(3,th)].mean() > .65:
            bottom = y+1
            break
    if bottom is None:
        return BattleListReading(None, status="panel_bottom_not_found", annotated_image=Image.fromarray(annotated))
    rect = (left, top, right-left+1, bottom-top+1)
    entries = []
    panel = cv2.resize(rgb[top:bottom+1,left:right+1], None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    words = [(np.asarray(box)/3 + np.array([left,top]), text, score)
             for box,text,score in _text(reader, panel)]
    for points, name, confidence in words:
        x,y,w,h = _ocr_rect(points, iw, ih)
        if not (left < x and x+w <= right and ty+th <= y+h/2 and y+h < bottom):
            continue
        if confidence < .4 or not re.search(r"[A-Za-z]", name):
            continue
        # The thin health track lies immediately below each name.
        best = None
        for row in range(y+h-2, min(bottom-1, y+h+max(8,h))):
            gray = cv2.cvtColor(rgb[row:row+1, x:right], cv2.COLOR_RGB2GRAY)[0]
            dark = gray < 45
            starts = np.flatnonzero(np.diff(np.r_[False,dark,False].astype(int)) == 1)
            ends = np.flatnonzero(np.diff(np.r_[False,dark,False].astype(int)) == -1)
            for start,end in zip(starts,ends):
                if end-start > (right-left)*.5 and (best is None or end-start > best[2]):
                    best = (x+int(start), row, int(end-start))
        if best is None:
            continue
        bx,by,bw = best
        # Inspect a few rows around the black track outline, exclude end caps.
        roi = rgb[max(y,by-3):min(bottom,by+4), bx+1:bx+bw-1]
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        fill = np.any((hsv[:,:,1] > 90) & (hsv[:,:,2] > 75), axis=0)
        percent = round(100*float(fill.mean()), 1)
        entry_rect = (left+2,y,right-left-3,min(bottom,y+h+8)-y)
        entries.append({"name": name.strip(), "hp_percent": percent,
                        "rect": entry_rect, "hp_rect": (bx,by-2,bw,5),
                        "name_confidence": float(confidence)})
    if draw_boxes:
        cv2.rectangle(annotated,(left,top),(right,bottom),(255,0,0),1)
        for entry in entries:
            x,y,w,h = entry["rect"]
            cv2.rectangle(annotated,(x,y),(x+w,y+h),(255,180,0),1)
            cv2.putText(annotated,f'{entry["name"]}: {entry["hp_percent"]}%',
                        (max(0,left-180),y+h),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,0,0),1)
    return BattleListReading(rect, entries, "ok" if entries else "no_readable_entries", Image.fromarray(annotated))
