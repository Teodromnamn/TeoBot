import json
import time
import win32gui
import win32ui
import ctypes
from PIL import Image
import numpy as np
import cv2
import signal
import gc
import keyboard  # pip install keyboard
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os

# ============================ TBD ============================
"""
1. UI - kafelki always on
2. Auto neck/ring
3. Profil niepowiazany z nickiem - mozliwe rozne rotacje
4. Rozne rozdzielczosci - mozliwosc definiowania okna hp/mp
5.      Aplikacja
            pyinstaller --onefile --noconsole --icon=Scout.ico TeoBot.py
6.      Licencje - ustawic date waznosci np
7. Spelle z listy
8. Odczyt HP/MP liczbowy
9. Rotacja - spam w kolejnosci zamiast czekac na CD (mozliwa redukcja cdka)
10. Wlaczanie rotacji za pomoca przycisku i np metoda toogle (klikam F11 to spamuje F11 co CD, klikam drugi raz i wylacza go z rotacji)
11. Dorobic default pod klase przy tworzeniu nowego profilu np opcaj wyboru
"""






# ============================ Bot Code ============================

# ----------------------- Bot Config -----------------------
HP_RECT = (196, 36, 680, 1)
MANA_RECT = (884, 36, 680, 1)
PROFILE_FILE = "profiles.json"
WINDOW_NAME = "Tibia - ProfilName"  # Will be replaced dynamically with profile name
# Określ datę, do której aplikacja ma działać (w formacie timestamp)
end_time = time.mktime((2025, 10, 25, 0, 0, 0, 0, 0, -1))  # 15 października 2025, 00:00:00

Heal_GCD = 1.1
Support_GCD = 2.1
Offensive_GCD = 2.1
Potion_GCD = 1.1

# ======= Defaults =======
DEFAULT_OFFENSIVE = [
    {"name": "exori amp kor", "key": "F5", "priority": 1, "mana_cost": 10.0, "cd": 14.0, "type": "spell"},
    {"name": "exori gran ico", "key": "F6", "priority": 2, "mana_cost": 15.0, "cd": 30.0, "type": "spell"},
    {"name": "exori gran", "key": "F7", "priority": 3, "mana_cost": 15.0, "cd": 6.0, "type": "spell"},
    {"name": "exori min", "key": "F8", "priority": 4, "mana_cost": 10.0, "cd": 6.0, "type": "spell"},
    {"name": "exori", "key": "F9", "priority": 5, "mana_cost": 5.0, "cd": 4.0, "type": "spell"},
]

DEFAULT_HEALING = [
    {"name": "exura gran ico", "key": "F1", "hp%": 15.0, "mana_cost": 0.0, "cd": 600.0},
    {"name": "exura med ico", "key": "F2", "hp%": 95.0, "mana_cost": 0.0, "cd": 1.0},
]

DEFAULT_POTIONS = [
    {"type": "mana", "key": "F3", "%": 90.0, "cd": 1.0},
    {"type": "hp", "key": "F4", "%": 80.0, "cd": 1.0},
]

DEFAULT_SUPPORT = [
    {"name": "utura gran", "key": "F10", "cd": 60.0, "enabled": True},
    {"name": "utito tempo", "key": "F10", "cd": 10.0, "enabled": False},
]

PROFILE_FILE = "profiles.json"
CHECKED = "☑"
UNCHECKED = "☐"

# ----------------------- Functions -----------------------

def screenshot_window(window_name):
    hwnd = win32gui.FindWindow(None, window_name)
    if not hwnd:
        raise Exception(f"Nie znaleziono okna: {window_name}")
    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bot - top
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
    saveDC.SelectObject(saveBitMap)
    PW_RENDERFULLCONTENT = 2
    ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    win32gui.DeleteObject(saveBitMap.GetHandle())
    return img

def calculate_bar_percentage(crop):
    arr = np.array(crop)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    mask = (s > 50) & (v > 50)
    filled = np.sum(mask)
    total = arr.shape[0] * arr.shape[1]
    percent = (filled / total) * 100
    return percent

def read_hp_mana(window_name, hp_rect, mana_rect):
    img = screenshot_window(window_name)
    x, y, w, h = hp_rect
    hp_crop = img.crop((x, y, x + w, y + h))
    hp_percent = calculate_bar_percentage(hp_crop)
    x, y, w, h = mana_rect
    mana_crop = img.crop((x, y, x + w, y + h))
    mana_percent = calculate_bar_percentage(mana_crop)
    return hp_percent, mana_percent

def send_key(hwnd, key):
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    if key == " " or key == "spacja":
        vk = 0x20
    elif key == "F1":
        vk = 0x70
    elif key == "F2":
        vk = 0x71
    elif key == "F3":
        vk = 0x72
    elif key == "F4":
        vk = 0x73
    elif key == "F5":
        vk = 0x74
    elif key == "F6":
        vk = 0x75
    elif key == "F7":
        vk = 0x76
    elif key == "F8":
        vk = 0x77
    elif key == "F9":
        vk = 0x78
    elif key == "F10":
        vk = 0x79
    elif key == "F11":
        vk = 0x7A
    elif key == "F12":
        vk = 0x7B
    else:
        vk = ord(key.upper())

    win32gui.PostMessage(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, WM_KEYUP, vk, 0)


