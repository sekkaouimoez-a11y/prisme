"""Couleurs des écrans : rampe gamma de Windows (par écran) + vibrance et teinte du pilote NVIDIA (NVAPI).
Les deux agissent à la sortie de la carte graphique : aucune image ajoutée, donc ni latence ni FPS en moins, même en
plein écran. C'est aussi ce que font le panneau NVIDIA et VibranceGUI."""
import ctypes
import os
from ctypes import wintypes as w
from functools import lru_cache
from pathlib import Path

# Valeurs neutres ; saturation : en % comme la « vibrance numérique » du panneau NVIDIA (50 = normal).
NEUTRE = {"luminosite": 0.0, "contraste": 0.0, "exposition": 0.0, "gamma": 0.0, "saturation": 50, "rotation": 0,
          "temperature": 0.0, "teinte": 0.0, "rouge": 0.0, "vert": 0.0, "bleu": 0.0}
BORNES = {k: (0, 100) if k == "saturation" else (0, 359) if k == "rotation" else (-1.0, 1.0) for k in NEUTRE}
PREREGLAGES = {
    "Neutre": {},
    "Gaming": {"luminosite": 0.2, "contraste": 0.15, "gamma": 0.1, "saturation": 80},
    "Filmique": {"contraste": 0.2, "gamma": -0.05, "saturation": 45, "temperature": 0.15},
    "Chaud": {"saturation": 55, "temperature": 0.4},
    "Froid": {"saturation": 55, "temperature": -0.4},
    "Éclatant": {"contraste": 0.1, "saturation": 90},
    "Doux": {"contraste": -0.1, "saturation": 35},
    "Nuit": {"luminosite": -0.1, "temperature": 0.7, "saturation": 45},
}


def courbe(r, canal, x):
    """Sortie (0..1) du canal 0, 1 ou 2 (rouge, vert, bleu) pour l'entrée x (0..1). Croissante : sinon Windows refuse."""
    x *= 2 ** r["exposition"]
    x **= 2 ** -r["gamma"]  # gamma > 0 : tons moyens plus clairs
    x = (x - 0.5) * (1 + r["contraste"]) + 0.5
    x += 0.5 * r["luminosite"]
    t, n = r["temperature"], r["teinte"]
    x *= (1 + 0.25 * t, 1 - 0.25 * n, 1 - 0.25 * t)[canal]  # chaud : + rouge − bleu ; teinte > 0 : vers le magenta
    x *= 1 + 0.5 * (r["rouge"], r["vert"], r["bleu"])[canal]
    return min(max(x, 0.0), 1.0)


def rampe(r, origine, force=1.0):
    """Rampe gamma de Windows (768 valeurs de 0 à 65535 : 256 rouges, 256 verts, 256 bleus) : la courbe de r posée par-dessus
    la rampe d'origine (étalonnage de l'écran). force < 1 rapproche le résultat de l'origine."""
    res = []
    for c in range(3):
        o = origine[c * 256:(c + 1) * 256]
        for i in range(256):
            y = courbe(r, c, i / 255) * 255
            k = min(int(y), 254)
            v = o[k] + (o[k + 1] - o[k]) * (y - k)
            res.append(round(o[i] + (v - o[i]) * force))
    return res


def niveau(pourcent, mini, maxi, defaut):
    """Saturation en % (50 = normal) -> niveau de vibrance du pilote, qui va de mini à maxi avec defaut au milieu."""
    p = (pourcent - 50) / 50
    return round(defaut + p * ((maxi - defaut) if p >= 0 else (defaut - mini)))


def plan(profils, ecrans, devant, apercu=None):
    """Profil à montrer sur chaque écran : {écran: profil, ou None pour les couleurs d'origine}.
    devant : (programme, titre, écran) de la fenêtre au premier plan ; apercu : profil en cours de réglage, montré à la place.
    Un profil sans cibles vaut toujours ; un profil à cibles, quand l'une est devant. Son écran vide = tous les écrans
    (sans cibles) ou celui de la fenêtre (avec cibles)."""
    exe, titre, ecran = devant
    voulu = dict.fromkeys(ecrans)

    def poser(p):
        for e in [p["ecran"]] if p["ecran"] else ecrans if not p["cibles"] else [ecran]:
            if e in voulu:
                voulu[e] = p

    for p in profils:
        if not p["cibles"]:
            poser(p)
    p = apercu or next((p for p in profils
                        if any(c["exe"] == exe and (not c["seule"] or c["titre"] == titre) for c in p["cibles"])), None)
    if p:
        poser(p)
    return voulu


# --- Windows -------------------------------------------------------------------------------------------------------

