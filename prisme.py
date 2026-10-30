"""Prisme : couleurs de l'écran par profil (luminosité, contraste, gamma, saturation NVIDIA…), posées quand l'appli ou
la fenêtre choisie est au premier plan, sur l'écran choisi. Les couleurs d'origine reviennent dès qu'elle passe derrière."""
import json
import os
import threading
from pathlib import Path

import webview

import couleurs as c

ICI = Path(__file__).parent
REGLAGES = ICI / "reglages.json"
# Couleurs d'avant Prisme. Effacé à la fermeture ; s'il reste (Prisme a planté), ce sont elles qu'on rend au lancement suivant.
ORIGINE = ICI / "origine.json"
DEPART = {"actif": True, "profils": [{
    "id": 1, "nom": "Valorant", "ecran": "", "r": {**c.NEUTRE, **c.PREREGLAGES["Gaming"]},
    "cibles": [{"exe": "VALORANT-Win64-Shipping.exe", "titre": "VALORANT", "seule": False}],
}]}


class Ecrans:
    """Ce qui est posé sur chaque écran, et les couleurs d'origine à rendre."""

    def __init__(self):
        self.nv = c.Nvidia()
        self.liste = c.moniteurs()
        try:
            self.origine = json.loads(ORIGINE.read_text())
        except (OSError, ValueError):
            self.origine = {}
        for e in self.liste:
            self.noter(e["id"])
        self.pose = {}  # écran -> copie des réglages posés, None = couleurs d'origine
        self.limite = set()  # écrans où Windows n'a accepté qu'une partie de l'effet

    def noter(self, e):
        """Retient les couleurs d'origine d'un écran pas encore vu."""
        if e not in self.origine:
            v = self.nv.vibrance(e)
            self.origine[e] = {"rampe": c.lire_rampe(e), "vibrance": v[0] if v else None, "teinte": self.nv.teinte(e)}
            ORIGINE.write_text(json.dumps(self.origine))

    def appliquer(self, voulu, forcer=False):
        """voulu : {écran: réglages, ou None pour l'origine}. Ne repose que ce qui a changé ; forcer : repose aussi le reste
        (Windows remet la rampe à zéro après une veille ou un changement de mode d'affichage)."""
        for e, r in voulu.items():
            o = self.origine.get(e)
            if o is None or self.pose.get(e, "?") == r and not (forcer and r):
                continue
            if r is None:
                c.poser_rampe(e, o["rampe"])
                self.limite.discard(e)
            else:
                # Windows refuse une rampe trop loin de la normale : on essaie l'effet de moins en moins fort.
                force = next((f for f in (1, 0.75, 0.5, 0.25) if c.poser_rampe(e, c.rampe(r, o["rampe"], f))), 0)
                (self.limite.discard if force == 1 else self.limite.add)(e)
            if o["vibrance"] is not None:
                v = self.nv.vibrance(e)
                if v is None:
                    self.nv.relister()  # poignée périmée : on retentera au prochain passage forcé
                elif r is None:
                    self.nv.poser(e, o["vibrance"], o["teinte"] or 0)
                else:
                    self.nv.poser(e, c.niveau(r["saturation"], *v[1:]), r["rotation"])
            self.pose[e] = dict(r) if r else None

    def restaurer(self):
        self.pose = {}
        self.appliquer(dict.fromkeys(self.origine))
        ORIGINE.unlink(missing_ok=True)


