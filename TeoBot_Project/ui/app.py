import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os

from profiles.manager import ProfileManager
from logic.offensive import OffensiveLogic
from logic.healing import HealingLogic
from logic.potions import PotionLogic
from logic.support import SupportLogic
from logic.bot_engine import BotEngine
from profiles.defaults import DEFAULT_OFFENSIVE, DEFAULT_HEALING, DEFAULT_POTIONS, DEFAULT_SUPPORT

from ui.dialogs import ItemDialog


class BotUI:
    """
    Warstwa UI — zarządza widżetami, profilami i komunikacją z BotEngine.
    Engine działa całkowicie poza UI.
    UI jedynie:
    - wyświetla zakładki
    - zarządza profilami
    - wypełnia treeview
    - wysyła dane profilu do logic modules
    - uruchamia BotEngine
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Teo Bot")

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
            self._update_hp_mp,      # callback do aktualizacji HP/MP
            self._update_status      # callback statusu
        )

        # UI
        self._build_ui()

        # Load default
        self._set_current_profile(self.profile_mgr.current_name)

    # ======================================================
    # BUILD UI
    # ======================================================
    def _build_ui(self):
        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # Tabs
        self._create_profiles_tab()
        self._create_offensive_tab()
        self._create_healing_tab()
        self._create_potions_tab()
        self._create_support_tab()
        #self._create_cavebot_tab()


        # Footer
        self._create_hpm_mp_panel()
        self._create_bot_control()

    # ======================================================
    # PROFILES TAB
    # ======================================================
    def _create_profiles_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Profiles")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=6, padx=6)

        ttk.Button(btn_frame, text="New", command=self._new_profile).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Save", command=self._save_profile).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Copy", command=self._copy_profile).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Delete", command=self._delete_profile).pack(side="left", padx=3)

        load_frame = ttk.Frame(frame)
        load_frame.pack(fill="x", pady=6, padx=6)

        ttk.Label(load_frame, text="Profile: ").pack(side="left")
        self.profile_combo = ttk.Combobox(load_frame, state="readonly", width=25)
        self.profile_combo.pack(side="left")
        ttk.Button(load_frame, text="Load", command=self._load_selected_profile).pack(side="left", padx=4)

        self.label_current = ttk.Label(frame, text="Current: -")
        self.label_current.pack(anchor="w", padx=6, pady=6)

    # PROFILE FUNCTIONS
    def _new_profile(self):
        name = simpledialog.askstring("New Profile", "Enter name:")
        if not name:
            return
        self.profile_mgr.new_profile(name)
        self.profile_mgr.save_all()
        self._update_profile_combo()
        self._set_current_profile(name)

    def _copy_profile(self):
        src = self.profile_mgr.current_name
        new_name = simpledialog.askstring("Copy profile", "New name:")
        if not new_name:
            return
        self.profile_mgr.duplicate(src, new_name)
        self.profile_mgr.save_all()
        self._update_profile_combo()

    def _delete_profile(self):
        name = self.profile_mgr.current_name
        if name == "Default":
            messagebox.showwarning("Error", "Cannot delete Default profile!")
            return
        if messagebox.askyesno("Delete", f"Delete profile '{name}'?"):
            self.profile_mgr.delete(name)
            self.profile_mgr.save_all()
            self._update_profile_combo()
            if self.profile_mgr.profiles:
                new_first = next(iter(self.profile_mgr.profiles.keys()))
                self._set_current_profile(new_first)

    def _load_selected_profile(self):
        name = self.profile_combo.get()
        if name:
            self._set_current_profile(name)

    def _update_profile_combo(self):
        self.profile_combo["values"] = list(self.profile_mgr.profiles.keys())
        if self.profile_mgr.current_name:
            self.profile_combo.set(self.profile_mgr.current_name)

    def _set_current_profile(self, name):
        """Wgrywa profil do UI i logic modules."""
        if name not in self.profile_mgr.profiles:
            return

        self.profile_mgr.set_current(name)
        self.label_current.config(text=f"Current: {name}")
        self._update_profile_combo()

        p = self.profile_mgr.current

        # Fill treeviews
        self._fill_tree(self.off_tree, p["offensive"], "off")
        self._fill_tree(self.heal_tree, p["healing"], "heal")
        self._fill_tree(self.pot_tree, p["potions"], "pot")
        self._fill_tree(self.sup_tree, p["support"], "sup")

        # Push data to logic modules
        self.logic["offensive"].update(p["offensive"])
        self.logic["healing"].update(p["healing"])
        self.logic["potions"].update(p["potions"])
        self.logic["support"].update(p["support"])

    def _save_profile(self):
        """Save to JSON + update logic modules."""
        name = self.profile_mgr.current_name
        if not name:
            return

        profile = {
            "offensive": self._collect_data_from_tree(self.off_tree, "off"),
            "healing": self._collect_data_from_tree(self.heal_tree, "heal"),
            "potions": self._collect_data_from_tree(self.pot_tree, "pot"),
            "support": self._collect_data_from_tree(self.sup_tree, "sup"),
        }

        self.profile_mgr.profiles[name] = profile
        self.profile_mgr.save_all()

        # update logic
        self.logic["offensive"].update(profile["offensive"])
        self.logic["healing"].update(profile["healing"])
        self.logic["potions"].update(profile["potions"])
        self.logic["support"].update(profile["support"])

        messagebox.showinfo("Saved", f"Profile '{name}' saved.")

    # ======================================================
    # AUTO-REFRESH LOGIC MODULES
    # ======================================================
    def _refresh_logic(self):
        """
        Odczytuje dane z TreeView i aktualizuje logic modules.
        Dzięki temu bot natychmiast widzi zmiany.
        """
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
                tree.insert("", "end",
                            values=(item["name"], item["key"], item["priority"],
                                    item["mana_cost"], item["cd"], item["type"]))
            elif section == "heal":
                tree.insert("", "end",
                            values=(item["name"], item["key"], item["hp%"],
                                    item["mana_cost"], item["cd"]))
            elif section == "pot":
                tree.insert("", "end",
                            values=(item["type"], item["key"], item["%"], item["cd"]))
            elif section == "sup":
                icon = "☑" if item["enabled"] else "☐"
                tree.insert("", "end",
                            values=(item["name"], item["key"], item["cd"], icon))

    def _collect_data_from_tree(self, tree, section):
        out = []
        for iid in tree.get_children():
            vals = tree.item(iid, "values")

            if section == "off":
                out.append({
                    "name": vals[0],
                    "key": vals[1],
                    "priority": int(vals[2]),
                    "mana_cost": float(vals[3]),
                    "cd": float(vals[4]),
                    "type": vals[5],
                })
            if section == "heal":
                out.append({
                    "name": vals[0],
                    "key": vals[1],
                    "hp%": float(vals[2]),
                    "mana_cost": float(vals[3]),
                    "cd": float(vals[4]),
                })
            if section == "pot":
                out.append({
                    "type": vals[0],
                    "key": vals[1],
                    "%": float(vals[2]),
                    "cd": float(vals[3]),
                })
            if section == "sup":
                out.append({
                    "name": vals[0],
                    "key": vals[1],
                    "cd": float(vals[2]),
                    "enabled": vals[3] == "☑"
                })

        return out

    # ======================================================
    # OFFENSIVE TAB
    # ======================================================
    def _create_offensive_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Offensive")

        cols = ("name", "key", "priority", "mana_cost", "cd", "type")
        self.off_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        for c in cols:
            self.off_tree.heading(c, text=c.capitalize())
            self.off_tree.column(c, width=110)

        self.off_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=6)

        ttk.Button(btnf, text="Add", command=self._add_off).pack(side="left", padx=4)
        ttk.Button(btnf, text="Edit", command=self._edit_off).pack(side="left", padx=4)
        ttk.Button(btnf, text="Del", command=lambda: self._delete_selected(self.off_tree)).pack(side="left", padx=4)

    def _add_off(self):
        schema = [
            ("name", "entry", {"default": ""}),
            ("key", "entry", {"required": True}),
            ("priority", "spin_int", {"default": 10, "range": (1, 20)}),
            ("mana_cost", "spin_float", {"default": 0}),
            ("cd", "spin_float", {"default": 1.0}),
            ("type", "combo", {"values": ["spell", "rune"], "default": "spell"}),
        ]
        dlg = ItemDialog(self.root, "Add Offensive Spell", schema)
        if dlg.result:
            v = dlg.result
            self.off_tree.insert("", "end",
                                 values=(v["name"], v["key"], v["priority"],
                                         v["mana_cost"], v["cd"], v["type"]))
            self._refresh_logic()

    def _edit_off(self):
        sel = self.off_tree.selection()
        if not sel:
            return
        iid = sel[0]
        values = self.off_tree.item(iid, "values")

        data = {
            "name": values[0],
            "key": values[1],
            "priority": int(values[2]),
            "mana_cost": float(values[3]),
            "cd": float(values[4]),
            "type": values[5],
        }

        schema = [
            ("name", "entry", {"default": data["name"]}),
            ("key", "entry", {"default": data["key"], "required": True}),
            ("priority", "spin_int", {"default": data["priority"], "range": (1, 20)}),
            ("mana_cost", "spin_float", {"default": data["mana_cost"]}),
            ("cd", "spin_float", {"default": data["cd"]}),
            ("type", "combo", {"values": ["spell", "rune"], "default": data["type"]}),
        ]
        dlg = ItemDialog(self.root, "Edit Offensive", schema, data)
        if dlg.result:
            v = dlg.result
            self.off_tree.item(iid,
                               values=(v["name"], v["key"], v["priority"],
                                       v["mana_cost"], v["cd"], v["type"]))
            self._refresh_logic()

    # ======================================================
    # HEALING TAB
    # ======================================================
    def _create_healing_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Healing")

        cols = ("name", "key", "hp%", "mana_cost", "cd")
        self.heal_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        for c in cols:
            self.heal_tree.heading(c, text=c.capitalize())
            self.heal_tree.column(c, width=110)

        self.heal_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=6)

        ttk.Button(btnf, text="Add", command=self._add_heal).pack(side="left", padx=4)
        ttk.Button(btnf, text="Edit", command=self._edit_heal).pack(side="left", padx=4)
        ttk.Button(btnf, text="Del", command=lambda: self._delete_selected(self.heal_tree)).pack(side="left", padx=4)

    def _add_heal(self):
        schema = [
            ("name", "entry", {"default": ""}),
            ("key", "entry", {"required": True}),
            ("hp%", "spin_float", {"default": 50}),
            ("mana_cost", "spin_float", {"default": 0}),
            ("cd", "spin_float", {"default": 1}),
        ]
        dlg = ItemDialog(self.root, "Add Healing", schema)
        if dlg.result:
            v = dlg.result
            self.heal_tree.insert("", "end",
                                  values=(v["name"], v["key"], v["hp%"],
                                          v["mana_cost"], v["cd"]))
            self._refresh_logic()

    def _edit_heal(self):
        sel = self.heal_tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self.heal_tree.item(iid, "values")

        data = {
            "name": vals[0],
            "key": vals[1],
            "hp%": float(vals[2]),
            "mana_cost": float(vals[3]),
            "cd": float(vals[4]),
        }

        schema = [
            ("name", "entry", {"default": data["name"]}),
            ("key", "entry", {"default": data["key"]}),
            ("hp%", "spin_float", {"default": data["hp%"]}),
            ("mana_cost", "spin_float", {"default": data["mana_cost"]}),
            ("cd", "spin_float", {"default": data["cd"]}),
        ]
        dlg = ItemDialog(self.root, "Edit Healing", schema, data)
        if dlg.result:
            v = dlg.result
            self.heal_tree.item(iid,
                                values=(v["name"], v["key"], v["hp%"],
                                        v["mana_cost"], v["cd"]))
            self._refresh_logic()

    # ======================================================
    # POTIONS TAB
    # ======================================================
    def _create_potions_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Potions")

        cols = ("type", "key", "percent", "cd")
        self.pot_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        for c in cols:
            self.pot_tree.heading(c, text=c.capitalize())
            self.pot_tree.column(c, width=110)

        self.pot_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=6)

        ttk.Button(btnf, text="Add", command=self._add_pot).pack(side="left", padx=4)
        ttk.Button(btnf, text="Edit", command=self._edit_pot).pack(side="left", padx=4)
        ttk.Button(btnf, text="Del", command=lambda: self._delete_selected(self.pot_tree)).pack(side="left", padx=4)

    def _add_pot(self):
        schema = [
            ("type", "combo", {"values": ["hp", "mana"], "default": "mana"}),
            ("key", "entry", {"required": True}),
            ("percent", "spin_float", {"default": 50}),
            ("cd", "spin_float", {"default": 1}),
        ]
        dlg = ItemDialog(self.root, "Add Potion", schema)
        if dlg.result:
            v = dlg.result
            self.pot_tree.insert("", "end",
                                 values=(v["type"], v["key"], v["percent"], v["cd"]))
            self._refresh_logic()

    def _edit_pot(self):
        sel = self.pot_tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self.pot_tree.item(iid, "values")

        data = {
            "type": vals[0],
            "key": vals[1],
            "percent": float(vals[2]),
            "cd": float(vals[3]),
        }

        schema = [
            ("type", "combo", {"values": ["hp", "mana"], "default": data["type"]}),
            ("key", "entry", {"default": data["key"]}),
            ("percent", "spin_float", {"default": data["percent"]}),
            ("cd", "spin_float", {"default": data["cd"]}),
        ]
        dlg = ItemDialog(self.root, "Edit Potion", schema, data)
        if dlg.result:
            v = dlg.result
            self.pot_tree.item(iid,
                               values=(v["type"], v["key"], v["percent"], v["cd"]))
            self._refresh_logic()

    # ======================================================
    # SUPPORT TAB
    # ======================================================
    def _create_support_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Support")

        cols = ("name", "key", "cd", "enabled")
        self.sup_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        for c in cols:
            self.sup_tree.heading(c, text=c.capitalize())
            self.sup_tree.column(c, width=110)

        self.sup_tree.pack(fill="both", expand=True, padx=6, pady=6)

        btnf = ttk.Frame(frame)
        btnf.pack(fill="x", padx=6, pady=6)

        ttk.Button(btnf, text="Add", command=self._add_sup).pack(side="left", padx=4)
        ttk.Button(btnf, text="Edit", command=self._edit_sup).pack(side="left", padx=4)
        ttk.Button(btnf, text="Del", command=lambda: self._delete_selected(self.sup_tree)).pack(side="left", padx=4)

    def _add_sup(self):
        schema = [
            ("name", "entry", {"default": ""}),
            ("key", "entry", {"required": True}),
            ("cd", "spin_float", {"default": 1}),
            ("enabled", "check", {"default": True}),
        ]
        dlg = ItemDialog(self.root, "Add Support", schema)
        if dlg.result:
            v = dlg.result
            icon = "☑" if v["enabled"] else "☐"
            self.sup_tree.insert("", "end",
                                 values=(v["name"], v["key"], v["cd"], icon))
            self._refresh_logic()

    def _edit_sup(self):
        sel = self.sup_tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self.sup_tree.item(iid, "values")

        data = {
            "name": vals[0],
            "key": vals[1],
            "cd": float(vals[2]),
            "enabled": vals[3] == "☑"
        }

        schema = [
            ("name", "entry", {"default": data["name"]}),
            ("key", "entry", {"default": data["key"]}),
            ("cd", "spin_float", {"default": data["cd"]}),
            ("enabled", "check", {"default": data["enabled"]})
        ]
        dlg = ItemDialog(self.root, "Edit Support", schema, data)
        if dlg.result:
            v = dlg.result
            icon = "☑" if v["enabled"] else "☐"
            self.sup_tree.item(iid,
                               values=(v["name"], v["key"], v["cd"], icon))
            self._refresh_logic()
            
    # ======================================================
    # CAVEBOT
    # ======================================================
    def _create_cavebot_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Cavebot")

        # ---- LISTA MARKERÓW ----
        self.cave_list = tk.Listbox(frame, height=12)
        self.cave_list.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        # ---- PANEL BOCZNY ----
        side = ttk.Frame(frame)
        side.pack(side="right", fill="y", padx=6)

        # Dropdown template
        ttk.Label(side, text="Template:").pack()
        self.marker_select = ttk.Combobox(
            side,
            values=[str(i) for i in range(1, 21)],
            state="readonly",
            width=5
        )
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
    
    # --- SAVE / LOAD ---
    
    def _cb_save(self):
        name = simpledialog.askstring("Save route", "File name:")
        if name:
            self.engine.cavebot.save_to_file(f"{name}.json")
    
    def _cb_load(self):
        import tkinter.filedialog as fd
        f = fd.askopenfilename(initialdir="cavebots", filetypes=[("JSON","*.json")])
        if not f:
            return
    
        self.engine.cavebot.load_from_file(os.path.basename(f))
    
        # wczytaj do UI
        self.cave_list.delete(0, "end")
        for m in self.engine.cavebot.sequence:
            self.cave_list.insert("end", str(m))
    
    # --- START / STOP ---
    
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

        self.hp_lbl = ttk.Label(frame, text="HP: -")
        self.hp_lbl.pack(anchor="w", padx=6, pady=3)

        self.mp_lbl = ttk.Label(frame, text="MP: -")
        self.mp_lbl.pack(anchor="w", padx=6, pady=3)

    def _create_bot_control(self):
        frame = ttk.LabelFrame(self.root, text="Bot Control")
        frame.pack(fill="x", padx=6, pady=6)

        ttk.Button(frame, text="Start", command=self._btn_start).pack(side="left", padx=4)
        ttk.Button(frame, text="Stop", command=self._btn_stop).pack(side="left", padx=4)
        ttk.Button(frame, text="Pause Rotation", command=self._btn_pause).pack(side="left", padx=4)

        self.status_lbl = ttk.Label(frame, text="Status: -")
        self.status_lbl.pack(side="right", padx=6)

    # Bot control handlers
    def _btn_start(self):
        name = self.profile_mgr.current_name
        self.engine.start(name)

    def _btn_stop(self):
        self.engine.stop()

    def _btn_pause(self):
        self.engine.toggle_rotation()

    # CALLS FROM ENGINE
    def _update_hp_mp(self, hp, mana):
        self.hp_lbl.config(text=f"HP: {hp:.1f}%")
        self.mp_lbl.config(text=f"MP: {mana:.1f}%")

    def _update_status(self, txt):
        self.status_lbl.config(text=f"Status: {txt}")

    # DELETE ROW
    def _delete_selected(self, tree):
        for s in tree.selection():
            tree.delete(s)
        self._refresh_logic()