user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
user32.GetForegroundWindow.restype = w.HWND
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
user32.MonitorFromWindow.restype = w.HMONITOR
user32.GetMonitorInfoW.argtypes = [w.HMONITOR, ctypes.c_void_p]
user32.GetWindow.argtypes = [w.HWND, w.UINT]
user32.GetWindow.restype = w.HWND
user32.IsWindowVisible.argtypes = [w.HWND]
user32.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
user32.GetShellWindow.restype = w.HWND
WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, w.LPARAM]
MONITORENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HMONITOR, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)
user32.EnumDisplayMonitors.argtypes = [w.HDC, ctypes.c_void_p, MONITORENUMPROC, w.LPARAM]
gdi32.CreateDCW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p]
gdi32.CreateDCW.restype = w.HDC
gdi32.DeleteDC.argtypes = [w.HDC]
gdi32.GetDeviceGammaRamp.argtypes = [w.HDC, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.argtypes = [w.HDC, ctypes.c_void_p]
kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel32.OpenProcess.restype = w.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel32.CloseHandle.argtypes = [w.HANDLE]
kernel32.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = w.HANDLE
kernel32.Process32FirstW.argtypes = kernel32.Process32NextW.argtypes = [w.HANDLE, ctypes.c_void_p]
dwmapi = ctypes.windll.dwmapi
dwmapi.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]


class MONITORINFOEX(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD),
                ("szDevice", w.WCHAR * 32)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
                ("pcPriClassBase", w.LONG), ("dwFlags", w.DWORD), ("szExeFile", w.WCHAR * 260)]


def _info(hmon):
    mi = MONITORINFOEX(cbSize=ctypes.sizeof(MONITORINFOEX))
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    return mi


def moniteurs():
    """Écrans branchés : [{"id": "\\\\.\\DISPLAY1", "nom": "Écran 1", "taille": "1920×1080", "principal": True}]."""
    res = []

    def un(hmon, *_):
        mi = _info(hmon)
        r = mi.rcMonitor
        res.append({"id": mi.szDevice, "nom": "Écran " + mi.szDevice.rsplit("DISPLAY", 1)[-1],
                    "taille": f"{r.right - r.left}×{r.bottom - r.top}", "principal": bool(mi.dwFlags & 1)})
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(un), 0)
    return res


def ecran_de(hwnd):
    return _info(user32.MonitorFromWindow(hwnd, 2)).szDevice  # 2 = MONITOR_DEFAULTTONEAREST


def pid_de(hwnd):
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, pid)
    return pid.value


def titre_de(hwnd):
    t = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, t, 256)
    return t.value.strip()


def processus():
    """Liste des processus, sans avoir à les ouvrir : [(numéro, "programme.exe")]."""
    res = []
    snap = kernel32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    pe = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
    ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        res.append((pe.th32ProcessID, pe.szExeFile))
        ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    return res


@lru_cache(maxsize=32)  # shortcut: un numéro de processus réutilisé par Windows garderait l'ancien nom ; rare, à revoir si gênant
def _exe_par_liste(pid):
    """Nom du programme par la liste des processus, qui n'a pas besoin d'ouvrir le processus : l'anti-triche de Valorant
    (Vanguard) en interdit l'accès, et QueryFullProcessImageNameW échoue alors."""
    return next((exe for p, exe in processus() if p == pid), "")


def programme(hwnd):
    """Nom du programme d'une fenêtre (« VALORANT-Win64-Shipping.exe »), "" si inconnu."""
    pid = pid_de(hwnd)
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        tampon, n = ctypes.create_unicode_buffer(1024), w.DWORD(1024)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, tampon, ctypes.byref(n))
        kernel32.CloseHandle(h)
        if ok:
            return Path(tampon.value).name
    return _exe_par_liste(pid)


def devant():
    """Fenêtre au premier plan : (hwnd, programme, titre, écran), ou None (bascule Alt+Tab en cours)."""
    hwnd = user32.GetForegroundWindow()
    return (hwnd, programme(hwnd), titre_de(hwnd), ecran_de(hwnd)) if hwnd else None


def fenetres_ouvertes():
    """Fenêtres ouvertes comme dans Alt+Tab, la plus en avant d'abord, sans celles de ce logiciel : [{"exe", "titre"}]."""
    res = []

    def une(hwnd, _):
        cachee = w.DWORD()  # applis Windows en veille : « visibles » mais invisibles à l'écran
        dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cachee), 4)  # 14 = DWMWA_CLOAKED
        outil = user32.GetWindowLongW(hwnd, -20) & 0x08000080  # GWL_EXSTYLE : WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if (user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4) and not cachee.value  # 4 = GW_OWNER
                and not outil and hwnd != user32.GetShellWindow() and pid_de(hwnd) != os.getpid()):
            titre, exe = titre_de(hwnd), programme(hwnd)
            if titre and exe:
                res.append({"exe": exe, "titre": titre})
        return True

    user32.EnumWindows(WNDENUMPROC(une), 0)
    return res


