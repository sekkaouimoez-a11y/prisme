"""Latence CPU : la « Game Latency (CPU) » de Valorant, le temps que met le PC à préparer chaque image. Bilan de ce qui la
fait monter (alimentation, Mode Jeu, réglages de Valorant, applis en fond, RAM) et correction en un clic de ce que Windows
permet sans droits administrateur. Rien n'est lu ni écrit dans la mémoire du jeu (Vanguard).
Pas de réglage de priorité : Valorant se met lui-même en Haute quand on joue et en Normale quand il passe derrière."""
import ctypes
import os
import subprocess
import time
import uuid
import winreg
from ctypes import wintypes as w
from functools import lru_cache
from pathlib import Path

import couleurs as c

JEU = "VALORANT-Win64-Shipping.exe"
CONFIG = Path(os.environ.get("LOCALAPPDATA", "")) / "VALORANT" / "Saved" / "Config"
PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"  # mode d'alimentation « Performances élevées »
PROC, PROC_MIN = "54533251-82be-4824-96c1-47b60b740d00", "893dee8e-2bef-41e0-89c6-b55d0929964c"  # « État minimal du processeur »
# Toujours là et impossibles à fermer : pas comptés parmi les applis en fond.
SYSTEME = {"[system process]", "system", "registry", "memory compression", "secure system", "csrss.exe", "dwm.exe",
           "audiodg.exe", "svchost.exe", "lsass.exe", "services.exe", "msmpeng.exe", "vgc.exe", JEU.lower()}
# Réglages de Valorant qui coûtent du calcul à chaque image : (clé, nom, valeur la plus légère).
GRAPHISMES = [("MaterialQuality", "Matériaux", "0"), ("DetailQuality", "Détails", "0"), ("TextureQuality", "Textures", "0"),
              ("UIQuality", "Interface", "0"), ("BloomQuality", "Bloom", "0"), ("ShadowsEnabled", "Ombres", "False"),
              ("DisableDistortion", "Distorsion", "True")]

kernel32, powrprof = ctypes.windll.kernel32, ctypes.windll.powrprof
kernel32.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.c_void_p] * 4
kernel32.LocalFree.argtypes = [ctypes.c_void_p]


def lire_ini(texte):
    """Lignes « EAresIntSettingName::Cle=valeur » ou « Cle=valeur » -> {"Cle": "valeur"}."""
    res = {}
    for ligne in texte.splitlines():
        cle, egal, val = ligne.partition("=")
        if egal and not cle.startswith(("[", ";")):
            res[cle.split("::")[-1].strip()] = val.strip()
    return res


def fiches(m):
    """Bilan à afficher à partir des mesures m (voir mesures()) : [{id, nom, etat, ok, conseil, action}].
    ok : True (déjà au mieux), False (à corriger), None (à savoir, ou impossible à lire)."""
    res = []

    def fiche(id, nom, etat, ok, conseil, action=None):
        res.append({"id": id, "nom": nom, "etat": etat, "ok": ok, "conseil": conseil, "action": action})

    mini = m["plan_min"]
    fiche("alim", "Mode d'alimentation", m["plan"], None if mini is None else mini >= 100,
          "En « Performances élevées », le processeur reste à pleine vitesse au lieu de ralentir entre deux images.",
          "Passer en Performances élevées" if mini is not None and mini < 100 and m["perf_existe"] else None)
    fiche("modejeu", "Mode Jeu de Windows", "Activé" if m["mode_jeu"] else "Désactivé", m["mode_jeu"],
          "Windows donne la priorité au jeu et repousse ses propres tâches pendant la partie.",
          None if m["mode_jeu"] else "Activer")

    v = m["valorant"]
    if not v:
        fiche("valorant", "Réglages de Valorant", "introuvables", None, "Lance Valorant une fois sur ce PC.")
    else:
        r = v.get("NvidiaReflexLowLatencySetting")
        fiche("reflex", "NVIDIA Reflex", {"0": "Désactivé", "1": "Activé", "2": "Activé + Boost"}.get(r, "inconnu"),
              None if r is None else r == "2",
              "Dans Valorant : Paramètres › Vidéo › Qualité graphique › NVIDIA Reflex Low Latency › Activé + Boost.")
        lus = [(nom, v[cle] == leger) for cle, nom, leger in GRAPHISMES if cle in v]
        lourds = [nom for nom, leger in lus if not leger]
        fiche("graphismes", "Qualité graphique",
              "plus haut que le minimum : " + ", ".join(lourds) if lourds else "tout au minimum" if lus else "inconnue",
              None if not lus else not lourds,
              "Moins de détails, moins de calcul par image : tout sur Basse, ombres et distorsion désactivées.")
        mode, vsync = v.get("PreferredFullscreenMode"), v.get("bUseVSync") == "True"
        fiche("affichage", "Mode d'affichage",
              {"0": "Plein écran", "1": "Fenêtré sans bordure", "2": "Fenêtré"}.get(mode, "inconnu")
              + (", VSync activée" if vsync else ""), None if mode is None else mode == "0" and not vsync,
              "En plein écran et sans VSync, chaque image part dès qu'elle est prête.")
        fps = v.get("MaxFramerateAlways") if v.get("LimitFramerateAlways") == "True" else None
        fiche("fps", "Limite d'images par seconde", f"{float(fps):.0f} FPS" if fps else "sans limite", None,
              "Plus d'images par seconde peut encore baisser un peu la latence. À essayer : une limite plus haute ou "
              "aucune, en regardant la Game Latency (CPU) en jeu.")

    cpu = m["cpu"]
    lourds = [(exe, pct) for exe, pct in sorted((cpu or {}).items(), key=lambda x: -x[1])
              if pct >= 1 and exe.lower() not in SYSTEME][:5]
    fiche("fond", "Applis en fond",
          "mesure en cours…" if cpu is None else ", ".join(f"{exe.removesuffix('.exe')} {pct:.0f} %" for exe, pct in lourds)
          or "rien de gourmand", None if cpu is None else not lourds,
          "Ferme ces programmes pendant que tu joues : ils prennent du temps au processeur (en % du processeur entier).")
    fiche("ram", "Vitesse de la RAM", m["ram"] or "inconnue", None,
          "Si ta RAM est vendue plus rapide (sur la boîte ou la fiche de son modèle), active son profil XMP (Intel) ou "
          "EXPO (AMD) dans le BIOS : un vrai gain sur la latence CPU. À faire toi-même, au démarrage du PC.")
    return res


