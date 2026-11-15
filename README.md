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
- Interface en français ou en anglais (bouton « English / Français »).

## Installation

Les installateurs sont dans les
[releases](https://github.com/davidsanchez/PhotoImport/releases) :
`.dmg` pour macOS (Apple Silicon ou Intel), `-setup.exe` pour Windows,
`.deb` ou `.tar.gz` pour Linux. Ils sont construits automatiquement à chaque
tag (`git tag v1.0.0 && git push origin v1.0.0`).

### macOS

1. Téléchargez le `.dmg` qui correspond à votre Mac : `macos-arm64` pour les
   Mac Apple Silicon (M1 et suivants), `macos-intel` pour les Mac Intel.
2. Ouvrez le `.dmg` et glissez **PhotoImport** dans **Applications**.
3. Lancez PhotoImport. L'application n'est pas signée auprès d'Apple : macOS
   refuse de l'ouvrir la première fois et affiche un avertissement. Cliquez
   sur **Terminé** (pas sur « Placer dans la corbeille »).
4. Ouvrez **Réglages Système > Confidentialité et sécurité**, descendez
   jusqu'à la section **Sécurité** : un message indique que PhotoImport a été
   bloqué. Cliquez sur **Ouvrir quand même**, puis confirmez avec votre mot de
   passe ou Touch ID.
5. Les lancements suivants se font normalement, par double-clic.

Le bouton « Ouvrir quand même » n'apparaît qu'après une première tentative
d'ouverture, et pendant environ une heure. Sur macOS 14 et antérieurs, un clic
droit sur l'application puis **Ouvrir** suffit.

Si macOS affiche « PhotoImport est endommagé et ne peut pas être ouvert »,
retirez la marque de quarantaine dans le Terminal :

```
xattr -dr com.apple.quarantine /Applications/PhotoImport.app
```

Au premier import, macOS demande aussi l'autorisation d'accéder au volume
amovible (la carte SD) et au dossier de destination : acceptez.

### Windows

Lancez le `-setup.exe`. L'installateur n'est pas signé : si SmartScreen
affiche « Windows a protégé votre ordinateur », cliquez sur **Informations
complémentaires**, puis sur **Exécuter quand même**.

### Linux

Debian / Ubuntu : `sudo apt install ./PhotoImport-<version>-linux-amd64.deb`,
puis lancez `photoimport`. Autres distributions : décompressez le `.tar.gz`
et lancez le fichier `PhotoImport`.

## Lancer depuis les sources

```
pip3 install -r requirements.txt
python3 import_photos.py
```

Seul Pillow est indispensable ; les autres paquets ajoutent les RAW, le HEIC
et la suppression vers la Corbeille.
