"""Calculs purs : rien ne change à l'écran. Lancer : uv run python -m unittest"""
import os
import tempfile
import time
import unittest
from pathlib import Path

import couleurs as c
import latence as lat
import videos as vid

IDENTITE = [i * 257 for i in range(256)] * 3
EXTREMES = [{**c.NEUTRE, **{k: v for k in c.NEUTRE if k not in ("saturation", "rotation")}} for v in (-1.0, 1.0)]


class Rampe(unittest.TestCase):
    def test_neutre_ne_change_rien(self):
        self.assertEqual(c.rampe(c.NEUTRE, IDENTITE), IDENTITE)

    def test_croissante_et_dans_les_bornes(self):
        # Windows refuse une rampe qui redescend ; et une valeur hors de 0..65535 ne tient pas dans un WORD.
        for r in [{**c.NEUTRE, **p} for p in c.PREREGLAGES.values()] + EXTREMES:
            v = c.rampe(r, IDENTITE)
            for k in range(3):
                canal = v[k * 256:(k + 1) * 256]
                self.assertEqual(canal, sorted(canal), r)
                self.assertTrue(0 <= min(canal) and max(canal) <= 65535, r)

    def test_force_zero_rend_l_origine(self):
        origine = [min(65535, i * 300) for i in range(256)] * 3  # écran étalonné
        self.assertEqual(c.rampe({**c.NEUTRE, **c.PREREGLAGES["Gaming"]}, origine, 0), origine)

    def test_effets_dans_le_bon_sens(self):
        milieu = lambda r, canal=1: c.courbe({**c.NEUTRE, **r}, canal, 0.5)
        self.assertGreater(milieu({"luminosite": 0.5}), 0.5)
        self.assertGreater(milieu({"gamma": 0.5}), 0.5)
        self.assertGreater(milieu({"exposition": 0.5}), 0.5)
        self.assertGreater(c.courbe({**c.NEUTRE, "contraste": 0.5}, 0, 0.8), 0.8)
        self.assertGreater(milieu({"temperature": 0.5}, 0), milieu({"temperature": 0.5}, 2))  # chaud : plus de rouge


class Cube(unittest.TestCase):
    @staticmethod
    def points(r, n=5):
        lignes = c.cube(r, n).splitlines()
        assert lignes[0] == f"LUT_3D_SIZE {n}" and len(lignes) == n ** 3 + 1
        return [tuple(map(float, l.split())) for l in lignes[1:]]

    def test_neutre_ne_change_rien(self):
        grille = [(rr / 4, g / 4, b / 4) for b in range(5) for g in range(5) for rr in range(5)]  # rouge le plus rapide
        for p, q in zip(self.points(c.NEUTRE), grille):
            self.assertAlmostEqual(max(abs(x - y) for x, y in zip(p, q)), 0, places=4)

    def test_saturation(self):
        rouge_terne = 2 * 25 + 1 * 5 + 3  # point (0,75 ; 0,25 ; 0,5) de la grille 5×5×5
        ecart = lambda s: (lambda p: p[0] - p[1])(self.points({**c.NEUTRE, "saturation": s})[rouge_terne])
        self.assertGreater(ecart(80), ecart(50))
        self.assertAlmostEqual(ecart(0), 0, places=4)  # 0 % : gris

    def test_dans_les_bornes(self):
        for r in [{**c.NEUTRE, **p} for p in c.PREREGLAGES.values()] + EXTREMES:
            self.assertTrue(all(0 <= x <= 1 for p in self.points(r) for x in p), r)


class Niveau(unittest.TestCase):
    def test_pourcent_vers_pilote(self):
        self.assertEqual(c.niveau(50, 0, 100, 50), 50)
        self.assertEqual(c.niveau(80, 0, 100, 50), 80)
        self.assertEqual(c.niveau(100, 0, 63, 0), 63)  # ancienne échelle : 0 = normal
        self.assertEqual(c.niveau(0, -63, 63, 0), -63)


def profil(nom, cibles=(), ecran=""):
    return {"nom": nom, "ecran": ecran, "r": c.NEUTRE, "cibles": [
        {"exe": e, "titre": t, "seule": s} for e, t, s in cibles]}