# --- Windows -------------------------------------------------------------------------------------------------------

class GUID(ctypes.Structure):
    _fields_ = [("octets", ctypes.c_ubyte * 16)]


def _guid(texte):
    return GUID((ctypes.c_ubyte * 16)(*uuid.UUID(texte).bytes_le))


def plan_actif():
    p = ctypes.POINTER(GUID)()
    if powrprof.PowerGetActiveScheme(None, ctypes.byref(p)):
        return ""
    texte = str(uuid.UUID(bytes_le=bytes(p.contents.octets)))
    kernel32.LocalFree(p)
    return texte


def nom_plan(plan):
    """Nom du mode d'alimentation tel que Windows l'affiche, None s'il n'existe pas sur ce PC."""
    g, n = _guid(plan), w.DWORD(0)
    if powrprof.PowerReadFriendlyName(None, ctypes.byref(g), None, None, None, ctypes.byref(n)) or not n.value:
        return None
    tampon = ctypes.create_string_buffer(n.value)
    powrprof.PowerReadFriendlyName(None, ctypes.byref(g), None, None, tampon, ctypes.byref(n))
    return tampon.raw.decode("utf-16-le").rstrip("\0")


def vitesse_mini(plan):
    """« État minimal du processeur » du mode, sur secteur, en % : 100 = jamais ralenti. None si illisible."""
    v = w.DWORD()
    ok = powrprof.PowerReadACValueIndex(None, ctypes.byref(_guid(plan)), ctypes.byref(_guid(PROC)),
                                        ctypes.byref(_guid(PROC_MIN)), ctypes.byref(v)) == 0
    return v.value if ok else None


def mode_jeu():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar") as k:
            return winreg.QueryValueEx(k, "AutoGameModeEnabled")[0] != 0
    except OSError:
        return True  # valeur absente : activé, comme Windows par défaut


def reglages_valorant():
    """Réglages du compte Valorant joué en dernier (RiotUserSettings.ini le plus récent, plus son GameUserSettings.ini) :
    {"NvidiaReflexLowLatencySetting": "2", ...}, ou {} si Valorant n'a jamais été lancé ici."""
    riot = max(CONFIG.glob("*/Windows/RiotUserSettings.ini"), key=lambda f: f.stat().st_mtime, default=None)
    if riot is None:
        return {}
    res = {}
    for f in (riot.parent.parent / "WindowsClient" / "GameUserSettings.ini", riot):
        try:
            res.update(lire_ini(f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass
    return res


@lru_cache(maxsize=1)
def ram():
    """« DDR5 à 4800 MT/s (référence) », lu une seule fois : PowerShell met une seconde à répondre."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "$m = Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1; "
                            "'{0};{1};{2}' -f $m.SMBIOSMemoryType, $m.ConfiguredClockSpeed, $m.PartNumber.Trim()"],
                           capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        genre, vitesse, ref = r.stdout.strip().split(";")
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    genre = {"26": "DDR4", "34": "DDR5"}.get(genre, "RAM")
    return f"{genre} à {vitesse} MT/s" + (f" ({ref})" if ref else "")


def _temps_cpu(pid):
    """Temps de processeur consommé par un processus depuis son lancement (en 100 ns), None si illisible."""
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    t = [ctypes.c_ulonglong() for _ in range(4)]
    ok = kernel32.GetProcessTimes(h, *map(ctypes.byref, t))
    kernel32.CloseHandle(h)
    return t[2].value + t[3].value if ok else None


class Charge:
    """Part du processeur prise par chaque programme entre deux appels de mesure()."""

    def __init__(self):
        self._avant, self._t = {}, None

    def mesure(self):
        """{programme: % du processeur entier}, ou None au premier appel."""
        t, maintenant = time.perf_counter(), {}
        for pid, exe in c.processus():
            v = _temps_cpu(pid) if pid != os.getpid() else None
            if v is not None:
                maintenant[pid] = (exe, v)
        res = None
        if self._t is not None:
            res = {}
            for pid, (exe, v) in maintenant.items():
                if self._avant.get(pid, ("",))[0] == exe:
                    res[exe] = res.get(exe, 0) + (v - self._avant[pid][1]) / 1e5 / (t - self._t) / os.cpu_count()
        self._avant, self._t = maintenant, t
        return res


def mesures(charge):
    plan = plan_actif()
    return {"plan": nom_plan(plan) or "inconnu", "plan_min": vitesse_mini(plan), "perf_existe": nom_plan(PERF) is not None,
            "mode_jeu": mode_jeu(), "valorant": reglages_valorant(),
            "cpu": charge.mesure(), "ram": ram()}


def corriger(id):
    """Applique la correction d'une fiche (celles qui ont une action)."""
    if id == "alim":
        powrprof.PowerSetActiveScheme(None, ctypes.byref(_guid(PERF)))
    elif id == "modejeu":
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar") as k:
            winreg.SetValueEx(k, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1)
