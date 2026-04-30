import win32con
import win32api
import time
import win32gui
from game.consts import VK



def send_key(hwnd, key):
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101

    key_u = key.upper().strip()

    if key_u in VK:
        vk = VK[key_u]
    else:
        vk = ord(key_u)

    win32gui.PostMessage(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, WM_KEYUP, vk, 0)


# Helper: pack coordinates to lParam (low word = x, high word = y)
def _mk_lparam(x: int, y: int) -> int:
    return (y << 16) | (x & 0xFFFF)

def click_at(hwnd, x_client: int, y_client: int, button='left'):
    """
    Wyślij klik w tle do okna HWND w koordynatach klienta (x_client, y_client).
    Nie porusza fizycznego kursora.
    """
    if button != 'left':
        raise NotImplementedError("Only left supported")

    WM_LBUTTONDOWN = win32con.WM_LBUTTONDOWN
    WM_LBUTTONUP = win32con.WM_LBUTTONUP
    MK_LBUTTON = win32con.MK_LBUTTON

    lparam = _mk_lparam(x_client, y_client)
    # wParam zwykle zawiera flagę przycisków (MK_*)
    wparam = MK_LBUTTON

    # PostMessage (asynchroniczne)
    win32gui.PostMessage(hwnd, WM_LBUTTONDOWN, wparam, lparam)
    time.sleep(0.03)  # krótka przerwa
    win32gui.PostMessage(hwnd, WM_LBUTTONUP, 0, lparam)
