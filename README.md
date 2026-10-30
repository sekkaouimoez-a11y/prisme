# Prisme

Change les couleurs de l'écran par profil : luminosité, contraste, exposition, gamma, saturation (vibrance NVIDIA),
rotation de teinte, température, teinte vert / magenta, et rouge / vert / bleu un par un.

Chaque profil choisit :
- **quand** il s'applique : toujours, ou seulement quand une appli (ou une seule de ses fenêtres) est au premier plan ;
- **sur quel écran** : tous, celui où est la fenêtre, ou un écran précis.

Dès que l'appli passe derrière (Alt+Tab), l'écran retrouve ses couleurs d'origine. Pendant qu'on règle un profil dans
Prisme, il est montré en aperçu.

## Lancer
Double-clic sur `Lancer.bat` (ou `uv run prisme.py`). À la fermeture, les couleurs d'origine reviennent.

## Comment ça marche
- Rampe gamma de Windows (`SetDeviceGammaRamp`), par écran : luminosité, contraste, exposition, gamma, température,
  teinte, canaux. Posée par-dessus l'étalonnage existant de l'écran.
- Pilote NVIDIA (NVAPI, comme VibranceGUI) : vibrance numérique (0 à 100 %, 50 = normal, la même échelle que le
  panneau NVIDIA) et rotation de teinte. Sans carte NVIDIA, ces deux réglages sont grisés.
- Les deux agissent à la sortie de la carte graphique : pas d'image ajoutée, donc ni latence ni FPS en moins, et ça
  marche en plein écran.
- Si un anti-triche (Vanguard de Valorant) bloque l'accès au processus, le nom du programme est lu dans la liste des
  processus à la place.

## Fichiers
- `reglages.json` : les profils.
- `origine.json` : couleurs d'avant Prisme, effacé à la fermeture. S'il reste (plantage), Prisme les rend au lancement
  suivant.

## Tests
`uv run python -m unittest` (calculs seuls : rien ne change à l'écran).
