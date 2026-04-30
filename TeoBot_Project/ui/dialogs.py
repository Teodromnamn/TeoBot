import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

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
                messagebox.showerror("Error", f"Field '{field}' is required.")
                return
            if raw == "":
                out[field] = opts.get("default", "")
                continue
            # type conversions
            if wtype == "spin_int":
                try:
                    v = int(raw)
                except:
                    messagebox.showerror("Error", f"Field '{field}' must be a int number.")
                    return
                r = opts.get("range")
                if r and not (r[0] <= v <= r[1]):
                    messagebox.showerror("Error", f"'{field}' must be in range {r}.")
                    return
                out[field] = v
            elif wtype == "spin_float":
                try:
                    v = float(raw)
                except:
                    messagebox.showerror("Error", f"Field '{field}' must be a number.")
                    return
                r = opts.get("range")
                if r and not (r[0] <= v <= r[1]):
                    messagebox.showerror("Error", f"'{field}' must be in range {r}.")
                    return
                out[field] = v
            elif wtype == "combo":
                if opts.get("values") and raw not in opts.get("values"):
                    messagebox.showerror("Error", f"'{field}' must be one of {opts.get('values')}.")
                    return
                out[field] = raw
            else:
                out[field] = raw
        self.result = out
        self.destroy()
