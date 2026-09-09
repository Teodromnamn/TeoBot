"""Automatic HP/MP bar detection and numeric OCR."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

Rect = Tuple[int, int, int, int]


@dataclass(frozen=True)
class BarReading:
    current: int
    maximum: int
    percent: float
    rect: Rect
    raw_text: str
    confidence: float


@dataclass(frozen=True)
class HpMpReading:
    hp: Optional[BarReading]
    mp: Optional[BarReading]
    annotated_image: Image.Image


@dataclass
class _Candidate:
    current: int
    maximum: int
    raw_text: str
    ocr_confidence: float
    text_rect: Rect
    rect: Rect
    hp_colour_score: float = 0.0
    mp_colour_score: float = 0.0

    @property
    def percent(self) -> float:
        return 100.0 * self.current / self.maximum


_READER: Any = None
_VALUE_RE = re.compile(r"(?<!\d)(\d{1,9})\s*/\s*(\d{1,9})(?!\d)")


def _get_reader() -> Any:
    global _READER
    if _READER is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "Brak RapidOCR. Zainstaluj: pip install rapidocr onnxruntime"
            ) from exc
        _READER = RapidOCR()
    return _READER


def _as_rgb(image: Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGB"))
    array = np.asarray(image)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError("image must be a PIL image or an RGB/RGBA numpy array")
    return np.ascontiguousarray(array[:, :, :3].astype(np.uint8, copy=False))


def _ocr_rect(points: Sequence[Sequence[float]], width: int, height: int) -> Rect:
    xs, ys = zip(*((float(p[0]), float(p[1])) for p in points))
    x1, y1 = max(0, int(min(xs))), max(0, int(min(ys)))
    x2, y2 = min(width, int(np.ceil(max(xs)))), min(height, int(np.ceil(max(ys))))
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def _normalise(text: str) -> str:
    table = str.maketrans({"|": "/", "\\": "/", "I": "1", "l": "1"})
    text = " ".join(text.translate(table).split())
    # Thousands separators: 2,776 / 2,850 -> 2776 / 2850.
    return re.sub(r"(?<=\d)[,.\s](?=\d)", "", text)


def _run_ocr(reader: Any, rgb: np.ndarray) -> list[tuple]:
    """Normalise RapidOCR and EasyOCR-compatible results."""
    if hasattr(reader, "readtext"):
        return list(reader.readtext(
            rgb, detail=1, paragraph=False, allowlist="0123456789/|Il,. ",
            text_threshold=0.35, low_text=0.20, link_threshold=0.20,
            mag_ratio=1.35,
        ))

    output = reader(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    boxes = getattr(output, "boxes", None)
    texts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)
    if boxes is None or texts is None or scores is None:
        return []
    return [(box, text, float(score)) for box, text, score in zip(boxes, texts, scores)]


def _same_line(left: tuple, right: tuple) -> bool:
    _, ly, _, lh = left[3]
    _, ry, _, rh = right[3]
    return abs((ly + lh / 2) - (ry + rh / 2)) <= 0.65 * max(lh, rh)


def _join_ocr_parts(parts: list[tuple]) -> list[tuple]:
    """Also support OCR returning ``123``, ``/``, ``456`` separately."""
    output = list(parts)
    ordered = sorted(parts, key=lambda item: (item[3][1], item[3][0]))
    for start in range(len(ordered)):
        group = [ordered[start]]
        for item in ordered[start + 1:]:
            previous = group[-1]
            px, _, pw, ph = previous[3]
            x, _, _, h = item[3]
            gap = x - (px + pw)
            if gap > 2.2 * max(ph, h):
                break
            if gap < -max(ph, h) or not _same_line(previous, item):
                continue
            group.append(item)
            if len(group) > 4:
                break
            text = " ".join(part[1] for part in group)
            if "/" not in _normalise(text):
                continue
            x1 = min(p[3][0] for p in group)
            y1 = min(p[3][1] for p in group)
            x2 = max(p[3][0] + p[3][2] for p in group)
            y2 = max(p[3][1] + p[3][3] for p in group)
            output.append((None, text, min(p[2] for p in group), (x1, y1, x2-x1, y2-y1)))
    return output


def _find_bar_rect(rgb: np.ndarray, text_rect: Rect) -> Rect:
    """Find a rectangular outline around the OCR text, with safe fallback."""
    image_h, image_w = rgb.shape[:2]
    tx, ty, tw, th = text_rect
    cx, cy = tx + tw / 2, ty + th / 2
    # Bars in Tibia-like clients can be many times wider than their text.
    pad_x = min(image_w // 2, max(120, int(tw * 8.0)))
    pad_y = max(10, int(th * 2.0))
    rx1, ry1 = max(0, tx-pad_x), max(0, ty-pad_y)
    rx2, ry2 = min(image_w, tx+tw+pad_x), min(image_h, ty+th+pad_y)
    gray = cv2.cvtColor(rgb[ry1:ry2, rx1:rx2], cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 45, 130)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    choices = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        gx, gy = rx1+x, ry1+y
        contains_text = (
            gx <= tx + 2 and gx + w >= tx + tw - 2
            and gy <= cy <= gy + h
        )
        if not contains_text:
            continue
        if w < max(50, tw*1.12) or h < max(5, th*0.45):
            continue
        if w/max(h, 1) < 2.5 or h > th*2.8:
            continue
        # Prefer an outline with the text-like height and a wide horizontal span.
        height_error = abs(h - th*1.15) / max(th, 1)
        width_bonus = min(w / max(tw, 1), 12.0) * 0.035
        score = height_error - width_bonus
        choices.append((score, (gx, gy, w, h)))
    if choices:
        return min(choices, key=lambda item: item[0])[1]
    mx, my = max(8, tw//4), max(3, th//3)
    x1, y1 = max(0, tx-mx), max(0, ty-my)
    x2, y2 = min(image_w, tx+tw+mx), min(image_h, ty+th+my)
    return x1, y1, x2-x1, y2-y1


def _colour_scores(rgb: np.ndarray, rect: Rect) -> tuple[float, float]:
    x, y, w, h = rect
    ih, iw = rgb.shape[:2]
    mx, my = max(4, w//10), max(2, h//3)
    roi = rgb[max(0, y-my):min(ih, y+h+my), max(0, x-mx):min(iw, x+w+mx)]
    hue, saturation, value = cv2.split(cv2.cvtColor(roi, cv2.COLOR_RGB2HSV))
    colourful = (saturation >= 70) & (value >= 45)
    red = colourful & ((hue <= 12) | (hue >= 172))
    green = colourful & (hue >= 35) & (hue <= 88)
    blue = colourful & (hue >= 88) & (hue <= 135)
    purple = colourful & (hue >= 130) & (hue <= 171)
    total = max(1, colourful.size)
    hp_colour = red | green
    mp_colour = blue | purple
    return float(hp_colour.sum()/total), float(mp_colour.sum()/total)


def _extract_candidates(rgb: np.ndarray, ocr_result: Sequence) -> list[_Candidate]:
    ih, iw = rgb.shape[:2]
    parts = []
    for item in ocr_result:
        if len(item) >= 3:
            points, text, confidence = item[:3]
            parts.append((points, str(text), float(confidence), _ocr_rect(points, iw, ih)))
    candidates, seen = [], set()
    for _, raw_text, confidence, text_rect in _join_ocr_parts(parts):
        match = _VALUE_RE.search(_normalise(raw_text))
        if not match:
            continue
        current, maximum = map(int, match.groups())
        if maximum <= 0 or current < 0 or current > maximum*1.05:
            continue
        key = (current, maximum, text_rect)
        if key in seen:
            continue
        seen.add(key)
        rect = _find_bar_rect(rgb, text_rect)
        red, blue = _colour_scores(rgb, rect)
        candidates.append(_Candidate(current, maximum, raw_text, confidence,
                                     text_rect, rect, red, blue))
    return candidates


def _select(candidates: list[_Candidate]):
    if not candidates:
        return None, None
    pairs = []
    for index, first in enumerate(candidates):
        for second in candidates[index + 1:]:
            ax, ay, aw, ah = first.rect
            bx, by, bw, bh = second.rect
            acx, acy = ax + aw/2, ay + ah/2
            bcx, bcy = bx + bw/2, by + bh/2
            mean_w, mean_h = max(1, (aw+bw)/2), max(1, (ah+bh)/2)
            size_error = abs(np.log(max(aw, 1)/max(bw, 1))) + abs(np.log(max(ah, 1)/max(bh, 1)))

            # Stacked layout: HP above MP.
            vertical_alignment = abs(acx-bcx)/mean_w
            vertical_gap = abs(by-(ay+ah))/mean_h if ay <= by else abs(ay-(by+bh))/mean_h
            if vertical_alignment <= 0.40 and vertical_gap <= 5.0:
                hp, mp = (first, second) if ay <= by else (second, first)
                geometry = vertical_alignment + 0.22*vertical_gap + 0.30*size_error
                pairs.append((geometry, hp, mp))

            # Side-by-side layout: HP on the left, MP on the right.
            horizontal_alignment = abs(acy-bcy)/mean_h
            horizontal_gap = abs(bx-(ax+aw))/mean_w if ax <= bx else abs(ax-(bx+bw))/mean_w
            if horizontal_alignment <= 1.25 and horizontal_gap <= 3.0:
                hp, mp = (first, second) if ax <= bx else (second, first)
                geometry = horizontal_alignment + 0.22*horizontal_gap + 0.30*size_error
                pairs.append((geometry, hp, mp))

    if pairs:
        def pair_score(item):
            geometry, hp, mp = item
            colour_support = hp.hp_colour_score + mp.mp_colour_score
            confidence = hp.ocr_confidence + mp.ocr_confidence
            width_bonus = np.log1p(hp.rect[2] + mp.rect[2])
            return geometry - 1.6*colour_support - 0.22*confidence - 0.035*width_bonus
        _, hp, mp = min(pairs, key=pair_score)
        return hp, mp

    # Last-resort fallback for a non-standard, non-paired layout.
    hp = max(candidates, key=lambda c: c.hp_colour_score + 0.12*c.ocr_confidence)
    remaining = [c for c in candidates if c is not hp]
    mp = max(remaining, key=lambda c: c.mp_colour_score + 0.12*c.ocr_confidence) if remaining else None
    return hp, mp


def _public(candidate: Optional[_Candidate], kind: str) -> Optional[BarReading]:
    if candidate is None:
        return None
    colour = candidate.hp_colour_score if kind == "HP" else candidate.mp_colour_score
    confidence = min(1.0, 0.75*candidate.ocr_confidence + 2.5*colour)
    return BarReading(candidate.current, candidate.maximum, candidate.percent,
                      candidate.rect, candidate.raw_text, confidence)


def detect_hp_mp(
    image: Image.Image | np.ndarray,
    *,
    reader: Any = None,
    draw_boxes: bool = True,
    min_ocr_confidence: float = 0.20,
) -> HpMpReading:
    """Locate HP/MP anywhere and read current, maximum and percentage.

    PIL input is recommended. Numpy input must use RGB channel order. Pass an
    existing OCR reader to avoid recreating the model outside this module.
    """
    rgb = _as_rgb(image)
    ocr = reader or _get_reader()
    result = _run_ocr(ocr, rgb)
    result = [item for item in result if len(item) >= 3 and float(item[2]) >= min_ocr_confidence]
    hp_candidate, mp_candidate = _select(_extract_candidates(rgb, result))

    annotated = rgb.copy()
    if draw_boxes:
        for label, candidate in (("HP", hp_candidate), ("MP", mp_candidate)):
            if candidate is None:
                continue
            x, y, w, h = candidate.rect
            cv2.rectangle(annotated, (x, y), (x+w, y+h), (255, 0, 0), 2)
            text = f"{label}: {candidate.current}/{candidate.maximum} ({candidate.percent:.1f}%)"
            cv2.putText(annotated, text, (x, max(14, y-5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 0), 1, cv2.LINE_AA)

    return HpMpReading(_public(hp_candidate, "HP"), _public(mp_candidate, "MP"),
                       Image.fromarray(annotated))
