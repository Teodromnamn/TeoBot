import time
import threading
import gc
import win32gui
import cv2
import numpy as np

from game.window_capture import read_hp_mana
from game.window_capture import screenshot_window
from config.settings import WINDOW_NAME, end_time
from logic.cavebot import Cavebot



class BotEngine:
    """
    BotEngine jest "mózgiem" bota:
    - Łączy wszystkie logiczne moduły (healing, potions, offensive, support).
    - Odpala pętlę bota w osobnym wątku.
    - Jest kontrolowany przez UI (start/stop/pause).
    - Aktualizuje UI przez callbacki przekazane z tkinter.
    """

    def __init__(self, logic_modules, update_ui_callback, update_status_callback):
        self.healing = logic_modules["healing"]
        self.potions = logic_modules["potions"]
        self.offensive = logic_modules["offensive"]
        self.support = logic_modules["support"]

        # po utworzeniu self.logic ...
        self.cavebot = Cavebot(
            map_rect=(1761, 36, 1866, 144),   # TWOJE współrzędne minimapy
        )


        # UI callbacki
        self.update_ui = update_ui_callback        # update HP/MP labels
        self.update_status = update_status_callback

        # engine state
        self.running = False
        self.rotation_enabled = False
        self.thread = None
        self.cavebot_enabled = False

    # ----------------------------------------------------
    # PUBLIC API — wywoływane przez UI
    # ----------------------------------------------------

    def start(self, profile_name):
        if self.running:
            self.update_status("Bot already running.")
            return

        # sprawdź licencję
        if time.time() > end_time:
            self.update_status("End of LICENSE.")
            return

        window_name = WINDOW_NAME.format(profile=profile_name)
        
        hwnd = win32gui.FindWindow(None, window_name)

        if not hwnd:
            self.update_status(f"Window not found: {window_name}")
            return

        # start
        self.hwnd = hwnd
        self.window_name = window_name

        self.running = True
        self.rotation_enabled = False

        # reset cooldownów
        self.healing.reset_last_used()
        self.potions.reset_last_used()
        self.offensive.reset_last_used()
        self.support.reset_last_used()

        self.update_status(f"Running ({profile_name}) — rotation paused")

        # start thread
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.rotation_enabled = False
        self.update_status("Stopped.")
        self.cavebot_enabled = False

    def toggle_rotation(self):
        if not self.running:
            return

        self.rotation_enabled = not self.rotation_enabled

        if self.rotation_enabled:
            self.update_status("Rotation ENABLED")
        else:
            self.update_status("Rotation PAUSED")
            
    def start_cavebot(self):
        self.cavebot_enabled = True
    
    def stop_cavebot(self):
        self.cavebot_enabled = False
    
    def cavebot_set_sequence(self, seq):
        self.cavebot.set_sequence(seq)


    # ----------------------------------------------------
    # INTERNAL LOOP
    # ----------------------------------------------------
    def _loop(self):
        """Główna pętla bota — działa w osobnym wątku."""
        while self.running:
            try:
                # read HP/MP
                img_Full = screenshot_window(self.window_name)
                '''
                # lewo gora 1761,36 - prawy dol 1866,144
                MAP_RECT = (1761,36,1866,144)
                
                img_Full.save("full.png", "PNG")
                img_map = img_Full.crop(MAP_RECT)
                img_map.save("mapa.png", "PNG")
                img_map_np = np.array(img_map)
                template_path = "game\markersTemplate\MarkerTemplate1.png"
                template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                screenshot_gray = cv2.cvtColor(img_map_np, cv2.COLOR_RGB2GRAY)
    
                # Wykrywanie template'u w zrzucie ekranu
                result = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
                threshold=0.99
                # Szukamy dopasowań powyżej zadanego progu
                loc = np.where(result >= threshold)
                
                # Zwracamy pozycje dopasowanych template'ów
                print(loc)
                '''
                

                hp, mana = read_hp_mana(img_Full)
                self.update_ui(hp, mana)

                # potions
                self.potions.use(self.hwnd, hp, mana)

                # healing
                self.healing.use(self.hwnd, hp, mana, img_Full)

                # offensive + support (only if rotation enabled)
                if self.rotation_enabled:
                    self.offensive.use(self.hwnd, mana)
                    self.support.use(self.hwnd)
                
                # === CAVEBOT MODULE ===
                if self.cavebot_enabled:
                    msg = self.cavebot.step(img_Full, self.hwnd)
                    if msg:
                        print("[CAVEBOT]", msg)


                time.sleep(0.2)
                gc.collect()

            except Exception as e:
                print("Engine error:", e)
                time.sleep(0.2)

