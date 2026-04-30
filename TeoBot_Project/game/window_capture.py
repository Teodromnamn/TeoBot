import win32gui
import win32ui
import ctypes
from PIL import Image
import numpy as np
import cv2
from config.settings import HP_RECT, MANA_RECT


def screenshot_window(window_name):
    hwnd = win32gui.FindWindow(None, window_name)
    if not hwnd:
        raise Exception(f"Window not found: {window_name}")

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

    img = Image.frombuffer(
        "RGB",
        (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
        bmpstr,
        "raw",
        "BGRX",
        0,
        1,
    )

    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    win32gui.DeleteObject(saveBitMap.GetHandle())

    #img.save("testAltaron.png")

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

def calculate_bar_percentage2(crop): #altaron
    arr = np.array(crop)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)

   
    # --- MASKI DO ODRZUCENIA ---
    
    # 🌑 Ciemne piksele
    dark_mask = (v < 60)

    # 🤎 Brązowy
    brown_mask = ((h > 10) & (h < 25) & (s > 80) & (v > 50) & (v < 170))

    not_ok_mask = dark_mask | brown_mask

    # Usuń piksele "nie OK" z maski OK (na wszelki wypadek)
    final_mask = ~not_ok_mask

    filled = np.sum(final_mask)
    total = arr.shape[0] * arr.shape[1]
    percent = (filled / total) * 100

    return percent


def read_hp_mana(img, hp_rect=HP_RECT, mana_rect=MANA_RECT):
    x, y, w, h = hp_rect
    hp_crop = img.crop((x, y, x + w, y + h))
    hp_percent = calculate_bar_percentage(hp_crop)

    x, y, w, h = mana_rect
    mana_crop = img.crop((x, y, x + w, y + h))
    mana_percent = calculate_bar_percentage(mana_crop)

    return hp_percent, mana_percent

