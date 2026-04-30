# game/map_detector.py
import os
import cv2
import numpy as np
from typing import List, Tuple, Dict

TEMPLATE_FOLDER = os.path.join("game", "markersTemplate")

def load_template(index: int) -> np.ndarray:
    """
    Wczytuje template o numerze index (1..20).
    Zwraca tablicę grayscale.
    """
    path = os.path.join(TEMPLATE_FOLDER, f"MarkerTemplate{index}.png")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if tpl is None:
        raise Exception(f"Failed to load template {path}")
    return tpl

def find_templates_in_map(img_map_rgb: np.ndarray,
                          template_indices: List[int],
                          method=cv2.TM_CCOEFF_NORMED,
                          threshold: float = 0.99) -> List[Dict]:
    """
    Szuka wszystkich wystąpień zadanych template'ów w obrazie mapy.
    - img_map_rgb: numpy array w formacie RGB (np.array(PIL.Image))
    - template_indices: lista numerów template'ów, np. [1,2,3]
    Zwraca listę słowników:
      { "template":idx, "x":x, "y":y, "score":score, "w":w,"h":h }
    gdzie x,y to współrzędne lewego górnego rogu dopasowania w układzie img_map.
    """
    out = []
    # grayscale screenshot
    screenshot_gray = cv2.cvtColor(img_map_rgb, cv2.COLOR_RGB2GRAY)

    for idx in template_indices:
        try:
            tpl = load_template(idx)
        except FileNotFoundError:
            continue
        h, w = tpl.shape[:2]
        result = cv2.matchTemplate(screenshot_gray, tpl, method)
        # znajdź wszystkie lokalizacje powyżej threshold
        loc = np.where(result >= threshold)
        # loc[0] -> y coords, loc[1] -> x coords
        for (y, x) in zip(*loc):
            score = float(result[y, x])
            out.append({"template": idx, "x": int(x), "y": int(y), "score": score, "w": w, "h": h})
    # Opcjonalnie sortuj po score (malejąco)
    out.sort(key=lambda r: r["score"], reverse=True)
    return out

def find_best_for_template(img_map_rgb: np.ndarray, template_index: int, threshold: float=0.99):
    res = find_templates_in_map(img_map_rgb, [template_index], threshold=threshold)
    return res[0] if res else None
