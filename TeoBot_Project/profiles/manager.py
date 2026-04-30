import json
import os
from profiles.defaults import (
    DEFAULT_OFFENSIVE,
    DEFAULT_HEALING,
    DEFAULT_POTIONS,
    DEFAULT_SUPPORT
)
from config.settings import PROFILE_FILE


class ProfileManager:
    def __init__(self):
        self.profiles = {}
        self.current = None
        self.current_name = None
        self.load()

    # === load profiles from file or defaults ===
    def load(self):
        if os.path.exists(PROFILE_FILE):
            try:
                with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                    self.profiles = json.load(f)
            except:
                self.profiles = {}

        if "Default" not in self.profiles:
            self.profiles["Default"] = {
                "offensive": DEFAULT_OFFENSIVE,
                "healing": DEFAULT_HEALING,
                "potions": DEFAULT_POTIONS,
                "support": DEFAULT_SUPPORT,
            }

        self.current_name = "Default"
        self.current = self.profiles["Default"]

    # === save all profiles ===
    def save_all(self):
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.profiles, f, indent=2, ensure_ascii=False)

    # === set active profile ===
    def set_current(self, name):
        if name in self.profiles:
            self.current_name = name
            self.current = self.profiles[name]

    # === create / delete / duplicate ===
    def new_profile(self, name):
        self.profiles[name] = {"offensive": [], "healing": [], "potions": [], "support": []}

    def delete(self, name):
        if name in self.profiles:
            del self.profiles[name]

    def duplicate(self, name, new_name):
        import copy
        self.profiles[new_name] = copy.deepcopy(self.profiles[name])