class Api:
    """Ce que l'interface (ui/index.html) appelle ; elle relit etat() 4 fois par seconde."""

    def __init__(self, ecrans):
        self._e = ecrans
        self._verrou = threading.RLock()  # pywebview appelle l'Api depuis plusieurs fils à la fois
        try:
            self._d = json.loads(REGLAGES.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._d = json.loads(json.dumps(DEPART))  # copie profonde
        for p in self._d["profils"]:
            p["r"] = {**c.NEUTRE, **p["r"]}
        self._choisi = self._d["profils"][0]["id"] if self._d["profils"] else None
        self._version = 0  # change quand Python remplace des réglages : l'interface redessine ses curseurs
        self._montres, self._apercu = {}, False
        self._stop = threading.Event()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def etat(self):
        with self._verrou:
            return {"actif": self._d["actif"], "profils": self._d["profils"], "choisi": self._choisi,
                    "version": self._version, "ecrans": self._e.liste, "nvidia": list(self._e.nv.ecrans),
                    "montres": self._montres, "apercu": self._apercu, "limite": sorted(self._e.limite),
                    "neutre": c.NEUTRE, "prereglages": list(c.PREREGLAGES)}

    def basculer(self):
        with self._verrou:
            self._d["actif"] = not self._d["actif"]
            self._sauver()

    def choisir(self, id):
        with self._verrou:
            if self._profil(id):
                self._choisi = id

    def ajouter(self):
        with self._verrou:
            ids = [p["id"] for p in self._d["profils"]]
            id = max(ids, default=0) + 1
            self._d["profils"].append({"id": id, "nom": f"Profil {len(ids) + 1}", "ecran": "", "cibles": [],
                                       "r": dict(c.NEUTRE)})
            self._choisi = id
            self._version += 1
            self._sauver()

    def supprimer(self, id):
        with self._verrou:
            self._d["profils"] = [p for p in self._d["profils"] if p["id"] != id]
            if self._choisi == id:
                self._choisi = self._d["profils"][0]["id"] if self._d["profils"] else None
            self._version += 1
            self._sauver()

    def prereglage(self, id, nom):
        with self._verrou:
            p = self._profil(id)
            if p and nom in c.PREREGLAGES:
                p["r"] = {**c.NEUTRE, **c.PREREGLAGES[nom]}
                self._version += 1
                self._sauver()

    def modifier(self, id, champ, valeur):
        """Un réglage (luminosite…), ou "nom", "ecran" ("" ou un écran branché), "cibles" ([{exe, titre, seule}])."""
        with self._verrou:
            p = self._profil(id)
            if p is None:
                return
            if champ in c.BORNES:
                bas, haut = c.BORNES[champ]
                p["r"][champ] = min(max(float(valeur), bas), haut)
            elif champ == "nom":
                p["nom"] = str(valeur).strip()[:40] or p["nom"]
            elif champ == "ecran":
                p["ecran"] = valeur if any(e["id"] == valeur for e in self._e.liste) else ""
            elif champ == "cibles":
                p["cibles"] = [{"exe": str(x["exe"]), "titre": str(x["titre"]), "seule": bool(x["seule"])} for x in valeur]
            self._sauver()

    def fenetres_ouvertes(self):
        return c.fenetres_ouvertes()

    def _profil(self, id):
        return next((p for p in self._d["profils"] if p["id"] == id), None)

    def _sauver(self):
        REGLAGES.write_text(json.dumps(self._d, ensure_ascii=False, indent=1), encoding="utf-8")

    def _boucle(self):
        """10 fois par seconde : quelle fenêtre est devant, donc quel profil sur quel écran."""
        n = 0
        while not self._stop.wait(0.1):
            n += 1
            if n % 50 == 0:  # toutes les 5 s : écrans branchés ou débranchés
                liste = c.moniteurs()
                for e in liste:
                    self._e.noter(e["id"])
                self._e.liste = liste
            d = c.devant()
            if d is None:  # bascule Alt+Tab en cours : on garde ce qui est posé
                continue
            hwnd, exe, titre, ecran = d
            with self._verrou:
                ids = [e["id"] for e in self._e.liste]
                # Pendant qu'on règle un profil dans Prisme, on le montre, même s'il est fait pour une autre appli.
                apercu = self._profil(self._choisi) if c.pid_de(hwnd) == os.getpid() else None
                voulu = c.plan(self._d["profils"], ids, (exe, titre, ecran), apercu) if self._d["actif"] \
                    else dict.fromkeys(ids)
                self._apercu = bool(apercu and self._d["actif"])
                self._montres = {e: p["nom"] for e, p in voulu.items() if p}
                self._e.appliquer({e: p and p["r"] for e, p in voulu.items()}, forcer=n % 20 == 0)

    def _fermer(self):
        self._stop.set()
        self._fil.join(1)
        self._e.restaurer()


def main():
    api = Api(Ecrans())
    try:
        webview.create_window("Prisme", str(ICI / "ui" / "index.html"), js_api=api, width=1100, height=740,
                              min_size=(900, 580), background_color="#12121f")
        webview.start()
    finally:
        api._fermer()


if __name__ == "__main__":
    main()
