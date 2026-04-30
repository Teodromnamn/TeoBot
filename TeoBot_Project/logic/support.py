import time
from typing import List, Dict
from game.input_sender import send_key
from config.settings import Support_GCD

class SupportLogic:
    """
    Logika supportów (buffy / utility).
    - update(data) przyjmuje listę słowników:
      { "name","key","cd","enabled"(bool),"last_used"(opcjonalnie) }
    - use(hwnd) używa pierwszego aktywnego wsparcia, które nie jest na CD.
    """

    def __init__(self):
        self.supports: List[Dict] = []
        self.last_support_gcd = 0.0

    def update(self, data: List[Dict]):
        out = []
        for it in data:
            o = {
                "name": it.get("name", ""),
                "key": it.get("key", ""),
                "cd": float(it.get("cd", 0.0)),
                "enabled": bool(it.get("enabled", True)),
                "last_used": float(it.get("last_used", 0.0)) if it.get("last_used") is not None else 0.0
            }
            out.append(o)
        # sortuj: enabled najpierw
        out.sort(key=lambda x: x["enabled"], reverse=True)
        self.supports = out

    def use(self, hwnd):
        now = time.time()
        if now - self.last_support_gcd < Support_GCD:
            return

        for s in self.supports:
            if s["enabled"] and (now - s["last_used"] > s["cd"]):
                send_key(hwnd, s["key"])
                s["last_used"] = now
                self.last_support_gcd = now
                return

    def reset_last_used(self):
        for s in self.supports:
            s["last_used"] = 0.0

    def get_state(self):
        return {"supports": self.supports}