class Plan(unittest.TestCase):
    ECRANS = ["\\\\.\\DISPLAY1", "\\\\.\\DISPLAY2"]
    D1, D2 = ECRANS

    def setUp(self):
        self.toujours = profil("Bureau")
        self.valo = profil("Valorant", [("VALORANT-Win64-Shipping.exe", "VALORANT", False)])
        self.onglet = profil("Onglet", [("chrome.exe", "YouTube", True)], ecran=self.D2)
        self.profils = [self.toujours, self.valo, self.onglet]

    def test_rien_devant(self):
        self.assertEqual(c.plan([self.valo], self.ECRANS, ("explorer.exe", "", self.D1)), {self.D1: None, self.D2: None})

    def test_appli_sur_l_ecran_de_sa_fenetre(self):
        v = c.plan(self.profils, self.ECRANS, ("VALORANT-Win64-Shipping.exe", "VALORANT", self.D2))
        self.assertEqual(v, {self.D1: self.toujours, self.D2: self.valo})

    def test_fenetre_seule_par_titre(self):
        self.assertIs(c.plan(self.profils, self.ECRANS, ("chrome.exe", "YouTube", self.D1))[self.D2], self.onglet)
        self.assertIs(c.plan(self.profils, self.ECRANS, ("chrome.exe", "Gmail", self.D1))[self.D2], self.toujours)

    def test_apercu_prend_la_place(self):
        v = c.plan(self.profils, self.ECRANS, ("python.exe", "Prisme", self.D1), apercu=self.valo)
        self.assertIs(v[self.D1], self.valo)


BON = {"plan": "Performances élevées", "plan_min": 100, "perf_existe": True, "mode_jeu": True,
       "valorant": lat.lire_ini("[Set]\nEAresIntSettingName::NvidiaReflexLowLatencySetting=2\n"
                                "EAresIntSettingName::MaterialQuality=0\nEAresBoolSettingName::ShadowsEnabled=False\n"
                                "PreferredFullscreenMode=0\nbUseVSync=False\n"),
       "cpu": {"Discord.exe": 0.4, "svchost.exe": 9.0}, "ram": "DDR5 à 4800 MT/s"}


class Latence(unittest.TestCase):
    def verdicts(self, **m):
        return {f["id"]: (f["ok"], f["action"]) for f in lat.fiches({**BON, **m})}

    def test_lire_ini(self):
        self.assertEqual(lat.lire_ini("[Sec]\nEAresFloatSettingName::MaxFramerateAlways=360\n;x=1\nbUseVSync=False"),
                         {"MaxFramerateAlways": "360", "bUseVSync": "False"})

    def test_pc_deja_regle(self):
        v = self.verdicts()
        self.assertFalse([k for k, (ok, action) in v.items() if ok is False or action], v)
        self.assertIs(v["fond"][0], True)  # svchost ne compte pas, Discord sous 1 %

    def test_a_corriger(self):
        v = self.verdicts(plan_min=5, mode_jeu=False, cpu={"RobloxStudioBeta.exe": 5.1},
                          valorant={"NvidiaReflexLowLatencySetting": "1", "ShadowsEnabled": "True", "bUseVSync": "True",
                                    "PreferredFullscreenMode": "1"})
        for k in ("alim", "modejeu", "reflex", "graphismes", "affichage", "fond"):
            self.assertIs(v[k][0], False, k)
        self.assertEqual([k for k, (_, action) in v.items() if action], ["alim", "modejeu"])

    def test_inconnu_sans_action(self):
        v = self.verdicts(plan_min=5, perf_existe=False, valorant={}, cpu=None)
        self.assertEqual(v["alim"], (False, None))  # pas de « Performances élevées » sur ce PC : rien à proposer
        self.assertEqual(v["fond"], (None, None))  # première mesure
        self.assertIn("valorant", v)
        self.assertNotIn("reflex", v)


class Videos(unittest.TestCase):
    def test_nouveaux(self):
        with tempfile.TemporaryDirectory() as d:
            d, maintenant = Path(d), time.time()
            sortie = d / "sortie"
            sortie.mkdir()

            def fichier(nom, age):
                (d / nom).write_bytes(b"x")
                os.utime(d / nom, (maintenant - age, maintenant - age))

            fichier("ancien.mp4", 3600)  # enregistré avant l'activation
            fichier("clip.mp4", 60)
            fichier("capture.png", 30)
            fichier("en cours.mp4", 1)  # encore en train de s'écrire
            fichier("notes.txt", 60)
            fichier("deja.mp4", 60)
            (sortie / f"deja{vid.SUFFIXE}.mp4").write_bytes(b"x")
            fichier(f"copie{vid.SUFFIXE}.mp4", 60)  # une copie posée dans un dossier surveillé
            self.assertEqual([f.name for f in vid.nouveaux([str(d)], maintenant - 600, sortie)],
                             ["clip.mp4", "capture.png"])


if __name__ == "__main__":
    unittest.main()
