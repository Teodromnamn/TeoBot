import time
from typing import List, Dict
from game.input_sender import send_key
from config.settings import Offensive_GCD, Potion_GCD

class OffensiveLogic:
    """
    Zarządza rotacją ofensywną.
    - update(data) przyjmuje listę słowników:
      { "name","key","priority","mana_cost","cd","type" }
    - use(hwnd, mana) wykonuje rotację (z uwzględnieniem GCDów i last_used).
    """

    def __init__(self):
        self.spells: List[Dict] = []
        self.last_offensive_gcd = 0.0
        self.last_potion_gcd = 0.0

    def update(self, data: List[Dict]):
        """Wczytaj dane z UI/profilu (lista słowników)."""
        # Normalizuj i dopisz pole last_used jeśli brak
        out = []
        for it in data:
            o = {
                "name": it.get("name", ""),
                "key": it.get("key", ""),
                "priority": int(it.get("priority", 99)),
                "mana_cost": float(it.get("mana_cost", 0.0)),
                "cd": float(it.get("cd", 0.0)),
                "type": it.get("type", "spell"),
                "last_used": float(it.get("last_used", 0.0)) if it.get("last_used") is not None else 0.0
            }
            out.append(o)
        # sort by priority (lower -> earlier)
        out.sort(key=lambda x: x["priority"])
        self.spells = out

    def use(self, hwnd, mana: float):
        """Spróbuj użyć pierwszego dostępnego zaklęcia/runy z rotacji."""
        now = time.time()
        if now - self.last_offensive_gcd < Offensive_GCD:
            return  # GCD ofensywny nie minął

        for spell in self.spells:
            if mana >= spell["mana_cost"]:
                if now - spell["last_used"] > spell["cd"]:
                    # runy mogą mieć wspólny GCD potiona - utrzymane z oryginału
                    if spell["type"] == "rune":
                        if now - self.last_potion_gcd > Potion_GCD:
                            send_key(hwnd, spell["key"])
                            spell["last_used"] = now
                            self.last_potion_gcd = now
                            self.last_offensive_gcd = now
                            # nie przerywamy - można spamować po priorytetach, ale zostawiam break podobnie jak w oryginale
                            #break
                    else:
                        send_key(hwnd, spell["key"])
                        spell["last_used"] = now
                        self.last_offensive_gcd = now
                        #break

    def reset_last_used(self):
        for s in self.spells:
            s["last_used"] = 0.0

    def get_state(self):
        return {"spells": self.spells}