# ======= Dialog for add/edit =======
class ItemDialog(tk.Toplevel):
    def __init__(self, parent, title, schema, data=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.grab_set()
        self.resizable(False, False)
        self.schema = schema  # list of tuples (field_name, widget_type, options)
        self.values = {} if data is None else data.copy()
        self.widgets = {}
        self.result = None
        self._build()
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(padx=8, pady=8)

        for i, (field, wtype, opts) in enumerate(self.schema):
            ttk.Label(frm, text=field).grid(row=i, column=0, sticky="w", padx=4, pady=4)
            val = self.values.get(field, opts.get("default", ""))
            if wtype == "entry":
                e = ttk.Entry(frm)
                e.insert(0, str(val))
                e.grid(row=i, column=1, padx=4, pady=4)
                self.widgets[field] = e
            elif wtype == "spin_int":
                minv, maxv = opts.get("range", (0, 100))
                sb = ttk.Spinbox(frm, from_=minv, to=maxv, width=6)
                sb.delete(0, "end")
                sb.insert(0, str(val if val != "" else opts.get("default", minv)))
                sb.grid(row=i, column=1, padx=4, pady=4)
                self.widgets[field] = sb
            elif wtype == "spin_float":
                # use entry but validate as float
                e = ttk.Entry(frm)
                e.insert(0, str(val if val != "" else opts.get("default", "")))
                e.grid(row=i, column=1, padx=4, pady=4)
                self.widgets[field] = e
            elif wtype == "combo":
                cb = ttk.Combobox(frm, values=opts.get("values", []), state="readonly")
                default = val if val != "" else opts.get("default", opts.get("values", [])[0] if opts.get("values") else "")
                cb.set(default)
                cb.grid(row=i, column=1, padx=4, pady=4)
                self.widgets[field] = cb
            elif wtype == "check":
                var = tk.BooleanVar(value=bool(val if val != "" else opts.get("default", False)))
                chk = ttk.Checkbutton(frm, variable=var)
                chk.var = var
                chk.grid(row=i, column=1, padx=4, pady=4, sticky="w")
                self.widgets[field] = var

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left")

    def _on_ok(self):
        out = {}
        # validation
        for field, wtype, opts in self.schema:
            widget = self.widgets[field]
            if wtype == "check":
                out[field] = bool(widget.get())
                continue
            raw = widget.get().strip()
            # required check
            if opts.get("required") and raw == "":
                messagebox.showerror("Błąd", f"Pole '{field}' jest wymagane.")
                return
            if raw == "":
                out[field] = opts.get("default", "")
                continue
            # type conversions
            if wtype == "spin_int":
                try:
                    v = int(raw)
                except:
                    messagebox.showerror("Błąd", f"Pole '{field}' musi być liczbą całkowitą.")
                    return
                r = opts.get("range")
                if r and not (r[0] <= v <= r[1]):
                    messagebox.showerror("Błąd", f"'{field}' musi być w zakresie {r}.")
                    return
                out[field] = v
            elif wtype == "spin_float":
                try:
                    v = float(raw)
                except:
                    messagebox.showerror("Błąd", f"Pole '{field}' musi być liczbą.")
                    return
                r = opts.get("range")
                if r and not (r[0] <= v <= r[1]):
                    messagebox.showerror("Błąd", f"'{field}' musi być w zakresie {r}.")
                    return
                out[field] = v
            elif wtype == "combo":
                if opts.get("values") and raw not in opts.get("values"):
                    messagebox.showerror("Błąd", f"'{field}' musi być jedną z {opts.get('values')}.")
                    return
                out[field] = raw
            else:
                out[field] = raw
        self.result = out
        self.destroy()

# ======= Main UI =======
class BotUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Tibia Bot UI")
        self.profiles = {}
        self.current_profile_name = None
        self.current_profile = None

        self._load_profiles_file_or_defaults()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        # Tabs order: Profiles first
        self._create_profiles_tab()
        self._create_healing_tab()
        self._create_potions_tab()
        self._create_offensive_tab()
        self._create_support_tab()

        # Bot control footer
        self._create_HpMp_control()
        self._create_bot_control()

        # initial fill
        self._update_profile_combo()
        self._set_current_profile(self.current_profile_name)
        
        # Flaga, która będzie kontrolować stan uruchomienia bota
        self.running_bot = False
        self.rotation_enabled = False
        self.last_Heal_GCD = 0  # Dodajemy last_Heal_GCD jako atrybut klasy
        self.last_Support_GCD = 0  # Dodajemy last_Support_GCD jako atrybut klasy
        self.last_Offensive_GCD = 0  # Dodajemy last_Offensive_GCD jako atrybut klasy
        self.last_Potion_GCD = 0  # Dodajemy last_Potion_GCD jako atrybut klasy

    def _load_profiles_file_or_defaults(self):
        if os.path.exists(PROFILE_FILE):
            try:
                with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                    self.profiles = json.load(f)
            except Exception:
                self.profiles = {}
        if "Default" not in self.profiles:
            self.profiles["Default"] = {
                "offensive": DEFAULT_OFFENSIVE,
                "healing": DEFAULT_HEALING,
                "potions": DEFAULT_POTIONS,
                "support": DEFAULT_SUPPORT,
            }
        # set default current
        self.current_profile_name = "Default"
        self.current_profile = self.profiles[self.current_profile_name]

    # ---------- Profiles tab ----------
    def _create_profiles_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Profile")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=6, padx=6)
        ttk.Button(btn_frame, text="Nowy", command=self._new_profile).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Zapisz", command=self._save_current_profile).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kopiuj", command=self._copy_profile).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Usuń", command=self._delete_profile).pack(side="left", padx=4)

        load_frame = ttk.Frame(frame)
        load_frame.pack(fill="x", pady=4, padx=6)
        ttk.Label(load_frame, text="Wybierz profil:").pack(side="left", padx=(0,6))
        self.profile_combo = ttk.Combobox(load_frame, state="readonly", width=30)
        self.profile_combo.pack(side="left")
        ttk.Button(load_frame, text="Wczytaj", command=self._load_profile_from_combo).pack(side="left", padx=6)

        self.current_label = ttk.Label(frame, text=f"Aktualny profil: {self.current_profile_name}")
        self.current_label.pack(anchor="w", padx=6, pady=6)

    def _update_profile_combo(self):
        keys = list(self.profiles.keys())
        self.profile_combo["values"] = keys
        if self.current_profile_name in keys:
            self.profile_combo.set(self.current_profile_name)

    def _set_current_profile(self, name):
        if name not in self.profiles:
            return
        self.current_profile_name = name
        self.current_profile = self.profiles[name]
        self.current_label.config(text=f"Aktualny profil: {name}")
        self._update_all_trees()

    def _new_profile(self):
        name = simpledialog.askstring("Nowy profil", "Podaj nazwę profilu:")
        if not name:
            return
        if name in self.profiles and not messagebox.askyesno("Zastąpić?", "Profil już istnieje. Nadpisać?"):
            return
        self.profiles[name] = {"offensive": [], "healing": [], "potions": [], "support": []}
        self._update_profile_combo()
        self._set_current_profile(name)

    def _save_current_profile(self):
        if not self.current_profile_name:
            messagebox.showwarning("Brak profilu", "Brak aktywnego profilu do zapisu.")
            return
        # collect from trees
        self.profiles[self.current_profile_name] = {
            "offensive": self._collect_tree_data(self.off_tree, "offensive"),
            "healing": self._collect_tree_data(self.heal_tree, "healing"),
            "potions": self._collect_tree_data(self.pot_tree, "potions"),
            "support": self._collect_tree_data(self.sup_tree, "support"),
        }
        # write file
        try:
            with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Zapisano", f"Profil '{self.current_profile_name}' zapisany.")
            self._update_profile_combo()
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))

    def _copy_profile(self):
        if not self.current_profile_name:
            return
        name = simpledialog.askstring("Kopiuj profil", "Podaj nazwę nowego profilu:")
        if not name:
            return
        # deep copy
        self.profiles[name] = json.loads(json.dumps(self.profiles[self.current_profile_name]))
        self._update_profile_combo()
        self._set_current_profile(name)

    def _delete_profile(self):
        if not self.current_profile_name:
            return
        if not messagebox.askyesno("Usuń", f"Czy na pewno usunąć profil '{self.current_profile_name}'?"):
            return
        self.profiles.pop(self.current_profile_name, None)
        # save
        try:
            with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
        except:
            pass
        # pick any remaining or create Default
        if self.profiles:
            name = next(iter(self.profiles.keys()))
            self._set_current_profile(name)
        else:
            self.profiles["Default"] = {
                "offensive": DEFAULT_OFFENSIVE,
                "healing": DEFAULT_HEALING,
                "potions": DEFAULT_POTIONS,
                "support": DEFAULT_SUPPORT,
            }
            self._set_current_profile("Default")
        self._update_profile_combo()

    def _load_profile_from_combo(self):
        name = self.profile_combo.get()
        if not name:
            return
        self._set_current_profile(name)

    # ---------- Offensive tab ----------
    def _create_offensive_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Ofensywa")

        # Dodajemy ukrytą kolumnę "_last_used" jako ostatnia kolumnę
        cols = ("name", "key", "priority", "mana_cost", "cd", "type", "_last_used")
        self.off_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        # Widoczne kolumny
        for c in ("name", "key", "priority", "mana_cost", "cd", "type"):
            self.off_tree.heading(c, text=c.capitalize())
            self.off_tree.column(c, width=110)

        # Ukryta kolumna: width=0, minwidth=0, stretch=False
        self.off_tree.heading("_last_used", text="")
        self.off_tree.column("_last_used", width=0, minwidth=0, stretch=False)

        self.off_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btnf, text="Dodaj", command=self._add_off).pack(side="left", padx=3)
        ttk.Button(btnf, text="Edytuj", command=self._edit_off).pack(side="left", padx=3)
        ttk.Button(btnf, text="Usuń", command=lambda: self._remove_selected(self.off_tree)).pack(side="left", padx=3)

    def _add_off(self):
        schema = [
            ("name", "entry", {"required": False, "default": ""}),
            ("key", "entry", {"required": True}),
            ("priority", "spin_int", {"required": False, "default": 20, "range": (1, 20)}),
            ("mana_cost", "spin_float", {"required": True, "default": 0, "range": (0, 100)}),
            ("cd", "spin_float", {"required": True, "default": 1.0, "range": (0.0, 9999.0)}),
            ("type", "combo", {"required": True, "values": ["spell", "rune"], "default": "spell"}),
        ]
        dlg = ItemDialog(self.root, "Dodaj offensive", schema)
        if dlg.result:
            entry = dlg.result
            self.off_tree.insert(
                "", "end",
                values=(
                    entry.get("name",""),
                    entry.get("key",""),
                    int(entry.get("priority", 20)),
                    float(entry.get("mana_cost", 0)),
                    float(entry.get("cd", 0.0)),
                    entry.get("type","spell"),
                    0.0  # _last_used (ukryte)
                )
            )
            self._sort_offensive_tree()

    def _edit_off(self):
        sel = self.off_tree.selection()
        if not sel:
            messagebox.showinfo("Edytuj", "Zaznacz wpis do edycji.")
            return
        iid = sel[0]
        vals = self.off_tree.item(iid, "values")
        current = {
            "name": vals[0],
            "key": vals[1],
            "priority": int(vals[2]) if vals[2] != "" else 20,
            "mana_cost": float(vals[3]) if vals[3] != "" else 0,
            "cd": float(vals[4]) if vals[4] != "" else 1.0,
            "type": vals[5] if len(vals) > 5 else "spell",
        }
        last_used_hidden = float(vals[6]) if len(vals) > 6 and vals[6] != "" else 0.0

        schema = [
            ("name", "entry", {"required": False, "default": ""}),
            ("key", "entry", {"required": True}),
            ("priority", "spin_int", {"required": False, "default": current["priority"], "range": (1, 20)}),
            ("mana_cost", "spin_float", {"required": True, "default": current["mana_cost"], "range": (0, 100)}),
            ("cd", "spin_float", {"required": True, "default": current["cd"], "range": (0.0, 9999.0)}),
            ("type", "combo", {"required": True, "values": ["spell", "rune"], "default": current["type"]}),
        ]
        dlg = ItemDialog(self.root, "Edytuj offensive", schema, data=current)
        if dlg.result:
            entry = dlg.result
            self.off_tree.item(
                iid,
                values=(
                    entry.get("name",""),
                    entry.get("key",""),
                    int(entry.get("priority",20)),
                    float(entry.get("mana_cost",0)),
                    float(entry.get("cd",0.0)),
                    entry.get("type","spell"),
                    last_used_hidden  # zachowujemy ukryte last_used
                )
            )
            self._sort_offensive_tree()

    def _sort_offensive_tree(self):
        rows = []
        for iid in self.off_tree.get_children():
            v = self.off_tree.item(iid, "values")
            pr = int(v[2]) if v[2] != "" else 99
            rows.append((pr, iid, v))
        rows.sort(key=lambda x: x[0])

        # przebudowa z zachowaniem ukrytego pola
        for iid in self.off_tree.get_children():
            self.off_tree.delete(iid)
        for _, __, values in rows:
            self.off_tree.insert("", "end", values=values)

    def use_offensive_rotation(self, hwnd, mana):
        offensive_spells = self.get_sorted_offensive()
        now = time.time()

        if now - self.last_Offensive_GCD < Offensive_GCD:
            return

        for spell in offensive_spells:
            if mana >= spell["mana_cost"]:
                if now - spell["last_used"] > spell["cd"]:
                    if spell["type"] == "rune":
                        if now - self.last_Potion_GCD > Potion_GCD:
                            send_key(hwnd, spell["key"])
                            self._set_offensive_last_used_by_key(spell["key"], now)  # <--- dopisane
                            self.last_Potion_GCD = now
                            self.last_Offensive_GCD = now
                            print(f"Użyto runy: {spell['key']}")
                            #break
                    else:
                        send_key(hwnd, spell["key"])
                        self._set_offensive_last_used_by_key(spell["key"], now)      # <--- dopisane
                        self.last_Offensive_GCD = now
                        print(f"Użyto czaru ofensywnego: {spell['key']}")
                        #break
               
    def get_sorted_offensive(self):
        offensive_spells = []
        for iid in self.off_tree.get_children():
            values = self.off_tree.item(iid, "values")
            offensive_spells.append({
                "name": values[0],
                "key": values[1],
                "priority": int(values[2]),
                "mana_cost": float(values[3]),
                "cd": float(values[4]),
                "type": values[5],
                "last_used": float(values[6]) if len(values) > 6 and values[6] != "" else 0.0,
            })

        offensive_spells.sort(key=lambda x: x["priority"])
        return offensive_spells
    
    def _set_offensive_last_used_by_key(self, key, ts):
        for iid in self.off_tree.get_children():
            v = list(self.off_tree.item(iid, "values"))
            if v[1] == key:
                if len(v) < 7:
                    v.append(ts)
                else:
                    v[6] = ts
                self.off_tree.item(iid, values=tuple(v))
                break

    def _reset_offensive_last_used(self):
        for iid in self.off_tree.get_children():
            v = list(self.off_tree.item(iid, "values"))
            if len(v) < 7:
                v.append(0.0)
            else:
                v[6] = 0.0
            self.off_tree.item(iid, values=tuple(v))

    # ---------- Healing tab ----------
    def _create_healing_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Leczenie")

        # Dodajemy ukrytą kolumnę "_last_used" jako ostatnia kolumnę
        cols = ("name", "key", "hp%", "mana_cost", "cd", "_last_used")
        self.heal_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        # Widoczne kolumny
        for c in ("name", "key", "hp%", "mana_cost", "cd"):
            self.heal_tree.heading(c, text=c.capitalize())
            self.heal_tree.column(c, width=110)

        # Ukryta kolumna: width=0, minwidth=0, stretch=False
        self.heal_tree.heading("_last_used", text="")
        self.heal_tree.column("_last_used", width=0, minwidth=0, stretch=False)

        self.heal_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btnf, text="Dodaj", command=self._add_heal).pack(side="left", padx=3)
        ttk.Button(btnf, text="Edytuj", command=self._edit_heal).pack(side="left", padx=3)
        ttk.Button(btnf, text="Usuń", command=lambda: self._remove_selected(self.heal_tree)).pack(side="left", padx=3)

    def _add_heal(self):
        schema = [
            ("name", "entry", {"required": False, "default": ""}),
            ("key", "entry", {"required": True}),
            ("hp%", "spin_float", {"required": True, "default": 50, "range": (0, 100)}),
            ("mana_cost", "spin_float", {"required": True, "default": 0, "range": (0, 100)}),
            ("cd", "spin_float", {"required": True, "default": 1.0, "range": (0.0, 9999.0)}),
        ]
        dlg = ItemDialog(self.root, "Dodaj healing", schema)
        if dlg.result:
            e = dlg.result
            self.heal_tree.insert(
                "", "end",
                values=(
                    e.get("name",""),
                    e.get("key",""),
                    float(e.get("hp%", 50)),
                    float(e.get("mana_cost", 0)),
                    float(e.get("cd", 1.0)),
                    0.0  # _last_used (ukryte)
                )
            )
            
    def _edit_heal(self):
        sel = self.heal_tree.selection()
        if not sel:
            messagebox.showinfo("Edytuj", "Zaznacz wpis do edycji.")
            return
        iid = sel[0]
        vals = self.heal_tree.item(iid, "values")
        current = {
            "name": vals[0],
            "key": vals[1],
            "hp%": float(vals[2]) if vals[2] != "" else 50,
            "mana_cost": float(vals[3]) if vals[3] != "" else 0,
            "cd": float(vals[4]) if vals[4] != "" else 1.0,
        }
        last_used_hidden = float(vals[5]) if len(vals) > 5 and vals[5] != "" else 0.0

        schema = [
            ("name", "entry", {"required": False, "default": current["name"]}),
            ("key", "entry", {"required": True}),
            ("hp%", "spin_float", {"required": True, "default": current["hp%"], "range": (0,100)}),
            ("mana_cost", "spin_float", {"required": True, "default": current["mana_cost"], "range": (0,100)}),
            ("cd", "spin_float", {"required": True, "default": current["cd"], "range": (0.0,9999.0)}),
        ]
        dlg = ItemDialog(self.root, "Edytuj healing", schema, data=current)
        if dlg.result:
            e = dlg.result
            self.heal_tree.item(
                iid,
                values=(
                    e.get("name",""),
                    e.get("key",""),
                    float(e.get("hp%",50)),
                    float(e.get("mana_cost",0)),
                    float(e.get("cd",1.0)),
                    last_used_hidden  # zachowujemy ukryte last_used
                )
            )

    def use_heals(self, hwnd, hp, mana):
        heals = self.get_sorted_heals()  # Pobierz posortowane czary leczenia
        now = time.time()

        # Sprawdzamy, czy minął czas GCD przed użyciem jakiegokolwiek czaru leczenia
        if now - self.last_Heal_GCD < Heal_GCD:
            return  # Jeśli nie minął wymagany czas GCD, nie wykonuj żadnej akcji

        for heal in heals:
            if hp <= heal["hp%"]:  # Sprawdzamy, czy HP jest niższe niż wymagane
                if mana >= heal["mana_cost"]:  # Sprawdzamy, czy mamy wystarczającą ilość many
                    if now - heal["last_used"] > heal["cd"]:  # Sprawdzamy cooldown
                        send_key(hwnd, heal["key"])
                        self._set_heal_last_used_by_key(heal["key"], now)  # Zapisz czas użycia
                        self.last_Heal_GCD = now  # Zapisz czas GCD
                        print(f"Użyto czaru leczenia: {heal['key']}")
                        break          

    def get_sorted_heals(self):
        heals = []
        for iid in self.heal_tree.get_children():
            values = self.heal_tree.item(iid, "values")
            heals.append({
                "name": values[0],
                "key": values[1],
                "hp%": float(values[2]),
                "mana_cost": float(values[3]),
                "cd": float(values[4]),
                "last_used": float(values[5]) if len(values) > 5 and values[5] != "" else 0.0
            })

        heals.sort(key=lambda x: x["hp%"])  # Posortuj po hp%
        return heals
    
    def _set_heal_last_used_by_key(self, key, last_used_time):
        """
        Ustawia czas ostatniego użycia dla danego czaru leczenia na podstawie klucza (key).
        """
        for iid in self.heal_tree.get_children():  # Pętla przez elementy w drzewie Healing
            values = self.heal_tree.item(iid, "values")
            if values[1] == key:  # Sprawdzamy, czy klucz odpowiada temu z czaru leczenia
                # Zaktualizuj last_used dla czaru leczenia
                self.heal_tree.item(iid, values=(values[0],  # name
                                                  values[1],  # key
                                                  values[2],  # hp%
                                                  values[3],  # mana_cost
                                                  values[4],  # cd
                                                  last_used_time))  # Ustawiamy new last_used
                #print(f"Zaktualizowano czas last_used dla czaru leczenia {key}: {last_used_time}")
                break

    def _reset_heal_last_used(self):
        """
        Resetuje czas ostatniego użycia (last_used) dla wszystkich czarów leczenia.
        """
        for iid in self.heal_tree.get_children():  # Pętla przez elementy w drzewie Healing
            values = self.heal_tree.item(iid, "values")
            # Resetujemy last_used do 0.0
            self.heal_tree.item(iid, values=(values[0],  # name
                                             values[1],  # key
                                             values[2],  # hp%
                                             values[3],  # mana_cost
                                             values[4],  # cd
                                             0.0))  # resetujemy last_used na 0.0
            print(f"Zresetowano last_used dla czaru leczenia {values[1]} na 0.0")
    
    # ---------- Potions tab ----------
    def _create_potions_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Mikstury")

        cols = ("type", "key", "percent", "cd", "_last_used")
        self.pot_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        for c in ("type", "key", "percent", "cd"):
            self.pot_tree.heading(c, text=c.capitalize())
            self.pot_tree.column(c, width=110)

        self.pot_tree.heading("_last_used", text="")
        self.pot_tree.column("_last_used", width=0, minwidth=0, stretch=False)

        self.pot_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btnf, text="Dodaj", command=self._add_pot).pack(side="left", padx=3)
        ttk.Button(btnf, text="Edytuj", command=self._edit_pot).pack(side="left", padx=3)
        ttk.Button(btnf, text="Usuń", command=lambda: self._remove_selected(self.pot_tree)).pack(side="left", padx=3)

    def _add_pot(self):
        schema = [
            ("type", "combo", {"required": True, "values": ["mana", "hp"], "default": "mana"}),
            ("key", "entry", {"required": True}),
            ("%", "spin_float", {"required": True, "default": 50, "range": (0,100)}),
            ("cd", "spin_float", {"required": True, "default": 1.0, "range": (0.0,9999.0)}),
        ]
        dlg = ItemDialog(self.root, "Dodaj potion", schema)
        if dlg.result:
            e = dlg.result
            self.pot_tree.insert(
                "", "end",
                values=(
                    e.get("type","mana"),
                    e.get("key",""),
                    float(e.get("%",50)),
                    float(e.get("cd",1.0)),
                    0.0  # _last_used (ukryte)
                )
            )

    def _edit_pot(self):
        sel = self.pot_tree.selection()
        if not sel:
            messagebox.showinfo("Edytuj", "Zaznacz wpis do edycji.")
            return
        iid = sel[0]
        vals = self.pot_tree.item(iid, "values")
        current = {
            "type": vals[0],
            "key": vals[1],
            "%": float(vals[2]) if vals[2] != "" else 50,
            "cd": float(vals[3]) if vals[3] != "" else 1.0,
        }
        last_used_hidden = float(vals[4]) if len(vals) > 4 else 0.0

        schema = [
            ("type", "combo", {"required": True, "values": ["mana", "hp"], "default": current["type"]}),
            ("key", "entry", {"required": True, "default": current["key"]}),
            ("%", "spin_float", {"required": True, "default": current["%"], "range": (0, 100.0)}),
            ("cd", "spin_float", {"required": True, "default": current["cd"], "range": (0.0, 9999.0)}),
        ]
        dlg = ItemDialog(self.root, "Edytuj potion", schema, data=current)
        if dlg.result:
            e = dlg.result
            self.pot_tree.item(
                iid,
                values=(
                    e.get("type","mana"),
                    e.get("key",""),
                    float(e.get("%",50)),
                    float(e.get("cd",1.0)),
                    last_used_hidden  # zachowujemy ukryte last_used
                )
            )
            
    def use_potions(self, hwnd, hp, mana, ):
        potions = self.get_sorted_potions()  # Pobierz posortowane potiony
        now = time.time()
        
            # Sprawdzamy, czy minął czas GCD przed użyciem jakiegokolwiek potiona
        if now - self.last_Potion_GCD < Potion_GCD:
            # Jeśli nie minął wymagany czas GCD, nie wykonuj żadnej akcji
            return

        for potion in potions:
            if potion["type"] == "hp" and hp < potion["percent"]:
                if now - potion["last_used"] > potion["cd"]:
                    send_key(hwnd, potion["key"])
                    self._set_potion_last_used_by_key(potion["key"], now)  # Zapisz czas użycia
                    self.last_Potion_GCD = now  # Zapisz czas użycia do last_Potion_GCD
                    print(f"Użyto potionu HP: {potion['key']}")
                    break

            elif potion["type"] == "mana" and mana < potion["percent"]:
                if now - potion["last_used"] > potion["cd"]:
                    send_key(hwnd, potion["key"])
                    self._set_potion_last_used_by_key(potion["key"], now)  # Zapisz czas użycia
                    self.last_Potion_GCD = now  # Zapisz czas użycia do last_Potion_GCD
                    print(f"Użyto potionu Mana: {potion['key']}")
                    break

    def get_sorted_potions(self):
        potions = []
        
        for iid in self.pot_tree.get_children():  # Pętla przez elementy w drzewie Potions
            values = self.pot_tree.item(iid, "values")
            potion = {
                "type": values[0],  # hp lub mana
                "key": values[1],   # klawisz
                "percent": float(values[2]),  # procent
                "cd": float(values[3]),      # cooldown
                "last_used": float(values[4]) if len(values) > 4 else 0.0  # last_used (ukryte)
            }
            potions.append(potion)
        
        # Sortujemy według typu (najpierw hp, potem mana) oraz procentu
        potions.sort(key=lambda x: (x["type"], x["percent"]))
        
        return potions
    
    def _set_potion_last_used_by_key(self, key, last_used_time):
        """
        Ustawia czas ostatniego użycia dla danego potiona na podstawie klucza (key).
        """
        for iid in self.pot_tree.get_children():  # Pętla przez elementy w drzewie Potions
            values = self.pot_tree.item(iid, "values")
            if values[1] == key:  # Sprawdzamy, czy klucz odpowiada temu z potiona
                # Zaktualizuj last_used dla potiona
                self.pot_tree.item(iid, values=(values[0],  # type
                                                values[1],  # key
                                                values[2],  # percent
                                                values[3],  # cd
                                                last_used_time))  # Ustawiamy new last_used
                print(f"Zaktualizowano czas last_used dla potiona {key}: {last_used_time}")
                break
            
    def _reset_potion_last_used(self):
        """
        Resetuje czas ostatniego użycia (last_used) dla wszystkich potionów.
        """
        for iid in self.pot_tree.get_children():  # Pętla przez elementy w drzewie Potions
            values = self.pot_tree.item(iid, "values")
            # Resetujemy last_used do 0.0
            self.pot_tree.item(iid, values=(values[0],  # type
                                            values[1],  # key
                                            values[2],  # percent
                                            values[3],  # cd
                                            0.0))  # resetujemy last_used na 0.0
            print(f"Zresetowano last_used dla potiona {values[1]} na 0.0")

    # ---------- Support tab ----------
    def _create_support_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Wsparcie")
    
        cols = ("name", "key", "cd", "enabled", "_last_used")
        self.sup_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
    
        for c in ("name", "key", "cd", "enabled"):
            self.sup_tree.heading(c, text=c.capitalize())
            self.sup_tree.column(c, width=110)
    
        self.sup_tree.heading("_last_used", text="")
        self.sup_tree.column("_last_used", width=0, minwidth=0, stretch=False)
    
        self.sup_tree.pack(fill="both", expand=True, padx=6, pady=6)
    
        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btnf, text="Dodaj", command=self._add_sup).pack(side="left", padx=3)
        ttk.Button(btnf, text="Edytuj", command=self._edit_sup).pack(side="left", padx=3)
        ttk.Button(btnf, text="Usuń", command=lambda: self._remove_selected(self.sup_tree)).pack(side="left", padx=3)

    def _add_sup(self):
        schema = [
            ("name", "entry", {"required": False, "default": ""}),
            ("key", "entry", {"required": True}),
            ("cd", "spin_float", {"required": True, "default": 1.0, "range": (0.0, 9999.0)}),
            ("enabled", "check", {"required": False, "default": True}),
        ]
        dlg = ItemDialog(self.root, "Dodaj support", schema)
        if dlg.result:
            e = dlg.result
            icon = CHECKED if e.get("enabled", True) else UNCHECKED
            self.sup_tree.insert("", "end", values=(e.get("name", ""), e.get("key", ""), float(e.get("cd", 1.0)), icon, 0.0))
    
    def _edit_sup(self):
        sel = self.sup_tree.selection()
        if not sel:
            messagebox.showinfo("Edytuj", "Zaznacz wpis do edycji.")
            return
        iid = sel[0]
        v = self.sup_tree.item(iid, "values")
        last_used_hidden = float(v[4]) if len(v) > 4 else 0.0

        schema = [
            ("name", "entry", {"required": False, "default": v[0]}),
            ("key", "entry", {"required": True, "default": v[1]}),
            ("cd", "spin_float", {"required": True, "default": float(v[2])}),
            ("enabled", "check", {"required": False, "default": (v[3] == CHECKED)}),
        ]
        dlg = ItemDialog(self.root, "Edytuj support", schema)
        if dlg.result:
            e = dlg.result
            icon = CHECKED if e.get("enabled", True) else UNCHECKED
            self.sup_tree.item(iid, values=(e.get("name", ""), e.get("key", ""), float(e.get("cd", 1.0)), icon, last_used_hidden))

    def use_support(self, hwnd):
        supports = self.get_sorted_support()  # Pobierz posortowane czary wsparcia
        now = time.time()
    
        # Sprawdzamy, czy minął czas GCD przed użyciem jakiegokolwiek wsparcia
        if now - self.last_Support_GCD < Support_GCD:
            return  # Jeśli nie minął wymagany czas GCD, nie wykonuj żadnej akcji
    
        for support in supports:
            if support["enabled"]:  # Sprawdzamy, czy wsparcie jest włączone
                if now - support["last_used"] > support["cd"]:  # Sprawdzamy cooldown
                    send_key(hwnd, support["key"])
                    self._set_support_last_used_by_key(support["key"], now)  # Zaktualizuj `last_used` w UI
                    self.last_Support_GCD = now  # Zapisz czas dla GCD
                    print(f"Użyto wsparcia: {support['key']}")
                    break

    def get_sorted_support(self):
        supports = []
        for iid in self.sup_tree.get_children():  # Pętla przez elementy w drzewie Support
            values = self.sup_tree.item(iid, "values")
            support = {
                "name": values[0],
                "key": values[1],
                "cd": float(values[2]),  # czas cooldownu
                "enabled": (values[3] == CHECKED),  # Sprawdzamy, czy jest włączone
                "last_used": float(values[4]) if len(values) > 4 else 0.0  # last_used (ukryte)
            }
            supports.append(support)
    
        # Sortujemy według aktywności (włączone na początku)
        supports.sort(key=lambda x: x["enabled"], reverse=True)
        
        return supports

    def _set_support_last_used_by_key(self, key, last_used_time):
        for iid in self.sup_tree.get_children():  # Pętla przez elementy w drzewie Support
            values = self.sup_tree.item(iid, "values")
            if values[1] == key:  # Sprawdzamy, czy klucz odpowiada temu z wsparcia
                self.sup_tree.item(iid, values=(values[0],  # name
                                                values[1],  # key
                                                values[2],  # cd
                                                values[3],  # enabled
                                                last_used_time))  # Ustawiamy new last_used
                print(f"Zaktualizowano czas last_used dla support {key}: {last_used_time}")
                break
            
    def _reset_support_last_used(self):
        for iid in self.sup_tree.get_children():  # Pętla przez elementy w drzewie Support
            values = self.sup_tree.item(iid, "values")
            # Resetujemy last_used do 0.0
            self.sup_tree.item(iid, values=(values[0],  # name
                                             values[1],  # key
                                             values[2],  # cd
                                             values[3],  # enabled
                                             0.0))  # resetujemy last_used na 0.0
            print(f"Zresetowano last_used dla wsparcia {values[1]} na 0.0")

    def _support_click(self, event):
        # detect column; toggle enabled if clicking that column
        region = self.sup_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.sup_tree.identify_column(event.x)  # e.g. #1..#4
        # enabled is last column -> check index
        if col != f"#{len(self.sup_tree['columns'])}":
            return
        row = self.sup_tree.identify_row(event.y)
        if not row:
            return
        vals = list(self.sup_tree.item(row, "values"))
        vals[-1] = CHECKED if vals[-1] == UNCHECKED else UNCHECKED
        self.sup_tree.item(row, values=vals)
        

    # ---------- helpers ----------
    def _remove_selected(self, tree):
        sel = tree.selection()
        for s in sel:
            tree.delete(s)

    def _collect_tree_data(self, tree, section):
        out = []
        cols = list(tree["columns"])
        for iid in tree.get_children():
            vals = tree.item(iid, "values")
            row = {}
            if section == "offensive":
                # name,key,priority,mana_cost,cd,type
                row["name"] = vals[0]
                row["key"] = vals[1]
                try:
                    row["priority"] = int(vals[2])
                except:
                    row["priority"] = 99
                try:
                    row["mana_cost"] = float(vals[3])
                except:
                    row["mana_cost"] = 0.0
                try:
                    row["cd"] = float(vals[4])
                except:
                    row["cd"] = 0.0
                row["type"] = vals[5] if len(vals) > 5 else "spell"
            elif section == "healing":
                row["name"] = vals[0]
                row["key"] = vals[1]
                try:
                    row["hp%"] = float(vals[2])
                except:
                    row["hp%"] = 0.0
                try:
                    row["mana_cost"] = float(vals[3])
                except:
                    row["mana_cost"] = 0.0
                try:
                    row["cd"] = float(vals[4])
                except:
                    row["cd"] = 0.0
            elif section == "potions":
                row["type"] = vals[0]
                row["key"] = vals[1]
                try:
                    row["%"] = float(vals[2])
                except:
                    row["%"] = 0.0
                try:
                    row["cd"] = float(vals[3])
                except:
                    row["cd"] = 0.0
            elif section == "support":
                row["name"] = vals[0]
                row["key"] = vals[1]
                try:
                    row["cd"] = float(vals[2])
                except:
                    row["cd"] = 0.0
                row["enabled"] = (vals[3] == CHECKED)
            out.append(row)
        return out

    def _update_tree_from_profile(self, section):
        if section == "offensive":
            tree = self.off_tree
            tree.delete(*tree.get_children())
            data = sorted(self.current_profile.get("offensive", []), key=lambda x: x.get("priority", 99))
            for it in data:
                tree.insert("", "end", values=(it.get("name",""), it.get("key",""),
                                               it.get("priority",99), it.get("mana_cost",0.0),
                                               it.get("cd",0.0), it.get("type","spell")))
        elif section == "healing":
            tree = self.heal_tree
            tree.delete(*tree.get_children())
            for it in self.current_profile.get("healing", []):
                tree.insert("", "end", values=(it.get("name",""), it.get("key",""),
                                               it.get("hp%",0.0), it.get("mana_cost",0.0), it.get("cd",0.0)))
        elif section == "potions":
            tree = self.pot_tree
            tree.delete(*tree.get_children())
            for it in self.current_profile.get("potions", []):
                tree.insert("", "end", values=(it.get("type","mana"), it.get("key",""), it.get("%",0.0), it.get("cd",0.0)))
        elif section == "support":
            tree = self.sup_tree
            tree.delete(*tree.get_children())
            for it in self.current_profile.get("support", []):
                icon = CHECKED if it.get("enabled", True) else UNCHECKED
                tree.insert("", "end", values=(it.get("name",""), it.get("key",""), it.get("cd",0.0), icon))

    def _update_all_trees(self):
        for sec in ("offensive","healing","potions","support"):
            self._update_tree_from_profile(sec)
    
    def update_hp_mp(self, hp, mana):
        """Aktualizuje etykiety HP i MP w UI"""
        self.hp_lbl.config(text=f"HP: {hp:.1f}%")  # Zaktualizowanie wartości HP
        self.mp_lbl.config(text=f"MP: {mana:.1f}%")  # Zaktualizowanie wartości MP        

    # ---------- Bot control UI ----------
    # Bot control functions
    def _create_HpMp_control(self):
        frame = ttk.LabelFrame(self.root, text="Hp / MP")
        frame.pack(fill="x", padx=6, pady=6)
        
        # Etykieta do wyświetlania HP, wyrównana do lewej
        self.hp_lbl = ttk.Label(frame, text="HP: -", anchor="w")  # anchor="w" oznacza wyrównanie do lewej
        self.hp_lbl.pack(fill="x", padx=6, pady=3)  # fill="x" pozwala na rozciągnięcie etykiety w poziomie

        # Etykieta do wyświetlania MP, wyrównana do lewej
        self.mp_lbl = ttk.Label(frame, text="MP: -", anchor="w")  # anchor="w" oznacza wyrównanie do lewej
        self.mp_lbl.pack(fill="x", padx=6, pady=3)  # fill="x" pozwala na rozciągnięcie etykiety w poziomie

    def _create_bot_control(self):
        frame = ttk.LabelFrame(self.root, text="Bot Control")
        frame.pack(fill="x", padx=6, pady=6)
        self.start_btn = ttk.Button(frame, text="Start", command=self._on_start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(frame, text="Stop", command=self._on_stop)
        self.stop_btn.pack(side="left", padx=4)
        self.pause_btn = ttk.Button(frame, text="Wstrzymaj", command=self._on_pause)
        self.pause_btn.pack(side="left", padx=4)
        self.status_lbl = ttk.Label(frame, text="Status: Stopped")
        self.status_lbl.pack(side="right", padx=6)

    def _on_start(self):
        # Sprawdzamy, czy bot już działa
        if self.running_bot:
            messagebox.showwarning("Bot already running", "Bot is already running!")
            return  # Zatrzymujemy dalsze wykonywanie, jeśli bot już działa

        self.current_profile_name = self.profile_combo.get()
        self.status_lbl.config(text=f"Status: Starting ({self.current_profile_name})")
        
        # Zablokowanie przycisku Start, żeby zapobiec wielokrotnemu uruchomieniu bota
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)  # Włączamy przycisk Stop

        # Startujemy bota w osobnym wątku
        threading.Thread(target=self._start_bot, daemon=True).start()

    def _start_bot(self):
        try:
            if time.time() > end_time:
                self.status_lbl.config(text="Status: Stopped - Koniec LICENCJI")
                self.running_bot = False
                print("Koniec ważności aplikacji!")
                return  # Zatrzymanie procesu bota, jeśli data minęła

             # Ustawiamy flagę, że bot działa
            self.running_bot = True  # Bot został uruchomiony
            
            # Pobierz aktualny profil i nazwę okna gry
            profile_name = self.current_profile_name
            window_name = f"Tibia - {profile_name}"

            # Próbujemy znaleźć okno
            hwnd = win32gui.FindWindow(None, window_name)
            if not hwnd:
                raise Exception(f"Nie znaleziono okna: {window_name}")
            
            # Jeśli okno jest dostępne, rozpocznij działanie bota
            print(f"Start bot: {profile_name}")
            self.status_lbl.config(text=f"Status: Running ({profile_name}), Rotation paused")
            
            # Wywołaj funkcję do działania bota
            self._reset_potion_last_used()
            self._reset_heal_last_used()
            self._reset_offensive_last_used()
            self._reset_support_last_used()
            self._run_bot(hwnd, window_name)
            
            

        except Exception as e:
            self.status_lbl.config(text=f"Status: Failed to start - {str(e)}")
        finally:
            self.start_btn.config(state=tk.NORMAL)

    def _run_bot(self, hwnd, window_name):
        while self.running_bot:
            try:
                # Zdobądź HP i MP
                hp, mana = read_hp_mana(window_name, HP_RECT, MANA_RECT)
                self.update_hp_mp(hp, mana)

                # Użyj potionów, jeśli wymagają tego warunki
                self.use_potions(hwnd, hp, mana)
                # Używamy healingów
                self.use_heals(hwnd, hp, mana)  # Wywołanie funkcji use_heals
                if self.rotation_enabled:
                    # Używamy ofensywnych zaklęć
                    self.use_offensive_rotation(hwnd, mana)  # Wywołanie funkcji use_offensive_rotation
                    # Używamy zaklec support
                    self.use_support(hwnd)  # Wywołanie funkcji use_support
                

                time.sleep(0.2)
                gc.collect()

            except Exception as e:
                print("Błąd:", e)
                time.sleep(0.2)

    def _on_stop(self):
        self.status_lbl.config(text="Status: Stopped")
        self.running_bot = False  # Zmieniamy flagę po zatrzymaniu bota
        self.start_btn.config(state=tk.NORMAL)  # Odblokowanie przycisku Start
        self.stop_btn.config(state=tk.DISABLED)  # Zablokowanie przycisku Stop

    def _on_pause(self):
        if self.running_bot:
            if self.rotation_enabled :
                self.status_lbl.config(text=f"Status: Running ({self.current_profile_name}), Rotation paused")
                self.rotation_enabled = False
            else :
                self.status_lbl.config(text=f"Status: Running ({self.current_profile_name})")
                self.rotation_enabled = True
        

                



# ======= Start =======
if __name__ == "__main__":
    root = tk.Tk()
    app = BotUI(root)
    root.mainloop()
