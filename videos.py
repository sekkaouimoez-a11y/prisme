"""Vidéos et captures recolorées. Les couleurs de Prisme sont posées à la sortie de la carte graphique, après l'endroit où
NVIDIA, OBS, Discord ou la touche Impr. écran prennent l'image : elles ne sont donc pas dans les enregistrements. Prisme
repasse les nouveaux fichiers des dossiers surveillés dans ffmpeg avec la LUT du profil (même rendu qu'à l'écran) et
range la copie à part ; l'original n'est jamais touché. Rien ne tourne pendant que le jeu est lancé (latence)."""
import subprocess
import tempfile
import time
import winreg
from pathlib import Path

import imageio_ffmpeg

import couleurs as c

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()  # fourni avec le paquet : marche aussi sur un PC sans ffmpeg
VIDEOS, IMAGES = (".mp4", ".mkv", ".mov"), (".png", ".jpg", ".jpeg")
SUFFIXE = " (Prisme)"
LUT = Path(tempfile.gettempdir()) / "prisme.cube"
# Clips NVIDIA, OBS, Xbox Game Bar : BT.709, plage TV. Conversion vers RGB et retour écrite en toutes lettres, sinon ffmpeg
# peut supposer BT.601 et décaler les couleurs.
FILTRE = ("scale=in_color_matrix=bt709:in_range=tv,format=gbrp,lut3d=prisme.cube,"
          "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
ENCODEURS = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"],  # puce vidéo NVIDIA
             ["-c:v", "libx264", "-preset", "fast", "-crf", "18"])  # sinon le processeur
DISCRET = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS


def dossier_nvidia():
    """Dossier où l'appli NVIDIA range clips et captures (un sous-dossier par jeu), None sans elle."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS") as k:
            return Path(winreg.QueryValueEx(k, "DefaultPathW")[0].decode("utf-16-le").rstrip("\0"))
    except (OSError, UnicodeDecodeError):
        return None


def reglages_par_defaut():
    n = dossier_nvidia()
    return {"actif": False, "profil": None, "dossiers": [str(n / "Valorant")] if n else [],
            "sortie": str(Path.home() / "Prisme"), "depuis": 0}


def copie(src, sortie):
    return Path(sortie) / f"{src.stem}{SUFFIXE}{src.suffix}"


def nouveaux(dossiers, depuis, sortie):
    """Fichiers des dossiers enregistrés après « depuis », finis d'écrire (rien depuis 5 s) et pas encore recolorés, le
    plus ancien d'abord."""
    res, avant = [], time.time() - 5
    for d in dossiers:
        for f in Path(d).rglob("*"):
            if f.suffix.lower() not in VIDEOS + IMAGES or f.stem.endswith(SUFFIXE):
                continue
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if depuis <= m < avant and not copie(f, sortie).exists():
                res.append((m, f))
    return [f for _, f in sorted(res)]


def lance(programmes):
    """Le premier de ces programmes (noms en minuscules) qui tourne, "" sinon."""
    return next((exe for _, exe in c.processus() if exe.lower() in programmes), "")


def recolorer(src, sortie, r, interrompre):
    """Copie de src recolorée avec les réglages r, rangée dans sortie. Vrai si faite, faux si ffmpeg échoue, None si
    interrompre() a demandé l'arrêt en route (le fichier sera repris plus tard)."""
    dst = copie(src, sortie)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".en-cours" + dst.suffix)  # jamais de copie à moitié écrite sous le vrai nom
    LUT.write_text(c.cube(r))
    image = src.suffix.lower() in IMAGES
    for enc in [None] if image else ENCODEURS:
        cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(src)]
        if image:
            cmd += ["-vf", "lut3d=prisme.cube", "-frames:v", "1", "-update", "1"]
            cmd += [] if src.suffix.lower() == ".png" else ["-q:v", "2"]
        else:
            cmd += ["-map", "0:v:0", "-map", "0:a?", "-vf", FILTRE, *enc, "-colorspace", "bt709", "-color_primaries",
                    "bt709", "-color_trc", "bt709", "-color_range", "tv", "-c:a", "copy", "-movflags", "+faststart"]
        # lut3d=prisme.cube lu dans le dossier de travail : pas de chemin Windows à échapper dans le filtre.
        p = subprocess.Popen(cmd + [str(tmp)], cwd=LUT.parent, creationflags=DISCRET,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while p.poll() is None:
            if interrompre():
                p.kill()
                p.wait()
                tmp.unlink(missing_ok=True)
                return None
            time.sleep(0.5)
        if p.returncode == 0:
            tmp.replace(dst)
            return True
    tmp.unlink(missing_ok=True)
    return False
