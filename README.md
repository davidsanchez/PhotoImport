# PhotoImport

Import de photos depuis une carte SD (macOS) et tri rapide.

- Copie les photos dans un dossier parent, dans des sous-dossiers `AAAA-MM-JJ`
  (date de prise de vue lue dans les métadonnées).
- Visionneuse pour marquer chaque photo : `X` rejet, `N` neutre, `P` gardé.
- Zoom : boutons `+` / `−`, touches `+` / `-`, molette ; `0` pour revenir.
- Bande de vignettes en bas : toutes les photos du dossier avec leur statut,
  clic pour naviguer.
- Bouton « Supprimer les photos rejetées » (avec confirmation).

## Installation

```
pip3 install Pillow
python3 import_photos.py
```

Optionnel : `pip3 install rawpy exifread pillow-heif` (RAW et HEIC),
`pip3 install send2trash` (suppression vers la Corbeille).
