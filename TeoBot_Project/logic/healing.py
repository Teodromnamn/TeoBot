import time
from typing import List, Dict
from game.input_sender import send_key
from game.window_capture import read_hp_mana
from config.settings import Heal_GCD, HP_RECT_SIO, MANA_RECT_SIO

class HealingLogic:
    """
    Zarządza logiką leczenia.
    - update(data) przyjmuje listę słowników:
      { "name","key","hp%","mana_cost","cd","last_used"(opcjonalnie) }
    - use(hwnd, hp, mana, window_name) spróbuje użyć leczenia.
    """

    def __init__(self):
        self.heals: List[Dict] = []
        self.last_heal_gcd = 0.0

    def update(self, data: List[Dict]):
        out = []
        for it in data:
            o = {
                "name": it.get("name", ""),
                "key": it.get("key", ""),
                "hp%": float(it.get("hp%", 0.0)),
                "mana_cost": float(it.get("mana_cost", 0.0)),
                "cd": float(it.get("cd", 0.0)),
                "last_used": float(it.get("last_used", 0.0)) if it.get("last_used") is not None else 0.0
            }
            out.append(o)
        # sortuj po progu hp% rosnąco (najniższe najpierw)
        out.sort(key=lambda x: x["hp%"])
        self.heals = out

    def use(self, hwnd, hp: float, mana: float, img_Full):
        """
        W oryginalnym kodzie jest mechanika 'sio' (sub-window) — jeśli nazwa czaru zawiera 'sio',
        odczytujemy oddzielny pasek HP/MP.
        """
        now = time.time()
        if now - self.last_heal_gcd < Heal_GCD:
            return

        # najpierw sprawdź czy mamy sio-holy spells i pobierz ich hp/mana
        hp_sio = None
        mana_sio = None
        for h in self.heals:
            if "sio" in h["name"].lower():
                try:
                    hp_sio, mana_sio = read_hp_mana(img_Full, HP_RECT_SIO, MANA_RECT_SIO)
                except Exception:
                    # jeśli nie uda się odczytać subsekcji — ignorujemy sio
                    hp_sio = None
                    mana_sio = None
                break

        # standardowe leczenie (bez sio)
        for h in self.heals:
            if "sio" in h["name"].lower():
                continue
            if hp <= h["hp%"] and mana >= h["mana_cost"]:
                if now - h["last_used"] > h["cd"]:
                    send_key(hwnd, h["key"])
                    h["last_used"] = now
                    self.last_heal_gcd = now
                    return  # wykonujemy jeden heal i wychodzimy

        # leczenie dla sio (jeśli było odczytane)
        if hp_sio is not None:
            for h in self.heals:
                if "sio" in h["name"].lower():
                    if hp_sio <= h["hp%"] and mana_sio >= h["mana_cost"]:
                        if now - h["last_used"] > h["cd"]:
                            send_key(hwnd, h["key"])
                            h["last_used"] = now
                            self.last_heal_gcd = now
                            return

    def reset_last_used(self):
        for h in self.heals:
            h["last_used"] = 0.0

    def get_state(self):
        return {"heals": self.heals}

