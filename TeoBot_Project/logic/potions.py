import time
from typing import List, Dict
from game.input_sender import send_key
from config.settings import Potion_GCD

class PotionLogic:
    """
    Logika potionów (HP / Mana).
    - update(data) przyjmuje listę słowników:
      { "type":"hp"|"mana", "key", "%", "cd", "last_used"(opcjonalne) }
    - use(hwnd, hp, mana) wykonuje użycie pierwszego dopasowanego potiona.
    """

    def __init__(self):
        self.potions: List[Dict] = []
        self.last_potion_gcd = 0.0

    def update(self, data: List[Dict]):
        out = []
        for it in data:
            o = {
                "type": it.get("type", "mana"),
                "key": it.get("key", ""),
                "percent": float(it.get("%", it.get("percent", 0.0))),
                "cd": float(it.get("cd", 0.0)),
                "last_used": float(it.get("last_used", 0.0)) if it.get("last_used") is not None else 0.0
            }
            out.append(o)
        # sortuj: najpierw hp potem mana (można zmienić)
        out.sort(key=lambda x: (x["type"], x["percent"]))
        self.potions = out

    def use(self, hwnd, hp: float, mana: float):
        now = time.time()
        if now - self.last_potion_gcd < Potion_GCD:
            return

        for p in self.potions:
            if p["type"] == "hp" and hp < p["percent"]:
                if now - p["last_used"] > p["cd"]:
                    send_key(hwnd, p["key"])
                    p["last_used"] = now
                    self.last_potion_gcd = now
                    return
            if p["type"] == "mana" and mana < p["percent"]:
                if now - p["last_used"] > p["cd"]:
                    send_key(hwnd, p["key"])
                    p["last_used"] = now
                    self.last_potion_gcd = now
                    return

    def reset_last_used(self):
        for p in self.potions:
            p["last_used"] = 0.0

    def get_state(self):
        return {"potions": self.potions}

