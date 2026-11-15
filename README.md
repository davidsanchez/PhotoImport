# PhotoImport

Import de photos depuis une carte SD et tri rapide (macOS, Windows, Linux).

- Copie les photos dans un dossier parent, dans des sous-dossiers `AAAA-MM-JJ`
  (date de prise de vue lue dans les métadonnées).
- Visionneuse pour marquer chaque photo : `X` rejet, `N` neutre, `P` gardé.
- Zoom : boutons `+` / `−`, touches `+` / `-`, molette ; `0` ou double-clic
  dans la photo pour l'ajuster à la fenêtre.
- Bande de vignettes en bas : toutes les photos du dossier avec leur statut,
  clic pour naviguer.
- Panneau de droite : vue d'ensemble de la photo avec le cadre de la zone
  affichée (clic ou glissé pour s'y déplacer) et histogramme rouge / vert / bleu.
- Bouton « Supprimer les photos rejetées » (avec confirmation).

## Installation

Les installateurs sont dans les
[releases](https://github.com/davidsanchez/PhotoImport/releases) :
`.dmg` pour macOS (Apple Silicon ou Intel), `-setup.exe` pour Windows,
`.deb` ou `.tar.gz` pour Linux. Ils sont construits automatiquement à chaque
tag (`git tag v1.0.0 && git push origin v1.0.0`).

Les applications ne sont pas signées : au premier lancement, macOS et Windows
affichent un avertissement qu'il faut passer manuellement.

## Lancer depuis les sources

```
pip3 install -r requirements.txt
python3 import_photos.py
```

Seul Pillow est indispensable ; les autres paquets ajoutent les RAW, le HEIC
et la suppression vers la Corbeille.