def lire_rampe(ecran):
    dc = gdi32.CreateDCW("DISPLAY", ecran, None, None)
    r = (w.WORD * 768)()
    ok = gdi32.GetDeviceGammaRamp(dc, r)
    gdi32.DeleteDC(dc)
    return list(r) if ok else [i * 257 for i in range(256)] * 3


def poser_rampe(ecran, valeurs):
    """Faux si Windows refuse (il bloque les rampes trop éloignées de la normale)."""
    dc = gdi32.CreateDCW("DISPLAY", ecran, None, None)
    ok = gdi32.SetDeviceGammaRamp(dc, (w.WORD * 768)(*valeurs))
    gdi32.DeleteDC(dc)
    return bool(ok)


# --- NVIDIA --------------------------------------------------------------------------------------------------------

class _DVC(ctypes.Structure):  # NV_DISPLAY_DVC_INFO_EX
    _fields_ = [("version", ctypes.c_uint), ("courant", ctypes.c_int), ("mini", ctypes.c_int), ("maxi", ctypes.c_int),
                ("defaut", ctypes.c_int)]


class _HUE(ctypes.Structure):  # NV_DISPLAY_HUE_INFO
    _fields_ = [("version", ctypes.c_uint), ("courant", ctypes.c_uint), ("defaut", ctypes.c_uint)]


class Nvidia:
    """Vibrance numérique (saturation) et teinte du pilote NVIDIA, par écran. Sans carte NVIDIA, ecrans reste vide.
    Numéros des fonctions de nvapi_QueryInterface : ceux qu'utilise VibranceGUI."""

    def __init__(self):
        self.ecrans = {}  # "\\.\DISPLAY1" -> poignée NVAPI
        try:
            qi = ctypes.WinDLL("nvapi64.dll").nvapi_QueryInterface
        except OSError:
            return
        qi.restype, qi.argtypes = ctypes.c_void_p, [ctypes.c_uint]

        def f(num, *args):
            p = qi(num)
            return ctypes.CFUNCTYPE(ctypes.c_int, *args)(p) if p else None

        h = ctypes.c_void_p
        self._enum = f(0x9ABDD40D, ctypes.c_uint, ctypes.POINTER(h))  # EnumNvidiaDisplayHandle
        self._nom = f(0x22A78B05, h, ctypes.c_char_p)  # GetAssociatedNvidiaDisplayName
        self._get_dvc = f(0x0E45002D, h, ctypes.c_uint, ctypes.POINTER(_DVC))  # GetDVCInfoEx
        self._set_dvc = f(0x4A82C2B1, h, ctypes.c_uint, ctypes.POINTER(_DVC))  # SetDVCLevelEx
        self._get_hue = f(0x95B64341, h, ctypes.c_uint, ctypes.POINTER(_HUE))  # GetHUEInfo
        self._set_hue = f(0xF5A0F22C, h, ctypes.c_uint, ctypes.c_uint)  # SetHUEAngle
        init = f(0x0150E828)  # Initialize
        if init and all((self._enum, self._nom, self._get_dvc, self._set_dvc, self._get_hue, self._set_hue)) \
                and init() == 0:
            self.relister()

    def relister(self):
        """Les poignées changent quand Windows rebranche un écran (veille, changement de mode)."""
        self.ecrans, k = {}, 0
        while True:
            h = ctypes.c_void_p()
            if self._enum(k, ctypes.byref(h)) != 0:  # -7 : fin de la liste
                return
            nom = ctypes.create_string_buffer(64)
            if self._nom(h, nom) == 0:
                self.ecrans[nom.value.decode()] = h
            k += 1

    def vibrance(self, ecran):
        """(courant, mini, maxi, defaut) du pilote, ou None."""
        d = _DVC(version=ctypes.sizeof(_DVC) | 1 << 16)
        if ecran in self.ecrans and self._get_dvc(self.ecrans[ecran], 0, ctypes.byref(d)) == 0:
            return d.courant, d.mini, d.maxi, d.defaut
        return None

    def teinte(self, ecran):
        d = _HUE(version=ctypes.sizeof(_HUE) | 1 << 16)
        if ecran in self.ecrans and self._get_hue(self.ecrans[ecran], 0, ctypes.byref(d)) == 0:
            return d.courant
        return None

    def poser(self, ecran, vibrance, teinte):
        """Pose le niveau de vibrance (celui du pilote) et l'angle de teinte. Faux en cas d'échec."""
        if ecran not in self.ecrans:
            return False
        d = _DVC(version=ctypes.sizeof(_DVC) | 1 << 16)
        h = self.ecrans[ecran]
        if self._get_dvc(h, 0, ctypes.byref(d)) != 0:
            return False
        d.courant = vibrance
        return self._set_dvc(h, 0, ctypes.byref(d)) == 0 and self._set_hue(h, 0, int(teinte) % 360) == 0
