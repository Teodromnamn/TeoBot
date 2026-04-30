import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
from datetime import datetime
import webbrowser

from profiles.manager import ProfileManager
from logic.offensive import OffensiveLogic
from logic.healing import HealingLogic
from logic.potions import PotionLogic
from logic.support import SupportLogic
from logic.bot_engine import BotEngine
from profiles.defaults import DEFAULT_OFFENSIVE, DEFAULT_HEALING, DEFAULT_POTIONS, DEFAULT_SUPPORT

# Okna dialogowe usunięte - wszystko odbywa się w jednym oknie (Inline Forms)


class BotUI:
    """
    Warstwa UI — zarządza widżetami, profilami i komunikacją z BotEngine.
    Engine działa całkowicie poza UI.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Teo Bot")
        
        # Ustawienie własnej ikony (zabezpieczone przed brakiem pliku)
        icon_path = "Scout.ico"
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # Profile Manager
        self.profile_mgr = ProfileManager()

        # Logic modules
        self.logic = {
            "offensive": OffensiveLogic(),
            "healing": HealingLogic(),
            "potions": PotionLogic(),
            "support": SupportLogic()
        }

        # Engine
        self.engine = BotEngine(
            self.logic,
            self._update_hp_mp,
            self._update_status
        )

        # UI
        self._build_ui()

        # Load default
        self._set_current_profile(self.profile_mgr.current_name)

    # ======================================================
    # DARK MODE THEME
    # ======================================================
    def _apply_dark_theme(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
            
        bg_color = "#2b2b2b"
        fg_color = "#d1d1d1"
        btn_bg = "#3c3f41"
        btn_active = "#4b6eaf"
        entry_bg = "#1e1e1e"
        
        self.root.configure(bg=bg_color)
        style.configure(".", background=bg_color, foreground=fg_color, fieldbackground=entry_bg, insertcolor=fg_color)
        style.configure("TNotebook", background=bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background=btn_bg, foreground=fg_color, padding=[15, 5])
        style.map("TNotebook.Tab", background=[("selected", btn_active)])
        style.configure("TButton", background=btn_bg, foreground=fg_color, borderwidth=1, padding=4)
        style.map("TButton", background=[("active", btn_active), ("pressed", btn_active)])
        style.configure("Treeview", background=entry_bg, fieldbackground=entry_bg, foreground=fg_color, borderwidth=0)
        style.map("Treeview", background=[("selected", btn_active)])
        style.configure("Treeview.Heading", background=btn_bg, foreground=fg_color)
        style.map("Treeview.Heading", background=[("active", btn_bg)])
        style.configure("TLabelframe", background=bg_color, foreground=fg_color)
        style.configure("TLabelframe.Label", background=bg_color, foreground="#5294e2", font=("Arial", 10, "bold"))
        
        # Styl dla etykiety z błędami/komunikatami (Inline Message)
        style.configure("Error.TLabel", foreground="#ff4d4d", background=bg_color, font=("Arial", 9, "bold"))
        style.configure("Success.TLabel", foreground="#4caf50", background=bg_color, font=("Arial", 9, "bold"))

    # ======================================================
    # HELPER: INLINE MESSAGE
    # ======================================================
    def _show_inline_msg(self, container, message, is_error=True):
        """Wyświetla tymczasowy komunikat wewnątrz podanego kontenera (zamiast pop-upa)."""
        if hasattr(self, '_current_msg_lbl') and self._current_msg_lbl.winfo_exists():
            self._current_msg_lbl.destroy()
            
        style_name = "Error.TLabel" if is_error else "Success.TLabel"
        self._current_msg_lbl = ttk.Label(container, text=message, style=style_name)
        self._current_msg_lbl.pack(pady=2)
        
        # Zniknij po 3 sekundach
        self.root.after(3000, lambda: self._current_msg_lbl.destroy() if self._current_msg_lbl.winfo_exists() else None)

    # ======================================================
    # BUILD UI
    # ======================================================
    def _build_ui(self):
        self._apply_dark_theme()

        # Sztywny kontener centralny pod warstwy
        self.center_frame = ttk.Frame(self.root)
        self.center_frame.pack(fill="both", expand=True)
        self.center_frame.grid_rowconfigure(0, weight=1)
        self.center_frame.grid_columnconfigure(0, weight=1)

        # WARSTWA 1: Notatnik (Zakładki)
        self.notebook = ttk.Notebook(self.center_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self._create_profiles_tab()
        self._create_offensive_tab()
        self._create_healing_tab()
        self._create_potions_tab()
        self._create_support_tab()
        
        # Cavebot ukryty na życzenie użytkownika
        # self._create_cavebot_tab()

        # WARSTWA 2: Widok Info
        self._create_info_view()

        # Przycisk ułożony "na twardo" z prawej strony paska zakładek (overlay)
        self.info_is_open = False
        self.info_btn = ttk.Button(self.root, text=" ℹ ", width=3, command=self._toggle_info_view)
        self.info_btn.place(relx=1.0, rely=0.0, x=-2, y=2, anchor="ne")

        # Ustawiamy Notebook na start na samym wierzchu
        self.notebook.tkraise()

        # Płyta dolna
        self._create_hpm_mp_panel()
        self._create_bot_control()

    # ======================================================
    # INFO / CONTACT VIEW
    # ======================================================
    def _create_info_view(self):
        # Frame dzielący komórkę (0,0) wspólnie z Notebookiem
        self.info_frame = ttk.Frame(self.center_frame)
        self.info_frame.grid(row=0, column=0, sticky="nsew")
        
        container = ttk.Frame(self.info_frame)
        container.pack(expand=True, fill="both", padx=20, pady=30)

        title = ttk.Label(container, text="Application Information", font=("Arial", 14, "bold"), foreground="#5294e2")
        title.pack(pady=(0, 15))

        version_lbl = ttk.Label(container, text="Bot Version: v1.0.1", font=("Arial", 10))
        version_lbl.pack(pady=2)

        expiry_date = "2027-01-01"
        try:
            days_left = (datetime.strptime(expiry_date, "%Y-%m-%d") - datetime.now()).days
            expiry_text = f"License Expiry: {expiry_date} (Days left: {days_left})"
        except Exception:
            expiry_text = f"License Expiry: {expiry_date}"
            
        expiry_lbl = ttk.Label(container, text=expiry_text, font=("Arial", 10))
        expiry_lbl.pack(pady=2)
        
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=15)
        
        contact_header = ttk.Label(container, text="Contact & Support:", font=("Arial", 11, "bold"))
        contact_header.pack(pady=(0, 5))

        discord_btn = ttk.Button(container, text="Discord (Main Support)", 
                                 command=lambda: webbrowser.open("https://discord.com/invite/wUxy42Ng9u"))
        discord_btn.pack(fill="x", pady=3, ipadx=5, ipady=3)

        yt_btn = ttk.Button(container, text="YouTube Channel (Tutorials)", 
                            command=lambda: webbrowser.open("https://www.youtube.com/@TeoBot-Tibia"))
        yt_btn.pack(fill="x", pady=3, ipadx=5, ipady=3)

    def _toggle_info_view(self):
        if self.info_is_open:
            # Wracamy do widoku zakładek
            self.notebook.tkraise()
            self.info_btn.configure(text=" ℹ ")
            self.info_is_open = False
        else:
            # Idziemy do informacji (przycisk zmienia się na X)
            self.info_frame.tkraise()
            self.info_btn.configure(text=" ✖ ")
            self.info_is_open = True

    # ======================================================
    # PROFILES TAB (BEZ POP-UPÓW)
    # ======================================================
    def _create_profiles_tab(self):
        self.prof_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.prof_frame, text="Profiles")

        # Top Control Panel
        load_frame = ttk.LabelFrame(self.prof_frame, text="Select / Load Profile")
        load_frame.pack(fill="x", pady=10, padx=10, ipadx=5, ipady=5)

        ttk.Label(load_frame, text="Available Profiles:").pack(side="left", padx=5)
        self.profile_combo = ttk.Combobox(load_frame, state="readonly", width=25)
        self.profile_combo.pack(side="left", padx=5)
        ttk.Button(load_frame, text="Load Selected", command=self._load_selected_profile).pack(side="left", padx=5)

        # Action Panel (Nowy układ dla akcji tworzenia/kopiowania)
        action_frame = ttk.LabelFrame(self.prof_frame, text="Manage Profiles")
        action_frame.pack(fill="x", pady=10, padx=10, ipadx=5, ipady=5)
        
        # Pole wejściowe do podawania nazwy nowego/kopiowanego profilu
        input_f = ttk.Frame(action_frame)
        input_f.pack(fill="x", pady=5)
        ttk.Label(input_f, text="Profile Name:").pack(side="left", padx=5)
        self.prof_name_entry = ttk.Entry(input_f, width=25)
        self.prof_name_entry.pack(side="left", padx=5)

        # Przyciski akcji
        btn_f = ttk.Frame(action_frame)
        btn_f.pack(fill="x", pady=5)
        ttk.Button(btn_f, text="Create New", command=self._new_profile).pack(side="left", padx=5)
        ttk.Button(btn_f, text="Copy Current As...", command=self._copy_profile).pack(side="left", padx=5)
        ttk.Button(btn_f, text="Save Current", command=self._save_profile).pack(side="left", padx=5)
        ttk.Button(btn_f, text="Delete Selected", command=self._delete_profile).pack(side="left", padx=5)

        # Aktualny status
        status_f = ttk.Frame(self.prof_frame)
        status_f.pack(fill="x", pady=10, padx=10)
        self.label_current = ttk.Label(status_f, text="Current Profile: -", font=("Arial", 11, "bold"), foreground="#5294e2")
        self.label_current.pack(anchor="w")
        
        # Kontener na komunikaty błędów w zakładce Profiles
        self.prof_msg_container = ttk.Frame(self.prof_frame)
        self.prof_msg_container.pack(fill="x", pady=5, padx=10)

    def _new_profile(self):
        name = self.prof_name_entry.get().strip()
        if not name: 
            self._show_inline_msg(self.prof_msg_container, "Error: Enter a profile name first.", True)
            return
        if name in self.profile_mgr.profiles:
            self._show_inline_msg(self.prof_msg_container, f"Error: Profile '{name}' already exists.", True)
            return
            
        self.profile_mgr.new_profile(name)
        self.profile_mgr.save_all()
        self._update_profile_combo()
        self._set_current_profile(name)
        self.prof_name_entry.delete(0, 'end')
        self._show_inline_msg(self.prof_msg_container, f"Created new profile: {name}", False)

    def _copy_profile(self):
        src = self.profile_mgr.current_name
        new_name = self.prof_name_entry.get().strip()
        if not new_name: 
            self._show_inline_msg(self.prof_msg_container, "Error: Enter a name for the copied profile.", True)
            return
        if new_name in self.profile_mgr.profiles:
            self._show_inline_msg(self.prof_msg_container, f"Error: Profile '{new_name}' already exists.", True)
            return
            
        self.profile_mgr.duplicate(src, new_name)
        self.profile_mgr.save_all()
        self._update_profile_combo()
        self._set_current_profile(new_name) # Auto load copied
        self.prof_name_entry.delete(0, 'end')
        self._show_inline_msg(self.prof_msg_container, f"Copied to: {new_name}", False)

    def _delete_profile(self):
        name = self.profile_combo.get()
        if not name:
            self._show_inline_msg(self.prof_msg_container, "Error: Select a profile to delete from the dropdown.", True)
            return
        if name == "Default":
            self._show_inline_msg(self.prof_msg_container, "Error: Cannot delete the Default profile!", True)
            return
            
        self.profile_mgr.delete(name)
        self.profile_mgr.save_all()
        self._update_profile_combo()
        
        if self.profile_mgr.current_name == name:
            if self.profile_mgr.profiles:
                new_first = next(iter(self.profile_mgr.profiles.keys()))
                self._set_current_profile(new_first)
                
        self._show_inline_msg(self.prof_msg_container, f"Deleted profile: {name}", False)

    def _load_selected_profile(self):
        name = self.profile_combo.get()
        if name:
            self._set_current_profile(name)
            self._show_inline_msg(self.prof_msg_container, f"Loaded profile: {name}", False)
        else:
            self._show_inline_msg(self.prof_msg_container, "Error: Select a profile to load.", True)

    def _update_profile_combo(self):
        self.profile_combo["values"] = list(self.profile_mgr.profiles.keys())
        if self.profile_mgr.current_name:
            self.profile_combo.set(self.profile_mgr.current_name)

    def _set_current_profile(self, name):
        if name not in self.profile_mgr.profiles: return
        self.profile_mgr.set_current(name)
        self.label_current.config(text=f"Current Profile: {name}")
        self._update_profile_combo()

        p = self.profile_mgr.current
        self._fill_tree(self.off_tree, p["offensive"], "off")
        self._fill_tree(self.heal_tree, p["healing"], "heal")
        self._fill_tree(self.pot_tree, p["potions"], "pot")
        self._fill_tree(self.sup_tree, p["support"], "sup")

        self.logic["offensive"].update(p["offensive"])
        self.logic["healing"].update(p["healing"])
        self.logic["potions"].update(p["potions"])
        self.logic["support"].update(p["support"])

    def _save_profile(self):
        name = self.profile_mgr.current_name
        if not name: return

        profile = {
            "offensive": self._collect_data_from_tree(self.off_tree, "off"),
            "healing": self._collect_data_from_tree(self.heal_tree, "heal"),
            "potions": self._collect_data_from_tree(self.pot_tree, "pot"),
            "support": self._collect_data_from_tree(self.sup_tree, "sup"),
        }

        self.profile_mgr.profiles[name] = profile
        self.profile_mgr.save_all()

        self.logic["offensive"].update(profile["offensive"])
        self.logic["healing"].update(profile["healing"])
        self.logic["potions"].update(profile["potions"])
        self.logic["support"].update(profile["support"])
        
        self._show_inline_msg(self.prof_msg_container, f"Profile '{name}' saved successfully.", False)

    def _refresh_logic(self):
        profile = {
            "offensive": self._collect_data_from_tree(self.off_tree, "off"),
            "healing": self._collect_data_from_tree(self.heal_tree, "heal"),
            "potions": self._collect_data_from_tree(self.pot_tree, "pot"),
            "support": self._collect_data_from_tree(self.sup_tree, "sup"),
        }
        self.logic["offensive"].update(profile["offensive"])
        self.logic["healing"].update(profile["healing"])
        self.logic["potions"].update(profile["potions"])
        self.logic["support"].update(profile["support"])

    # ======================================================
    # TREEVIEW HELPERS
    # ======================================================
    def _fill_tree(self, tree, data, section):
        tree.delete(*tree.get_children())
        for item in data:
            if section == "off":
                tree.insert("", "end", values=(item["name"], item["key"], item["priority"], item["mana_cost"], item["cd"], item["type"]))
            elif section == "heal":
                tree.insert("", "end", values=(item["name"], item["key"], item["hp%"], item["mana_cost"], item["cd"]))
            elif section == "pot":
                tree.insert("", "end", values=(item["type"], item["key"], item["%"], item["cd"]))
            elif section == "sup":
                icon = "☑" if item["enabled"] else "☐"
                tree.insert("", "end", values=(item["name"], item["key"], item["cd"], icon))

    def _collect_data_from_tree(self, tree, section):
        out = []
        for iid in tree.get_children():
            vals = tree.item(iid, "values")
            if section == "off":
                out.append({"name": vals[0], "key": vals[1], "priority": int(vals[2]), "mana_cost": float(vals[3]), "cd": float(vals[4]), "type": vals[5]})
            if section == "heal":
                out.append({"name": vals[0], "key": vals[1], "hp%": float(vals[2]), "mana_cost": float(vals[3]), "cd": float(vals[4])})
            if section == "pot":
                out.append({"type": vals[0], "key": vals[1], "%": float(vals[2]), "cd": float(vals[3])})
            if section == "sup":
                out.append({"name": vals[0], "key": vals[1], "cd": float(vals[2]), "enabled": vals[3] == "☑"})
        return out

    def _delete_selected(self, tree):
        for s in tree.selection():
            tree.delete(s)
        self._refresh_logic()

    # ======================================================
    # OFFENSIVE TAB (Inline Form)
    # ======================================================
    def _create_offensive_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Offensive")

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        right = ttk.LabelFrame(paned, text="Details")
        paned.add(left, weight=3)
        paned.add(right, weight=1)

        cols = ("name", "key", "priority", "mana_cost", "cd", "type")
        self.off_tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c in cols:
            self.off_tree.heading(c, text=c.capitalize())
            self.off_tree.column(c, width=80)
        self.off_tree.pack(fill="both", expand=True)
        self.off_tree.bind("<<TreeviewSelect>>", self._on_off_select)

        # Form
        right.columnconfigure(1, weight=1)
        ttk.Label(right, text="Name:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.off_name = ttk.Entry(right)
        self.off_name.grid(row=0, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Key:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.off_key = ttk.Entry(right)
        self.off_key.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Priority:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        self.off_prio = ttk.Spinbox(right, from_=1, to=20, width=5)
        self.off_prio.grid(row=2, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(right, text="Mana Cost:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        self.off_mana = ttk.Entry(right)
        self.off_mana.grid(row=3, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Cooldown:").grid(row=4, column=0, sticky="w", padx=5, pady=3)
        self.off_cd = ttk.Entry(right)
        self.off_cd.grid(row=4, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Type:").grid(row=5, column=0, sticky="w", padx=5, pady=3)
        self.off_type = ttk.Combobox(right, values=["spell", "rune"], state="readonly")
        self.off_type.grid(row=5, column=1, sticky="ew", padx=5, pady=3)
        
        # Kontener na wiadomości błędu (Inline Form)
        self.off_msg_container = ttk.Frame(right)
        self.off_msg_container.grid(row=6, column=0, columnspan=2, sticky="ew")

        btn_f = ttk.Frame(right)
        btn_f.grid(row=7, column=0, columnspan=2, pady=10, sticky="ew")
        ttk.Button(btn_f, text="Clear", command=self._clear_off).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Add", command=self._add_off).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Update", command=self._edit_off).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Del", command=lambda: self._delete_selected(self.off_tree)).pack(side="left", fill="x", expand=True, padx=2)

        self._clear_off()

    def _clear_off(self):
        self.off_name.delete(0, "end")
        self.off_key.delete(0, "end")
        self.off_prio.set(10)
        self.off_mana.delete(0, "end"); self.off_mana.insert(0, "0.0")
        self.off_cd.delete(0, "end"); self.off_cd.insert(0, "1.0")
        self.off_type.set("spell")

    def _on_off_select(self, event):
        sel = self.off_tree.selection()
        if not sel: return
        vals = self.off_tree.item(sel[0], "values")
        self._clear_off()
        self.off_name.insert(0, vals[0])
        self.off_key.insert(0, vals[1])
        self.off_prio.set(vals[2])
        self.off_mana.delete(0, "end"); self.off_mana.insert(0, vals[3])
        self.off_cd.delete(0, "end"); self.off_cd.insert(0, vals[4])
        self.off_type.set(vals[5])

    def _add_off(self):
        try:
            name = self.off_name.get()
            key = self.off_key.get()
            if not key:
                self._show_inline_msg(self.off_msg_container, "Error: 'Key' cannot be empty.")
                return
            prio = int(self.off_prio.get())
            mana = float(self.off_mana.get().replace(',', '.'))
            cd = float(self.off_cd.get().replace(',', '.'))
            typ = self.off_type.get()
            
            self.off_tree.insert("", "end", values=(name, key, prio, mana, cd, typ))
            self._refresh_logic()
            self._clear_off()
            self._show_inline_msg(self.off_msg_container, "Added successfully.", False)
        except ValueError:
            self._show_inline_msg(self.off_msg_container, "Error: Invalid number format.")

    def _edit_off(self):
        sel = self.off_tree.selection()
        if not sel: return
        try:
            name = self.off_name.get()
            key = self.off_key.get()
            if not key:
                self._show_inline_msg(self.off_msg_container, "Error: 'Key' cannot be empty.")
                return
            prio = int(self.off_prio.get())
            mana = float(self.off_mana.get().replace(',', '.'))
            cd = float(self.off_cd.get().replace(',', '.'))
            typ = self.off_type.get()
            
            self.off_tree.item(sel[0], values=(name, key, prio, mana, cd, typ))
            self._refresh_logic()
            self._show_inline_msg(self.off_msg_container, "Updated successfully.", False)
        except ValueError:
            self._show_inline_msg(self.off_msg_container, "Error: Invalid number format.")

    # ======================================================
    # HEALING TAB (Inline Form)
    # ======================================================
    def _create_healing_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Healing")

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        right = ttk.LabelFrame(paned, text="Details")
        paned.add(left, weight=3)
        paned.add(right, weight=1)

        cols = ("name", "key", "hp%", "mana_cost", "cd")
        self.heal_tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c in cols:
            self.heal_tree.heading(c, text=c.capitalize())
            self.heal_tree.column(c, width=80)
        self.heal_tree.pack(fill="both", expand=True)
        self.heal_tree.bind("<<TreeviewSelect>>", self._on_heal_select)

        # Form
        right.columnconfigure(1, weight=1)
        ttk.Label(right, text="Name:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.heal_name = ttk.Entry(right)
        self.heal_name.grid(row=0, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Key:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.heal_key = ttk.Entry(right)
        self.heal_key.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="HP %:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        self.heal_hp = ttk.Entry(right)
        self.heal_hp.grid(row=2, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Mana Cost:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        self.heal_mana = ttk.Entry(right)
        self.heal_mana.grid(row=3, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(right, text="Cooldown:").grid(row=4, column=0, sticky="w", padx=5, pady=3)
        self.heal_cd = ttk.Entry(right)
        self.heal_cd.grid(row=4, column=1, sticky="ew", padx=5, pady=3)
        
        self.heal_msg_container = ttk.Frame(right)
        self.heal_msg_container.grid(row=5, column=0, columnspan=2, sticky="ew")

        btn_f = ttk.Frame(right)
        btn_f.grid(row=6, column=0, columnspan=2, pady=10, sticky="ew")
        ttk.Button(btn_f, text="Clear", command=self._clear_heal).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Add", command=self._add_heal).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Update", command=self._edit_heal).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Del", command=lambda: self._delete_selected(self.heal_tree)).pack(side="left", fill="x", expand=True, padx=2)

        self._clear_heal()

    def _clear_heal(self):
        self.heal_name.delete(0, "end")
        self.heal_key.delete(0, "end")
        self.heal_hp.delete(0, "end"); self.heal_hp.insert(0, "50.0")
        self.heal_mana.delete(0, "end"); self.heal_mana.insert(0, "0.0")
        self.heal_cd.delete(0, "end"); self.heal_cd.insert(0, "1.0")

    def _on_heal_select(self, event):
        sel = self.heal_tree.selection()
        if not sel: return
        vals = self.heal_tree.item(sel[0], "values")
        self._clear_heal()
        self.heal_name.insert(0, vals[0])
        self.heal_key.insert(0, vals[1])
        self.heal_hp.delete(0, "end"); self.heal_hp.insert(0, vals[2])
        self.heal_mana.delete(0, "end"); self.heal_mana.insert(0, vals[3])
        self.heal_cd.delete(0, "end"); self.heal_cd.insert(0, vals[4])

    def _add_heal(self):
        try:
            name = self.heal_name.get()
            key = self.heal_key.get()
            if not key:
                self._show_inline_msg(self.heal_msg_container, "Error: 'Key' cannot be empty.")
                return
            hp = float(self.heal_hp.get().replace(',', '.'))
            mana = float(self.heal_mana.get().replace(',', '.'))
            cd = float(self.heal_cd.get().replace(',', '.'))
            
            self.heal_tree.insert("", "end", values=(name, key, hp, mana, cd))
            self._refresh_logic()
            self._clear_heal()
            self._show_inline_msg(self.heal_msg_container, "Added successfully.", False)
        except ValueError:
            self._show_inline_msg(self.heal_msg_container, "Error: Invalid number format.")

    def _edit_heal(self):
        sel = self.heal_tree.selection()
        if not sel: return
        try:
            name = self.heal_name.get()
            key = self.heal_key.get()
            if not key:
                self._show_inline_msg(self.heal_msg_container, "Error: 'Key' cannot be empty.")
                return
            hp = float(self.heal_hp.get().replace(',', '.'))
            mana = float(self.heal_mana.get().replace(',', '.'))
            cd = float(self.heal_cd.get().replace(',', '.'))
            
            self.heal_tree.item(sel[0], values=(name, key, hp, mana, cd))
            self._refresh_logic()
            self._show_inline_msg(self.heal_msg_container, "Updated successfully.", False)
        except ValueError:
            self._show_inline_msg(self.heal_msg_container, "Error: Invalid number format.")


    # ======================================================
    # POTIONS TAB (Inline Form)
    # ======================================================
    def _create_potions_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Potions")

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        right = ttk.LabelFrame(paned, text="Details")
        paned.add(left, weight=3)
        paned.add(right, weight=1)

        cols = ("type", "key", "percent", "cd")
        self.pot_tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c in cols:
            self.pot_tree.heading(c, text=c.capitalize())
            self.pot_tree.column(c, width=80)
        self.pot_tree.pack(fill="both", expand=True)
        self.pot_tree.bind("<<TreeviewSelect>>", self._on_pot_select)

        # Form
        right.columnconfigure(1, weight=1)
        ttk.Label(right, text="Type:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.pot_type = ttk.Combobox(right, values=["hp", "mana"], state="readonly")
        self.pot_type.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(right, text="Key:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.pot_key = ttk.Entry(right)
        self.pot_key.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(right, text="Percent %:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.pot_pct = ttk.Entry(right)
        self.pot_pct.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(right, text="Cooldown:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.pot_cd = ttk.Entry(right)
        self.pot_cd.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        
        self.pot_msg_container = ttk.Frame(right)
        self.pot_msg_container.grid(row=4, column=0, columnspan=2, sticky="ew")

        btn_f = ttk.Frame(right)
        btn_f.grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")
        ttk.Button(btn_f, text="Clear", command=self._clear_pot).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Add", command=self._add_pot).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Update", command=self._edit_pot).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Del", command=lambda: self._delete_selected(self.pot_tree)).pack(side="left", fill="x", expand=True, padx=2)

        self._clear_pot()

    def _clear_pot(self):
        self.pot_type.set("mana")
        self.pot_key.delete(0, "end")
        self.pot_pct.delete(0, "end"); self.pot_pct.insert(0, "50.0")
        self.pot_cd.delete(0, "end"); self.pot_cd.insert(0, "1.0")

    def _on_pot_select(self, event):
        sel = self.pot_tree.selection()
        if not sel: return
        vals = self.pot_tree.item(sel[0], "values")
        self._clear_pot()
        self.pot_type.set(vals[0])
        self.pot_key.insert(0, vals[1])
        self.pot_pct.delete(0, "end"); self.pot_pct.insert(0, vals[2])
        self.pot_cd.delete(0, "end"); self.pot_cd.insert(0, vals[3])

    def _add_pot(self):
        try:
            typ = self.pot_type.get()
            key = self.pot_key.get()
            if not key:
                self._show_inline_msg(self.pot_msg_container, "Error: 'Key' cannot be empty.")
                return
            pct = float(self.pot_pct.get().replace(',', '.'))
            cd = float(self.pot_cd.get().replace(',', '.'))
            
            self.pot_tree.insert("", "end", values=(typ, key, pct, cd))
            self._refresh_logic()
            self._clear_pot()
            self._show_inline_msg(self.pot_msg_container, "Added successfully.", False)
        except ValueError:
            self._show_inline_msg(self.pot_msg_container, "Error: Invalid number format.")

    def _edit_pot(self):
        sel = self.pot_tree.selection()
        if not sel: return
        try:
            typ = self.pot_type.get()
            key = self.pot_key.get()
            if not key:
                self._show_inline_msg(self.pot_msg_container, "Error: 'Key' cannot be empty.")
                return
            pct = float(self.pot_pct.get().replace(',', '.'))
            cd = float(self.pot_cd.get().replace(',', '.'))
            
            self.pot_tree.item(sel[0], values=(typ, key, pct, cd))
            self._refresh_logic()
            self._show_inline_msg(self.pot_msg_container, "Updated successfully.", False)
        except ValueError:
            self._show_inline_msg(self.pot_msg_container, "Error: Invalid number format.")


    # ======================================================
    # SUPPORT TAB (Inline Form)
    # ======================================================
    def _create_support_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Support")

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        right = ttk.LabelFrame(paned, text="Details")
        paned.add(left, weight=3)
        paned.add(right, weight=1)

        cols = ("name", "key", "cd", "enabled")
        self.sup_tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c in cols:
            self.sup_tree.heading(c, text=c.capitalize())
            self.sup_tree.column(c, width=80)
        self.sup_tree.pack(fill="both", expand=True)
        self.sup_tree.bind("<<TreeviewSelect>>", self._on_sup_select)

        # Form
        right.columnconfigure(1, weight=1)
        ttk.Label(right, text="Name:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.sup_name = ttk.Entry(right)
        self.sup_name.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(right, text="Key:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.sup_key = ttk.Entry(right)
        self.sup_key.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(right, text="Cooldown:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.sup_cd = ttk.Entry(right)
        self.sup_cd.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        self.sup_enabled_var = tk.BooleanVar(value=True)
        self.sup_enabled = ttk.Checkbutton(right, text="Enabled", variable=self.sup_enabled_var)
        self.sup_enabled.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        
        self.sup_msg_container = ttk.Frame(right)
        self.sup_msg_container.grid(row=4, column=0, columnspan=2, sticky="ew")

        btn_f = ttk.Frame(right)
        btn_f.grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")
        ttk.Button(btn_f, text="Clear", command=self._clear_sup).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Add", command=self._add_sup).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Update", command=self._edit_sup).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Del", command=lambda: self._delete_selected(self.sup_tree)).pack(side="left", fill="x", expand=True, padx=2)

        self._clear_sup()

    def _clear_sup(self):
        self.sup_name.delete(0, "end")
        self.sup_key.delete(0, "end")
        self.sup_cd.delete(0, "end"); self.sup_cd.insert(0, "1.0")
        self.sup_enabled_var.set(True)

    def _on_sup_select(self, event):
        sel = self.sup_tree.selection()
        if not sel: return
        vals = self.sup_tree.item(sel[0], "values")
        self._clear_sup()
        self.sup_name.insert(0, vals[0])
        self.sup_key.insert(0, vals[1])
        self.sup_cd.delete(0, "end"); self.sup_cd.insert(0, vals[2])
        self.sup_enabled_var.set(vals[3] == "☑")

    def _add_sup(self):
        try:
            name = self.sup_name.get()
            key = self.sup_key.get()
            if not key:
                self._show_inline_msg(self.sup_msg_container, "Error: 'Key' cannot be empty.")
                return
            cd = float(self.sup_cd.get().replace(',', '.'))
            icon = "☑" if self.sup_enabled_var.get() else "☐"
            
            self.sup_tree.insert("", "end", values=(name, key, cd, icon))
            self._refresh_logic()
            self._clear_sup()
            self._show_inline_msg(self.sup_msg_container, "Added successfully.", False)
        except ValueError:
            self._show_inline_msg(self.sup_msg_container, "Error: Invalid number format.")

    def _edit_sup(self):
        sel = self.sup_tree.selection()
        if not sel: return
        try:
            name = self.sup_name.get()
            key = self.sup_key.get()
            if not key:
                self._show_inline_msg(self.sup_msg_container, "Error: 'Key' cannot be empty.")
                return
            cd = float(self.sup_cd.get().replace(',', '.'))
            icon = "☑" if self.sup_enabled_var.get() else "☐"
            
            self.sup_tree.item(sel[0], values=(name, key, cd, icon))
            self._refresh_logic()
            self._show_inline_msg(self.sup_msg_container, "Updated successfully.", False)
        except ValueError:
            self._show_inline_msg(self.sup_msg_container, "Error: Invalid number format.")

    # ======================================================
    # CAVEBOT (Temporarily Hidden)
    # ======================================================
    def _create_cavebot_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Cavebot")

        self.cave_list = tk.Listbox(frame, height=12, bg="#1e1e1e", fg="#d1d1d1", selectbackground="#4b6eaf")
        self.cave_list.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        side = ttk.Frame(frame)
        side.pack(side="right", fill="y", padx=6)

        ttk.Label(side, text="Template:").pack()
        self.marker_select = ttk.Combobox(side, values=[str(i) for i in range(1, 21)], state="readonly", width=5)
        self.marker_select.current(0)
        self.marker_select.pack(pady=2)

        ttk.Button(side, text="Add Marker", command=self._cb_add_marker).pack(fill="x", pady=2)
        ttk.Button(side, text="Remove", command=self._cb_remove).pack(fill="x", pady=2)
        ttk.Button(side, text="Move UP", command=self._cb_move_up).pack(fill="x", pady=2)
        ttk.Button(side, text="Move DOWN", command=self._cb_move_down).pack(fill="x", pady=2)

        ttk.Separator(side).pack(fill="x", pady=8)

        ttk.Button(side, text="Save Route", command=self._cb_save).pack(fill="x", pady=2)
        ttk.Button(side, text="Load Route", command=self._cb_load).pack(fill="x", pady=2)

        ttk.Separator(side).pack(fill="x", pady=8)

        ttk.Button(side, text="▶ START CAVEBOT", command=self._cb_start).pack(fill="x", pady=2)
        ttk.Button(side, text="■ STOP CAVEBOT", command=self._cb_stop).pack(fill="x", pady=2)

    def _get_sequence_ui(self):
        return [int(self.cave_list.get(i)) for i in range(self.cave_list.size())]
    
    def _sync_engine_cavebot(self):
        seq = self._get_sequence_ui()
        self.engine.cavebot_set_sequence(seq)
    
    def _cb_add_marker(self):
        self.cave_list.insert("end", self.marker_select.get())
        self._sync_engine_cavebot()
    
    def _cb_remove(self):
        sel = self.cave_list.curselection()
        if sel:
            self.cave_list.delete(sel[0])
            self._sync_engine_cavebot()
    
    def _cb_move_up(self):
        sel = self.cave_list.curselection()
        if sel and sel[0] > 0:
            i = sel[0]
            val = self.cave_list.get(i)
            self.cave_list.delete(i)
            self.cave_list.insert(i-1, val)
            self.cave_list.select_set(i-1)
            self._sync_engine_cavebot()
    
    def _cb_move_down(self):
        sel = self.cave_list.curselection()
        if sel and sel[0] < self.cave_list.size() - 1:
            i = sel[0]
            val = self.cave_list.get(i)
            self.cave_list.delete(i)
            self.cave_list.insert(i+1, val)
            self.cave_list.select_set(i+1)
            self._sync_engine_cavebot()
    
    def _cb_save(self):
        name = simpledialog.askstring("Save route", "File name:")
        if name: self.engine.cavebot.save_to_file(f"{name}.json")
    
    def _cb_load(self):
        import tkinter.filedialog as fd
        f = fd.askopenfilename(initialdir="cavebots", filetypes=[("JSON","*.json")])
        if not f: return
        self.engine.cavebot.load_from_file(os.path.basename(f))
        self.cave_list.delete(0, "end")
        for m in self.engine.cavebot.sequence:
            self.cave_list.insert("end", str(m))
    
    def _cb_start(self):
        self.engine.start_cavebot()
    
    def _cb_stop(self):
        self.engine.stop_cavebot()

    # ======================================================
    # FOOTER PANELS
    # ======================================================
    def _create_hpm_mp_panel(self):
        frame = ttk.LabelFrame(self.root, text="HP / MP")
        frame.pack(fill="x", padx=6, pady=6)

        self.hp_lbl = ttk.Label(frame, text="HP: -", font=("Arial", 10, "bold"))
        self.hp_lbl.pack(anchor="w", padx=6, pady=3)

        self.mp_lbl = ttk.Label(frame, text="MP: -", font=("Arial", 10, "bold"))
        self.mp_lbl.pack(anchor="w", padx=6, pady=3)

    def _create_bot_control(self):
        frame = ttk.LabelFrame(self.root, text="Bot Control")
        frame.pack(fill="x", padx=6, pady=6)

        ttk.Button(frame, text="Start", command=self._btn_start).pack(side="left", padx=4)
        ttk.Button(frame, text="Stop", command=self._btn_stop).pack(side="left", padx=4)
        ttk.Button(frame, text="Pause Rotation", command=self._btn_pause).pack(side="left", padx=4)

        self.status_lbl = ttk.Label(frame, text="Status: -")
        self.status_lbl.pack(side="right", padx=6)

    def _btn_start(self):
        name = self.profile_mgr.current_name
        self.engine.start(name)

    def _btn_stop(self):
        self.engine.stop()

    def _btn_pause(self):
        self.engine.toggle_rotation()

    def _update_hp_mp(self, hp, mana):
        self.hp_lbl.config(text=f"HP: {hp:.1f}%")
        self.mp_lbl.config(text=f"MP: {mana:.1f}%")

    def _update_status(self, txt):
        self.status_lbl.config(text=f"Status: {txt}")