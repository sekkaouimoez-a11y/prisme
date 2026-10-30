# Prisme

Change les couleurs de l'écran par profil : luminosité, contraste, exposition, gamma, saturation (vibrance NVIDIA),
rotation de teinte, température, teinte vert / magenta, et rouge / vert / bleu un par un.

Chaque profil choisit :
- **quand** il s'applique : toujours, ou seulement quand une appli (ou une seule de ses fenêtres) est au premier plan ;
- **sur quel écran** : tous, celui où est la fenêtre, ou un écran précis.

Dès que l'appli passe derrière (Alt+Tab), l'écran retrouve ses couleurs d'origine. Pendant qu'on règle un profil dans
Prisme, il est montré en aperçu.

## Installer sur un PC
1. Télécharger le ZIP : bouton vert **Code** → **Download ZIP**, puis l'extraire (clic droit → Extraire tout).
2. Double-clic sur `Lancer.bat`. Si Windows affiche un avertissement : **Informations complémentaires** → **Exécuter
   quand même**.

Le premier lancement demande Internet et prend environ une minute : il installe [uv](https://docs.astral.sh/uv/), qui
installe lui-même Python et pywebview. Les fois suivantes, Prisme s'ouvre directement.

## Lancer
Double-clic sur `Lancer.bat` (ou `uv run prisme.py`). À la fermeture, les couleurs d'origine reviennent.

## Latence CPU
Page **Outils › Latence CPU** : bilan de ce qui fait monter la « Game Latency (CPU) » de Valorant (le temps que met le PC
à préparer chaque image), avec un voyant par point : mode d'alimentation, Mode Jeu de Windows, NVIDIA Reflex, qualité
graphique, plein écran et VSync, limite de FPS, applis qui prennent du processeur en fond, vitesse de la RAM.
- Corrigés en un clic : passage en « Performances élevées », activation du Mode Jeu.
- Lus dans les fichiers de réglages de Valorant, à changer dans le jeu : Reflex, graphismes, affichage, FPS.
- À faire soi-même : fermer les applis gourmandes, activer le profil XMP / EXPO de la RAM dans le BIOS.
Rien n'est lu ni écrit dans la mémoire du jeu. La priorité du jeu n'est pas touchée : Valorant se met lui-même en Haute
quand on joue.

## Vidéos et captures
Les couleurs de Prisme sont posées à la sortie de la carte graphique : les enregistrements (NVIDIA, OBS, Xbox Game Bar),
les captures et les partages d'écran ne les voient pas. Page **Outils › Vidéos et captures** : Prisme surveille des
dossiers (par défaut celui des clips NVIDIA de Valorant) et recolore chaque **nouveau** clip ou capture avec le rendu du
profil choisi (une LUT 3D calculée depuis ses réglages), puis range la copie, suffixée « (Prisme) », dans `~\Prisme`.
- Les originaux ne sont jamais modifiés.
- Rien ne tourne pendant que le jeu est lancé (pour ne pas ajouter de latence) : les fichiers attendent sa fermeture.
- Encodage par la puce vidéo NVIDIA (NVENC), sinon par le processeur. ffmpeg est fourni par le paquet `imageio-ffmpeg`.
- Le partage d'écran Discord en direct ne peut pas être recoloré sans coût en latence : pour ça, les filtres de jeu NVIDIA
  (Alt+F3) agissent dans l'image elle-même.

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
