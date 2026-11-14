#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import de photos depuis une carte SD + visionneuse de tri (macOS).

  1. Copie les photos de la carte SD vers un dossier parent choisi,
     dans des sous-dossiers AAAA-MM-JJ (date de prise de vue EXIF).
  2. Affiche les photos importées pour les classer :
        X = rejet      N = neutre      P = gardé
        <- / -> = photo précédente / suivante
     Zoom : boutons + / -, touches + / -, molette de la souris.
     Photo zoomée : cliquer-glisser pour se déplacer, 0 pour revenir.
     Bande de vignettes en bas : toutes les photos du dossier avec leur
     statut (rouge = rejet, gris = neutre, vert = gardé) ; cliquer sur une
     vignette pour l'afficher, molette pour faire défiler.

Les photos sont seulement marquées (fichier classement.json dans chaque
dossier) : aucun fichier n'est déplacé. Le bouton "Supprimer les photos
rejetées" efface les rejets après confirmation. La carte SD est seulement lue.

Installation :  pip3 install Pillow
Optionnel    :  pip3 install rawpy exifread pillow-heif   (RAW et HEIC)
                pip3 install send2trash   (suppression vers la Corbeille
                                           au lieu d'une suppression définitive)
Lancement    :  python3 import_photos.py
"""

import io
import json
import os
import queue
import shutil
import sys
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow est requis :  pip3 install Pillow")

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

try:
    import rawpy
except ImportError:
    rawpy = None

try:
    import exifread
except ImportError:
    exifread = None

try:
    import send2trash
except ImportError:
    send2trash = None


EXT_IMAGE = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif"}
EXT_RAW = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".dng",
           ".pef", ".srw"}
EXT_VIDEO = {".mov", ".mp4", ".mts", ".avi"}
EXT_TOUTES = EXT_IMAGE | EXT_RAW | EXT_VIDEO

DOSSIER_REJETS = "_rejets"
FICHIER_CLASSEMENT = "classement.json"
ZOOM_MAX = 12.0
PAS_ZOOM = 1.25
VIGNETTE = (96, 72)       # taille max des vignettes de la bande
LARGEUR_CASE = 112
HAUTEUR_BANDE = 112

REJET, NEUTRE, GARDE = "rejet", "neutre", "garde"
LIBELLES = {REJET: "REJET", NEUTRE: "NEUTRE", GARDE: "GARDÉ"}
COULEURS = {REJET: "#d9453b", NEUTRE: "#8a8a8a", GARDE: "#3fae5a"}


# --------------------------------------------------------------------------
# Date de prise de vue
# --------------------------------------------------------------------------

def _parse_date_exif(valeur):
    try:
        return datetime.strptime(str(valeur).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _date_pillow(chemin):
    try:
        with Image.open(chemin) as im:
            exif = im.getexif()
            sous_ifd = exif.get_ifd(0x8769)
            # DateTimeOriginal, DateTimeDigitized, puis DateTime
            for valeur in (sous_ifd.get(36867), sous_ifd.get(36868), exif.get(306)):
                date = _parse_date_exif(valeur)
                if date:
                    return date
    except Exception:
        pass
    return None


def _date_exifread(chemin):
    if exifread is None:
        return None
    try:
        with open(chemin, "rb") as f:
            tags = exifread.process_file(f, details=False)
        for cle in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized",
                    "Image DateTime"):
            date = _parse_date_exif(tags.get(cle))
            if date:
                return date
    except Exception:
        pass
    return None


def date_prise_de_vue(chemin):
    """Retourne (date, vient_des_metadonnees)."""
    chemin = Path(chemin)
    ext = chemin.suffix.lower()
    if ext not in EXT_VIDEO:
        date = _date_pillow(chemin) or _date_exifread(chemin)
        if date:
            return date, True
        if ext in EXT_RAW:
            # RAW illisible : on prend la date du JPEG jumeau s'il existe
            for e in (".JPG", ".jpg", ".JPEG", ".jpeg"):
                jumeau = chemin.with_suffix(e)
                if jumeau.exists():
                    date = _date_pillow(jumeau)
                    if date:
                        return date, True
    return datetime.fromtimestamp(chemin.stat().st_mtime), False


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

def detecter_cartes_sd():
    """Volumes montés dans /Volumes qui contiennent un dossier DCIM."""
    cartes = []
    volumes = Path("/Volumes")
    if volumes.is_dir():
        for vol in sorted(volumes.iterdir()):
            try:
                if (vol / "DCIM").is_dir():
                    cartes.append(vol / "DCIM")
            except OSError:
                pass
    return cartes


def lister_medias(racine):
    fichiers = []
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers[:] = [d for d in sous_dossiers
                            if not d.startswith(".") and d != DOSSIER_REJETS]
        for nom in noms:
            if nom.startswith("."):
                continue
            if Path(nom).suffix.lower() in EXT_TOUTES:
                fichiers.append(Path(dossier) / nom)
    return sorted(fichiers)


def _destination_libre(dest, taille):
    """Retourne (chemin, deja_present). Évite d'écraser un fichier différent."""
    if not dest.exists():
        return dest, False
    if dest.stat().st_size == taille:
        return dest, True
    n = 1
    while True:
        candidat = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
        if not candidat.exists():
            return candidat, False
        if candidat.stat().st_size == taille:
            return candidat, True
        n += 1


def importer(source, parent, progression=None):
    """Copie source -> parent/AAAA-MM-JJ/. Retourne un bilan (dict)."""
    fichiers = lister_medias(source)
    bilan = {"total": len(fichiers), "copies": 0, "deja_presents": 0,
             "sans_exif": 0, "erreurs": [], "dossiers": set()}
    for i, src in enumerate(fichiers, 1):
        if progression:
            progression(i, len(fichiers), src.name)
        try:
            date, exif_ok = date_prise_de_vue(src)
            if not exif_ok:
                bilan["sans_exif"] += 1
            dossier = Path(parent) / date.strftime("%Y-%m-%d")
            dossier.mkdir(parents=True, exist_ok=True)
            taille = src.stat().st_size
            dest, deja = _destination_libre(dossier / src.name, taille)
            bilan["dossiers"].add(dossier)
            if deja:
                bilan["deja_presents"] += 1
                continue
            shutil.copy2(src, dest)
            if dest.stat().st_size != taille:
                dest.unlink()
                raise OSError("copie incomplète")
            bilan["copies"] += 1
        except Exception as e:  # on continue avec les autres fichiers
            bilan["erreurs"].append(f"{src.name} : {e}")
    return bilan


# --------------------------------------------------------------------------
# Classement (un fichier classement.json par dossier de photos)
# --------------------------------------------------------------------------

def charger_classement(dossier):
    try:
        with open(Path(dossier) / FICHIER_CLASSEMENT, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if v in (REJET, GARDE)}
    except (OSError, ValueError):
        return {}


def sauver_classement(dossier, classement):
    chemin = Path(dossier) / FICHIER_CLASSEMENT
    tmp = chemin.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(classement, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, chemin)


class Photo:
    """Une prise de vue = tous les fichiers de même nom (ex. RAW + JPEG)."""

    def __init__(self, dossier, nom):
        self.dossier = dossier
        self.nom = nom
        self.fichiers = []

    def fichier_affichable(self):
        def ordre(p):
            ext = p.suffix.lower()
            return 0 if ext in EXT_IMAGE else 1 if ext in EXT_RAW else 2
        return sorted(self.fichiers, key=ordre)[0]


def supprimer_fichier(chemin):
    """Vers la Corbeille si send2trash est installé, sinon définitivement."""
    if send2trash is not None:
        send2trash.send2trash(str(chemin))
    else:
        Path(chemin).unlink()


def regrouper(fichiers):
    groupes = OrderedDict()
    for f in sorted(fichiers, key=lambda p: (str(p.parent), p.stem.lower())):
        cle = (f.parent, f.stem)
        if cle not in groupes:
            groupes[cle] = Photo(f.parent, f.stem)
        groupes[cle].fichiers.append(f)
    return list(groupes.values())


# --------------------------------------------------------------------------
# Chargement d'image pour l'affichage
# --------------------------------------------------------------------------

TAILLE_CACHE = 2600  # côté max des images gardées en mémoire


def charger_image(chemin, taille_max=TAILLE_CACHE):
    """Retourne une image PIL prête à afficher, ou None.
    taille_max=None : pleine résolution (utilisée pour le zoom)."""
    ext = chemin.suffix.lower()
    if ext in EXT_VIDEO:
        return None
    try:
        if ext in EXT_RAW and rawpy is not None:
            with rawpy.imread(str(chemin)) as raw:
                apercu = raw.extract_thumb()
            if apercu.format == rawpy.ThumbFormat.JPEG:
                im = Image.open(io.BytesIO(apercu.data))
            else:
                im = Image.fromarray(apercu.data)
        else:
            im = Image.open(chemin)
            if im.format == "JPEG" and taille_max:
                im.draft("RGB", (taille_max, taille_max))  # décodage rapide
        im = ImageOps.exif_transpose(im)
        if taille_max:
            im.thumbnail((taille_max, taille_max))
        return im.convert("RGB")
    except Exception:
        return None


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

def lancer_interface():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from PIL import ImageTk

    class Application:
        def __init__(self, racine):
            self.racine = racine
            racine.title("Import et tri de photos")
            racine.geometry("1200x800")
            racine.minsize(700, 450)

            self.photos = []
            self.index = 0
            self.classements = {}     # dossier -> {nom: statut}
            self.cache = OrderedDict()
            self.image_tk = None
            self.file_messages = queue.Queue()
            self.import_en_cours = False
            self._redessin = None
            self.zoom = 1.0            # 1.0 = image ajustée à la fenêtre
            self.centre = (0.5, 0.5)   # point de l'image au centre (0..1)
            self.taille_affichee = None
            self.pleine = (None, None)  # (chemin, image pleine résolution)
            self._glisse = None
            self.vignettes = {}        # chemin -> PhotoImage (None = pas d'aperçu)
            self.index_par_chemin = {}
            self.file_vignettes = queue.Queue()
            self.generation = 0        # change à chaque reconstruction de la bande

            barre = ttk.Frame(racine, padding=6)
            barre.pack(side="top", fill="x")
            for texte, commande in (
                    ("Importer depuis la carte SD…", self.lancer_import),
                    ("Ouvrir un dossier à trier…", self.ouvrir_dossier),
                    ("Supprimer les photos rejetées", self.supprimer_rejets)):
                ttk.Button(barre, text=texte, command=commande,
                           takefocus=0).pack(side="left", padx=(0, 6))
            ttk.Separator(barre, orient="vertical").pack(
                side="left", fill="y", padx=6)
            ttk.Button(barre, text="−", width=3, takefocus=0,
                       command=lambda: self.changer_zoom(1 / PAS_ZOOM)
                       ).pack(side="left")
            ttk.Button(barre, text="+", width=3, takefocus=0,
                       command=lambda: self.changer_zoom(PAS_ZOOM)
                       ).pack(side="left", padx=(2, 0))
            ttk.Button(barre, text="Ajuster", takefocus=0,
                       command=self.reinit_zoom_et_afficher
                       ).pack(side="left", padx=(6, 0))
            self.texte_zoom = ttk.Label(barre, text="", width=7)
            self.texte_zoom.pack(side="left", padx=6)
            self.barre_progression = ttk.Progressbar(barre, length=180)
            self.barre_progression.pack(side="right")
            self.texte_progression = ttk.Label(barre, text="")
            self.texte_progression.pack(side="right", padx=8)

            bas = tk.Frame(racine, bg="#1e1e1e")
            bas.pack(side="bottom", fill="x")
            self.etiquette_statut = tk.Label(
                bas, text="", width=9, fg="white", bg="#1e1e1e",
                font=("Helvetica", 15, "bold"), pady=6)
            self.etiquette_statut.pack(side="left", padx=(8, 10), pady=6)
            self.etiquette_info = tk.Label(
                bas, text="", fg="#dddddd", bg="#1e1e1e", anchor="w",
                font=("Helvetica", 13))
            self.etiquette_info.pack(side="left", fill="x", expand=True)
            self.etiquette_compte = tk.Label(
                bas, text="", fg="#aaaaaa", bg="#1e1e1e",
                font=("Helvetica", 12))
            self.etiquette_compte.pack(side="right", padx=10)

            # bande de vignettes (au-dessus de la barre d'état)
            cadre_bande = tk.Frame(racine, bg="#1e1e1e")
            cadre_bande.pack(side="bottom", fill="x")
            self.defilement = ttk.Scrollbar(cadre_bande, orient="horizontal")
            self.defilement.pack(side="bottom", fill="x")
            self.bande = tk.Canvas(
                cadre_bande, height=HAUTEUR_BANDE, bg="#1e1e1e",
                highlightthickness=0, xscrollincrement=40,
                xscrollcommand=self.defilement.set)
            self.bande.pack(side="top", fill="x")
            self.defilement.config(command=self.bande.xview)
            self.bande.bind("<ButtonPress-1>", self._clic_bande)
            self.bande.bind("<MouseWheel>", self._molette_bande)
            self.bande.bind("<Configure>", lambda _e: self._centrer_bande())

            self.canevas = tk.Canvas(racine, bg="#111111", highlightthickness=0)
            self.canevas.pack(side="top", fill="both", expand=True)
            self.canevas.bind("<Configure>", self._redimensionne)
            self.canevas.bind("<MouseWheel>", self._molette)
            self.canevas.bind("<Button-4>", self._molette)   # Linux
            self.canevas.bind("<Button-5>", self._molette)
            self.canevas.bind("<ButtonPress-1>", self._debut_glisse)
            self.canevas.bind("<B1-Motion>", self._glisser)

            racine.bind("<KeyPress>", self.touche)
            self.afficher()
            self._recevoir_vignettes()

        # ---------------- import ----------------

        def lancer_import(self):
            if self.import_en_cours:
                return
            cartes = detecter_cartes_sd()
            source = None
            if len(cartes) == 1:
                if messagebox.askyesno(
                        "Carte SD détectée",
                        f"Importer depuis :\n{cartes[0]} ?"):
                    source = cartes[0]
            if source is None:
                depart = str(cartes[0]) if cartes else "/Volumes"
                choix = filedialog.askdirectory(
                    title="Choisir la carte SD (ou le dossier source)",
                    initialdir=depart)
                if not choix:
                    return
                source = Path(choix)
            parent = filedialog.askdirectory(
                title="Choisir le dossier parent de destination")
            if not parent:
                return
            parent = Path(parent)
            try:
                if parent.resolve().is_relative_to(Path(source).resolve()):
                    messagebox.showerror(
                        "Destination invalide",
                        "La destination ne peut pas être sur la carte source.")
                    return
            except OSError:
                pass

            self.import_en_cours = True
            self.texte_progression.config(text="Lecture de la carte…")

            def travail():
                def progression(i, n, nom):
                    self.file_messages.put(("progression", i, n, nom))
                try:
                    bilan = importer(source, parent, progression)
                    self.file_messages.put(("fin", bilan))
                except Exception as e:
                    self.file_messages.put(("echec", str(e)))

            threading.Thread(target=travail, daemon=True).start()
            self.racine.after(100, self._suivre_import)

        def _suivre_import(self):
            try:
                while True:
                    msg = self.file_messages.get_nowait()
                    if msg[0] == "progression":
                        _, i, n, nom = msg
                        self.barre_progression.config(maximum=n, value=i)
                        self.texte_progression.config(text=f"{i} / {n}   {nom}")
                    elif msg[0] == "fin":
                        self._fin_import(msg[1])
                        return
                    else:
                        self.import_en_cours = False
                        self.texte_progression.config(text="")
                        messagebox.showerror("Import impossible", msg[1])
                        return
            except queue.Empty:
                pass
            self.racine.after(100, self._suivre_import)

        def _fin_import(self, bilan):
            self.import_en_cours = False
            self.barre_progression.config(value=0)
            self.texte_progression.config(text="")
            lignes = [f"{bilan['copies']} fichier(s) copié(s) "
                      f"sur {bilan['total']} trouvé(s).",
                      f"{bilan['deja_presents']} déjà présent(s), ignoré(s)."]
            if bilan["sans_exif"]:
                lignes.append(
                    f"{bilan['sans_exif']} sans date de prise de vue : "
                    "classé(s) selon la date du fichier.")
            if bilan["erreurs"]:
                lignes.append(f"\n{len(bilan['erreurs'])} erreur(s) :")
                lignes += bilan["erreurs"][:10]
            if bilan["total"] == 0:
                lignes = ["Aucune photo trouvée dans la source."]
            messagebox.showinfo("Import terminé", "\n".join(lignes))
            fichiers = []
            for dossier in sorted(bilan["dossiers"]):
                fichiers += [p for p in dossier.iterdir()
                             if p.is_file() and not p.name.startswith(".")
                             and p.suffix.lower() in EXT_TOUTES]
            if fichiers:
                self.charger_photos(fichiers)

        # ---------------- liste de photos ----------------

        def ouvrir_dossier(self):
            choix = filedialog.askdirectory(title="Choisir le dossier à trier")
            if choix:
                self.charger_photos(lister_medias(choix))

        def charger_photos(self, fichiers):
            self.photos = regrouper(fichiers)
            self.classements = {d: charger_classement(d)
                                for d in {p.dossier for p in self.photos}}
            self.cache.clear()
            self.reinit_zoom()
            # on se place sur la première photo non classée
            self.index = 0
            for i, p in enumerate(self.photos):
                if self.statut(p) == NEUTRE:
                    self.index = i
                    break
            self.construire_bande()
            self.afficher()

        def statut(self, photo):
            return self.classements.get(photo.dossier, {}).get(photo.nom, NEUTRE)

        def classer(self, statut):
            if not self.photos:
                return
            photo = self.photos[self.index]
            classement = self.classements.setdefault(photo.dossier, {})
            if statut == NEUTRE:
                classement.pop(photo.nom, None)
            else:
                classement[photo.nom] = statut
            try:
                sauver_classement(photo.dossier, classement)
            except OSError as e:
                messagebox.showerror("Enregistrement impossible", str(e))
            self.bande.itemconfig(f"statut{self.index}", fill=COULEURS[statut])
            if self.index < len(self.photos) - 1:
                self.index += 1
                self.reinit_zoom()
            self.afficher()

        def supprimer_rejets(self):
            rejets = [p for p in self.photos if self.statut(p) == REJET]
            if not rejets:
                messagebox.showinfo("Rejets", "Aucune photo marquée en rejet.")
                return
            nb_fichiers = sum(len(p.fichiers) for p in rejets)
            if send2trash is not None:
                suite = "Les fichiers seront placés dans la Corbeille."
            else:
                suite = ("ATTENTION : suppression définitive, sans passer par "
                         "la Corbeille.\n(Installez send2trash pour utiliser "
                         "la Corbeille.)")
            if not messagebox.askyesno(
                    "Supprimer les photos rejetées",
                    f"Supprimer {len(rejets)} photo(s) rejetée(s), soit "
                    f"{nb_fichiers} fichier(s) ?\n\n{suite}",
                    icon="warning", default="no"):
                return
            erreurs = []
            for photo in rejets:
                restants = []
                for f in photo.fichiers:
                    try:
                        supprimer_fichier(f)
                    except Exception as e:
                        restants.append(f)
                        erreurs.append(f"{f.name} : {e}")
                photo.fichiers = restants
                if not restants:
                    self.classements[photo.dossier].pop(photo.nom, None)
                    self.photos.remove(photo)
            for dossier in {p.dossier for p in rejets}:
                try:
                    sauver_classement(dossier, self.classements[dossier])
                except OSError:
                    pass
            self.index = min(self.index, max(len(self.photos) - 1, 0))
            self.cache.clear()
            self.pleine = (None, None)
            self.reinit_zoom()
            self.construire_bande()
            self.afficher()
            if erreurs:
                messagebox.showwarning("Fichiers non supprimés",
                                       "\n".join(erreurs[:10]))

        # ---------------- bande de vignettes ----------------

        def construire_bande(self):
            b = self.bande
            b.delete("all")
            self.generation += 1
            self.index_par_chemin = {}
            a_charger = []
            for i, photo in enumerate(self.photos):
                xc = i * LARGEUR_CASE + LARGEUR_CASE / 2
                chemin = photo.fichier_affichable()
                self.index_par_chemin[chemin] = i
                b.create_rectangle(xc - 48, 8, xc + 48, 80,
                                   fill="#333333", outline="")
                if chemin in self.vignettes:
                    self._poser_vignette(i, chemin)
                else:
                    a_charger.append(chemin)
                b.create_rectangle(xc - 48, 84, xc + 48, 91, outline="",
                                   fill=COULEURS[self.statut(photo)],
                                   tags=f"statut{i}")
                nom = photo.nom if len(photo.nom) <= 15 else photo.nom[:14] + "…"
                b.create_text(xc, 101, text=nom, fill="#cccccc",
                              font=("Helvetica", 10))
            self.vignettes = {c: v for c, v in self.vignettes.items()
                              if c in self.index_par_chemin}
            b.config(scrollregion=(0, 0, max(len(self.photos) * LARGEUR_CASE, 1),
                                   HAUTEUR_BANDE))
            b.xview_moveto(0)
            if a_charger:
                threading.Thread(target=self._charger_vignettes,
                                 args=(self.generation, a_charger),
                                 daemon=True).start()

        def _charger_vignettes(self, generation, chemins):
            """Fil d'arrière-plan : vignettes les plus proches de la photo
            affichée en premier."""
            restants = {self.index_par_chemin.get(c, 0): c for c in chemins}
            while restants and generation == self.generation:
                i = min(restants, key=lambda k: abs(k - self.index))
                chemin = restants.pop(i)
                image = charger_image(chemin, taille_max=2 * VIGNETTE[0])
                if image is not None:
                    image.thumbnail(VIGNETTE)
                self.file_vignettes.put((generation, chemin, image))

        def _recevoir_vignettes(self):
            try:
                for _ in range(40):
                    generation, chemin, image = self.file_vignettes.get_nowait()
                    i = self.index_par_chemin.get(chemin)
                    if generation != self.generation or i is None:
                        continue
                    self.vignettes[chemin] = (
                        None if image is None else ImageTk.PhotoImage(image))
                    self._poser_vignette(i, chemin)
            except queue.Empty:
                pass
            self.racine.after(120, self._recevoir_vignettes)

        def _poser_vignette(self, i, chemin):
            xc = i * LARGEUR_CASE + LARGEUR_CASE / 2
            vignette = self.vignettes.get(chemin)
            if vignette is None:
                self.bande.create_text(
                    xc, 44, fill="#999999", font=("Helvetica", 11),
                    text=chemin.suffix.upper().lstrip("."))
            else:
                self.bande.create_image(xc, 44, image=vignette)

        def _centrer_bande(self):
            """Encadre la photo affichée et la ramène au milieu de la bande."""
            b = self.bande
            b.delete("selection")
            if not self.photos:
                return
            x0 = self.index * LARGEUR_CASE
            b.create_rectangle(x0 + 3, 3, x0 + LARGEUR_CASE - 3,
                               HAUTEUR_BANDE - 3, outline="white", width=2,
                               tags="selection")
            total = len(self.photos) * LARGEUR_CASE
            visible = max(b.winfo_width(), 1)
            if total > visible:
                debut = x0 + LARGEUR_CASE / 2 - visible / 2
                b.xview_moveto(min(max(debut, 0), total - visible) / total)

        def _clic_bande(self, evenement):
            i = int(self.bande.canvasx(evenement.x) // LARGEUR_CASE)
            if 0 <= i < len(self.photos) and i != self.index:
                self.index = i
                self.reinit_zoom()
                self.afficher()

        def _molette_bande(self, evenement):
            crans = evenement.delta
            if abs(crans) >= 120:      # Windows
                crans /= 120
            crans = int(max(-5, min(5, crans)))
            if crans:
                self.bande.xview_scroll(-crans, "units")

        # ---------------- clavier ----------------

        def touche(self, evenement):
            t = evenement.keysym.lower()
            if t == "x":
                self.classer(REJET)
            elif t == "n":
                self.classer(NEUTRE)
            elif t == "p":
                self.classer(GARDE)
            elif t in ("right", "space"):
                self.aller(1)
            elif t == "left":
                self.aller(-1)
            elif t in ("plus", "equal", "kp_add"):
                self.changer_zoom(PAS_ZOOM)
            elif t in ("minus", "kp_subtract"):
                self.changer_zoom(1 / PAS_ZOOM)
            elif t in ("0", "kp_0", "agrave"):
                self.reinit_zoom_et_afficher()

        def aller(self, pas):
            if self.photos:
                nouveau = max(0, min(len(self.photos) - 1, self.index + pas))
                if nouveau != self.index:
                    self.index = nouveau
                    self.reinit_zoom()
                self.afficher()

        # ---------------- zoom ----------------

        def reinit_zoom(self):
            self.zoom = 1.0
            self.centre = (0.5, 0.5)

        def reinit_zoom_et_afficher(self):
            self.reinit_zoom()
            self.afficher()

        def changer_zoom(self, facteur, x=None, y=None):
            """Zoom autour du point (x, y) du canevas, ou du centre."""
            if not self.photos or not self.taille_affichee:
                return
            nouveau = min(max(self.zoom * facteur, 1.0), ZOOM_MAX)
            if abs(nouveau - self.zoom) < 1e-9:
                return
            if x is not None:
                # le point de l'image sous le curseur reste sous le curseur
                rapport = nouveau / self.zoom
                l_aff, h_aff = self.taille_affichee
                dx = x - self.canevas.winfo_width() / 2
                dy = y - self.canevas.winfo_height() / 2
                self.centre = (
                    self.centre[0] + dx / l_aff * (1 - 1 / rapport),
                    self.centre[1] + dy / h_aff * (1 - 1 / rapport))
            self.zoom = nouveau
            if self.zoom == 1.0:
                self.centre = (0.5, 0.5)
            self.afficher()

        def _molette(self, evenement):
            if getattr(evenement, "num", None) == 4:
                crans = 1
            elif getattr(evenement, "num", None) == 5:
                crans = -1
            else:
                crans = evenement.delta
                if abs(crans) >= 120:      # Windows
                    crans /= 120
                crans = max(-3, min(3, crans))
            if crans:
                self.changer_zoom(1.12 ** crans, evenement.x, evenement.y)

        def _debut_glisse(self, evenement):
            self._glisse = (evenement.x, evenement.y)

        def _glisser(self, evenement):
            if (self._glisse is None or self.zoom <= 1.0
                    or not self.taille_affichee):
                return
            dx = evenement.x - self._glisse[0]
            dy = evenement.y - self._glisse[1]
            self._glisse = (evenement.x, evenement.y)
            l_aff, h_aff = self.taille_affichee
            self.centre = (self.centre[0] - dx / l_aff,
                           self.centre[1] - dy / h_aff)
            self.afficher()

        def image_pleine(self, photo):
            chemin = photo.fichier_affichable()
            if self.pleine[0] != chemin:
                self.pleine = (chemin, charger_image(chemin, taille_max=None))
            return self.pleine[1]

        # ---------------- affichage ----------------

        def image_de(self, photo):
            chemin = photo.fichier_affichable()
            if chemin in self.cache:
                self.cache.move_to_end(chemin)
                return self.cache[chemin]
            image = charger_image(chemin)
            self.cache[chemin] = image
            if len(self.cache) > 10:
                self.cache.popitem(last=False)
            return image

        def _redimensionne(self, _evenement):
            if self._redessin:
                self.racine.after_cancel(self._redessin)
            self._redessin = self.racine.after(80, self.afficher)

        def afficher(self):
            self._redessin = None
            c = self.canevas
            c.delete("all")
            largeur, hauteur = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
            centre = (largeur // 2, hauteur // 2)

            if not self.photos:
                c.create_text(
                    *centre, fill="#bbbbbb", font=("Helvetica", 16),
                    justify="center",
                    text="Importez une carte SD ou ouvrez un dossier.\n\n"
                         "X = rejet     N = neutre     P = gardé\n"
                         "←  →  = photo précédente / suivante")
                self.etiquette_statut.config(text="", bg="#1e1e1e")
                self.etiquette_info.config(text="")
                self.etiquette_compte.config(text="")
                self.texte_zoom.config(text="")
                self.taille_affichee = None
                self._centrer_bande()
                return

            photo = self.photos[self.index]
            image = self.image_de(photo)
            if image is None:
                self.taille_affichee = None
                c.create_text(
                    *centre, fill="#bbbbbb", font=("Helvetica", 15),
                    justify="center",
                    text=f"Aperçu indisponible\n{photo.fichier_affichable().name}"
                         + ("\n\n(pip3 install rawpy pour afficher les RAW)"
                            if rawpy is None and
                            photo.fichier_affichable().suffix.lower() in EXT_RAW
                            else ""))
            else:
                if self.zoom > 1.0:
                    image = self.image_pleine(photo) or image
                li, hi = image.size
                echelle = min(largeur / li, hauteur / hi) * self.zoom
                demi_l, demi_h = largeur / (2 * echelle), hauteur / (2 * echelle)
                # centre borné pour ne pas sortir de l'image
                cx = (li / 2 if li * echelle <= largeur else
                      min(max(self.centre[0] * li, demi_l), li - demi_l))
                cy = (hi / 2 if hi * echelle <= hauteur else
                      min(max(self.centre[1] * hi, demi_h), hi - demi_h))
                self.centre = (cx / li, cy / hi)
                self.taille_affichee = (li * echelle, hi * echelle)
                boite = (max(0, cx - demi_l), max(0, cy - demi_h),
                         min(li, cx + demi_l), min(hi, cy + demi_h))
                taille = (max(1, round((boite[2] - boite[0]) * echelle)),
                          max(1, round((boite[3] - boite[1]) * echelle)))
                filtre = Image.BICUBIC if self.zoom == 1.0 else Image.BILINEAR
                vue = image.resize(taille, filtre, box=boite, reducing_gap=2.0)
                self.image_tk = ImageTk.PhotoImage(vue)
                c.create_image(*centre, image=self.image_tk)

            self.texte_zoom.config(text=f"× {self.zoom:.1f}".replace(".", ","))
            statut = self.statut(photo)
            if statut != NEUTRE:  # liseré de couleur autour de l'image
                c.create_rectangle(3, 3, largeur - 3, hauteur - 3,
                                   outline=COULEURS[statut], width=6)
            self.etiquette_statut.config(text=LIBELLES[statut],
                                         bg=COULEURS[statut])
            extensions = " + ".join(sorted(f.suffix.upper().lstrip(".")
                                           for f in photo.fichiers))
            self.etiquette_info.config(
                text=f"{self.index + 1} / {len(self.photos)}    "
                     f"{photo.dossier.name} / {photo.nom}  ({extensions})")
            statuts = [self.statut(p) for p in self.photos]
            self.etiquette_compte.config(
                text=f"gardés {statuts.count(GARDE)}   "
                     f"neutres {statuts.count(NEUTRE)}   "
                     f"rejets {statuts.count(REJET)}")
            self._centrer_bande()

    racine = tk.Tk()
    Application(racine)
    racine.mainloop()


if __name__ == "__main__":
    lancer_interface()
