"""Read-only Win32 window checks. No process memory, hooks or input."""
import sys
import time


class WindowGuard:
    def __init__(self, title='Tibia', resume_delay=1., backend=None, clock=time.perf_counter):
        self.clock=clock
        self.resume_delay=resume_delay
        self.blocked=False
        self.ready_at=0.
        self.backend=backend
        if backend is None and sys.platform == 'win32':
            self.backend=Win32Window(title)

    def check(self):
        if self.backend is None:
            return {'status':'OK','active':None,'monitoring':False}
        try:
            status,active=self.backend.state()
        except Exception:
            status,active='BLAD_STANU_OKNA',None
        if status != 'OK':
            self.blocked=True
            return {'status':status,'active':active,'monitoring':True}
        if self.blocked:
            self.blocked=False
            self.ready_at=self.clock()+self.resume_delay
        return {'status':'WZNAWIANIE_OBRAZU' if self.clock()<self.ready_at else 'OK',
                'active':active,'monitoring':True}


class Win32Window:
    def __init__(self,title):
        import ctypes
        from ctypes import wintypes
        self.ctypes=ctypes;self.w=wintypes
        self.title=title.casefold()
        self.api=ctypes.WinDLL('user32',use_last_error=True)
        self.callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        signatures={
            'EnumWindows':([self.callback,wintypes.LPARAM],wintypes.BOOL),
            'GetWindowTextLengthW':([wintypes.HWND],ctypes.c_int),
            'GetWindowTextW':([wintypes.HWND,wintypes.LPWSTR,ctypes.c_int],ctypes.c_int),
            'IsWindowVisible':([wintypes.HWND],wintypes.BOOL),
            'IsIconic':([wintypes.HWND],wintypes.BOOL),
            'GetForegroundWindow':([],wintypes.HWND)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.api,name);fn.argtypes=args;fn.restype=result

    def state(self):
        found=[]
        def visit(hwnd,_):
            length=self.api.GetWindowTextLengthW(hwnd)
            if length:
                text=self.ctypes.create_unicode_buffer(length+1)
                self.api.GetWindowTextW(hwnd,text,length+1)
                # Match the client title prefix, not an OBS scene/editor mentioning Tibia.
                if text.value.casefold().startswith(self.title):found.append(hwnd)
            return True
        if not self.api.EnumWindows(self.callback(visit),0):
            raise OSError('EnumWindows failed')
        if not found:return 'BRAK_OKNA_GRY',False
        if len(found)!=1:return 'NIEJEDNOZNACZNE_OKNO_GRY',None
        hwnd=found[0];active=self.api.GetForegroundWindow()==hwnd
        if self.api.IsIconic(hwnd):return 'GRA_ZMINIMALIZOWANA',active
        if not self.api.IsWindowVisible(hwnd):return 'OKNO_GRY_UKRYTE',active
        return 'OK',active
