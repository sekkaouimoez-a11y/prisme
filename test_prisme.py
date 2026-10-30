"""Calculs purs : rien ne change à l'écran. Lancer : uv run python -m unittest"""
import unittest

import couleurs as c

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


if __name__ == "__main__":
    unittest.main()
