"""Read separated glyphs independently; never use another counter as a label."""
import re
import cv2
import numpy as np


def groups(image):
    ink = image < 128
    edges = np.diff(np.r_[False, ink.any(axis=0), False].astype(np.int8))
    result = []
    for left, right in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        part = ink[:, left:right]
        rows = np.flatnonzero(part.any(axis=1))
        if len(rows):
            result.append(image[rows[0]:rows[-1]+1, left:right])
    return result


def read_digits(engine, image):
    parts = groups(image)
    if not parts or len(parts) > 8:
        return {'text':None, 'reason':'invalid_group_count'}
    texts = []
    for part in parts:
        if part.shape[0] < 6:
            return {'text':None, 'reason':'small_or_broken_glyph'}
        padded = cv2.copyMakeBorder(part, 16,16,16,16,cv2.BORDER_CONSTANT,value=255)
        # Two segmentation modes must independently return the same ONE digit.
        a = engine.recognize(padded, psm=10).txts[0].strip()
        b = engine.recognize(padded, psm=7).txts[0].strip()
        if not re.fullmatch('[0-9]', a) or a != b:
            return {'text':None, 'reason':'glyph_modes_disagree', 'raw':[a,b]}
        texts.append(a)
    return {'text':''.join(texts), 'reason':None, 'groups':len(parts)}


def is_slash(part):
    """A slash has a straight descending x(y) stroke; digits/parentheses don't."""
    ink = part < 128
    rows = np.flatnonzero(ink.any(axis=1))
    if len(rows) < 8 or part.shape[1] < 3:
        return False
    centers = np.array([np.flatnonzero(ink[y]).mean() for y in rows])
    slope, offset = np.polyfit(rows, centers, 1)
    error = np.max(np.abs(centers-(slope*rows+offset)))
    widths = np.array([np.count_nonzero(ink[y]) for y in rows])
    return bool(slope < -.18 and error < 1.8 and widths.max() <= max(4,part.shape[1]*.65))


def recover_ratio(engine, image):
    # A thin UI underline can connect all glyph columns. Remove at most two
    # bottom rows only when the terminal row spans most of the whole crop.
    clean = image.copy()
    rows = np.flatnonzero(np.any(clean < 128,axis=1))
    if len(rows) and np.count_nonzero(clean[rows[-1]] < 128) > image.shape[1]*.65:
        clean[max(0,rows[-1]-1):rows[-1]+1] = 255
    parts = [p for p in groups(clean) if p.shape[0] >= 6]
    slashes = [i for i,p in enumerate(parts) if is_slash(p)]
    if not slashes or slashes[0] == 0:
        return {'text':None, 'reason':'no_visual_separator'}
    index = slashes[0]
    # Read maximum only up to the first short/open suffix glyph. A complete
    # main ratio is required; arbitrary popup text must not be searched.
    height = parts[index].shape[0]
    right = []
    for part in parts[index+1:]:
        if part.shape[0] > height*1.25 or part.shape[0] < height*.65:
            return {'text':None,'reason':'unexpected_ratio_component'}
        padded = cv2.copyMakeBorder(part,16,16,16,16,cv2.BORDER_CONSTANT,value=255)
        a=engine.recognize(padded,psm=10).txts[0].strip()
        if a in ('(', ')'):
            break
        right.append(part)
    if not right:
        return {'text':None,'reason':'missing_maximum'}
    left = read_number(engine,join(parts[:index]))
    maximum = read_number(engine,join(right))
    if left['text'] is None or maximum['text'] is None:
        return {'text':None,'reason':'ratio_glyph_uncertain'}
    return {'text':left['text']+'/'+maximum['text'],'reason':None}


def read_number(engine,image):
    padded=cv2.copyMakeBorder(image,16,16,16,16,cv2.BORDER_CONSTANT,value=255)
    a=engine.recognize(padded,psm=7).txts[0].strip()
    b=engine.recognize(padded,psm=8).txts[0].strip()
    if re.fullmatch('[0-9]+',a) and a == b and len(a) == len(groups(image)):
        return {'text':a,'reason':None}
    return read_digits(engine,image)


def join(parts):
    height=max(p.shape[0] for p in parts)
    return np.concatenate([cv2.copyMakeBorder(p,height-p.shape[0],0,0,4,
                          cv2.BORDER_CONSTANT,value=255) for p in parts],axis=1)
