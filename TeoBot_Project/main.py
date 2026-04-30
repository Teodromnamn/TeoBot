import tkinter as tk
from ui.app import BotUI


def main():
    root = tk.Tk()

    # DPI awareness (optional but recommended for Tibia window capture)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor dpi
    except Exception:
        pass

    app = BotUI(root)

    root.mainloop()


if __name__ == "__main__":
    main()
