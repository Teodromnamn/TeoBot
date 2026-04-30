# logic/cavebot.py
import time
import json
import os
from typing import List

from game.map_detector import find_templates_in_map
from game.input_sender import click_at

import numpy as np


CAVEBOTS_FOLDER = "cavebots"

class Cavebot:
    """
    Zarządza listą markerów (kolejność), wyszukiwaniem na mapie i klikiem w sekwencji.
    """
    def __init__(self, map_rect: tuple):
        self.map_rect = map_rect  # (left, top, right, bottom) w koord. zrzutu okna
        self.sequence: List[int] = []  # lista template indices np [1,5,3]
        self.current_idx = 0
        self.threshold = 0.99
        self.arrival_radius = 10  # px - kiedy uznajemy że jesteśmy w celu
        os.makedirs(CAVEBOTS_FOLDER, exist_ok=True)

    def load_from_file(self, fname: str):
        path = os.path.join(CAVEBOTS_FOLDER, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.sequence = data.get("sequence", [])
        self.current_idx = 0

    def save_to_file(self, fname: str):
        path = os.path.join(CAVEBOTS_FOLDER, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sequence": self.sequence}, f, indent=2)

    def set_sequence(self, seq: List[int]):
        self.sequence = seq
        self.current_idx = 0

    def _maplocal_to_client(self, x_map: int, y_map: int) -> (int,int):
        """
        map_rect zawiera lewy i górny offset względem pełnego zrzutu okna (który zaczyna się od (0,0) window).
        Dla click_at potrzebujemy koordynatów klienta — po prostu używamy (map_left + x_map, map_top + y_map)
        jeśli screenshot zwraca pełne okno i współrzędne client == window client. W przypadku konieczności
        korekty (border/titlebar) trzeba to skorygować.
        """
        left, top, _, _ = self.map_rect
        client_x = left + x_map
        client_y = top + y_map
        return client_x, client_y

    def _is_arrived(self, found_x: int, found_y: int, map_w: int, map_h: int) -> bool:
        """
        Uznać że dotarliśmy, jeśli pozycja markera jest blisko środka mapy.
        """
        cx, cy = map_w // 2, map_h // 2
        dx = found_x + 0 - cx  # found_x to lewy górny rogu template, moglibyśmy użyć środka template
        dy = found_y + 0 - cy
        dist2 = dx*dx + dy*dy
        return dist2 <= (self.arrival_radius * self.arrival_radius)

    def step(self, full_frame, hwnd):
        """
        Jeden krok cavebota:
        - patrzy na aktualny marker w sekwencji,
        - jeśli go widzi -> clickuje w jego środek,
        - potem czeka do momentu dotarcia (w kolejnych wywołaniach step())
        - jeśli dotarcie -> przechodzi do następnego markera
        Zwraca informacje debug (np. "clicked marker 1") lub None.
        """
        if not self.sequence:
            return "empty sequence"

        map_img = full_frame.crop(self.map_rect)
        map_rgb = map_img.convert("RGB")
        map_np = np.array(map_rgb)
        
        curr_marker  = self.sequence[self.current_idx]
        # szukaj tylko tego template'u
        hits = find_templates_in_map(map_np, [curr_marker], threshold=self.threshold)

        if not hits:
            # jeśli nie ma markera, nic nie robimy
            return f"marker {curr_marker} not found"
        
        best = hits[0]

        cx = best["x"] + best["w"] // 2
        cy = best["y"] + best["h"] // 2

        map_w, map_h = map_img.size

        # --- ARRIVAL CHECK ---
        mx, my = map_w // 2, map_h // 2
        dx = cx - mx
        dy = cy - my

        if dx*dx + dy*dy <= self.arrival_radius**2:
            self.current_idx = (self.current_idx + 1) % len(self.sequence)
            return f"Arrived at marker {curr_marker}"

        # --- PRZELICZENIE KOORDYNAT ---
        ml, mt, _, _ = self.map_rect

        click_x = ml + cx
        click_y = mt + cy

        # --- CLICK ---
        click_at(hwnd, click_x, click_y)

        return f"Clicked marker {curr_marker}"
    

