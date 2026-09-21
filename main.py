"""
================================================
  APPLICATION DE GESTION DES PRÉSENCES - V12
  - Trait barré BLEU
  - Couleurs vert et rouge plus claires
================================================
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.graphics import (PushMatrix, PopMatrix, Rotate, Rectangle,
                           Color as GColor)

import json
import os
import math
from datetime import date, datetime, timedelta

# ---------- CONFIGURATION ----------
FICHIER = "presences.json"

NB_SEQUENCES = 10
SLOTS_PAR_SEQ = 4

LARGEUR_NOM = dp(100)
LARGEUR_CELL = dp(46)
LARGEUR_MT = dp(60)
LARGEUR_SEP = dp(8)
HAUTEUR_ENTETE = dp(40)
HAUTEUR_LIGNE = dp(40)

# ---------- COULEURS ----------
C_PRESENT = "#81C784"      # vert clair
C_ABSENT = "#E57373"       # rouge clair
C_VIDE = "#E0E0E0"         # gris clair
C_ENTETE = "#455A64"
C_ENTETE_NOM = "#37474F"
C_ENTETE_MT = "#546E7A"

COULEUR_TRAIT = (0.13, 0.59, 0.95, 1)   # bleu vif (Material Blue 500)

Window.size = (700, 750)


# ---------- WIDGET : case pouvant être barrée ----------
class CellButton(Button):
    """Case avec un trait diagonal bleu dessiné via Rectangle+Rotate."""

    def __init__(self, barre=False, **kwargs):
        super().__init__(**kwargs)
        self._barre = barre
        with self.canvas.after:
            self._color = GColor(*COULEUR_TRAIT)
            PushMatrix()
            self._rot = Rotate(angle=0, origin=(0, 0))
            self._rect = Rectangle(pos=(0, 0), size=(0, 0))
            PopMatrix()
        self.bind(pos=self._update_trait, size=self._update_trait)
        self._update_trait()

    def set_barre(self, val):
        self._barre = val
        self._update_trait()

    def _update_trait(self, *args):
        if (not self._barre) or self.width < 10 or self.height < 10:
            self._rect.size = (0, 0)
            return

        marge = 3
        w = self.width
        h = self.height

        dx = w - 2 * marge
        dy = h - 2 * marge
        longueur = math.sqrt(dx * dx + dy * dy)
        angle = math.degrees(math.atan2(dy, dx))

        x0 = self.x + marge
        y0 = self.y + marge

        self._rot.origin = (x0, y0)
        self._rot.angle = angle
        self._rect.pos = (x0, y0 - 1)
        self._rect.size = (longueur, 2)


# ---------- FICHIERS ----------
def structure_vide():
    return {
        "eleves": [],
        "sequences": [
            {
                "dates": [""] * SLOTS_PAR_SEQ,
                "presences": {},
                "barres": {},
                "mt": {}
            }
            for _ in range(NB_SEQUENCES)
        ]
    }


def migrer_classe(c):
    if "sequences" in c:
        for seq in c["sequences"]:
            seq.setdefault("mt", {})
            seq.setdefault("barres", {})
        return c

    nouveau = structure_vide()
    nouveau["eleves"] = c.get("eleves", [])
    anciennes_dates = c.get("dates", [])
    anciennes_pres = c.get("presences", {})

    for i, d in enumerate(anciennes_dates):
        seq_idx = i // SLOTS_PAR_SEQ
        slot_idx = i % SLOTS_PAR_SEQ
        if seq_idx >= NB_SEQUENCES:
            break
        nouveau["sequences"][seq_idx]["dates"][slot_idx] = d
        for nom in nouveau["eleves"]:
            slot_list = nouveau["sequences"][seq_idx]["presences"].setdefault(
                nom, [""] * SLOTS_PAR_SEQ
            )
            slot_list[slot_idx] = anciennes_pres.get(d, {}).get(nom, "")
    return nouveau


def charger():
    if os.path.exists(FICHIER):
        try:
            with open(FICHIER, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "classes" not in data:
                return {"classes": {}, "classe_active": None}
            for nom_c, c in list(data["classes"].items()):
                data["classes"][nom_c] = migrer_classe(c)
            return data
        except Exception:
            pass
    return {"classes": {}, "classe_active": None}


def sauver(data):
    with open(FICHIER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_affichage(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return d.strftime("%d/%m")
    except Exception:
        return iso


def parse_date(txt):
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    for fmt in ("%d/%m", "%d-%m"):
        try:
            return datetime.strptime(txt + f"/{date.today().year}",
                                     fmt + "/%Y").strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


# ---------- APPLICATION ----------
class AppPresences(App):

    def build(self):
        self.title = "Présences"
        self.data = charger()
        self.mode_barre = False

        racine = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(4))

        # ===== Titre =====
        racine.add_widget(Label(
            text="GESTION DES PRÉSENCES",
            size_hint_y=None, height=dp(28),
            bold=True, font_size=dp(15)
        ))

        # ===== Sélecteur de classe =====
        ligne_classe = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
        ligne_classe.add_widget(Label(text="Classe :", size_hint_x=0.22))
        self.spinner_classe = Spinner(
            text="-- Aucune --", values=[], size_hint_x=0.78,
            background_color=get_color_from_hex("#607D8B")
        )
        self.spinner_classe.bind(text=self.changer_classe)
        ligne_classe.add_widget(self.spinner_classe)
        racine.add_widget(ligne_classe)

        # ===== Boutons classes =====
        ligne_gestion = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        b_new = Button(text="+ Classe",
                       background_color=get_color_from_hex("#3F51B5"),
                       color=(1, 1, 1, 1), font_size=dp(12))
        b_new.bind(on_press=self.nouvelle_classe)
        b_ren = Button(text="Renommer",
                       background_color=get_color_from_hex("#795548"),
                       color=(1, 1, 1, 1), font_size=dp(12))
        b_ren.bind(on_press=self.renommer_classe)
        b_sup = Button(text="Suppr. classe",
                       background_color=get_color_from_hex("#B71C1C"),
                       color=(1, 1, 1, 1), font_size=dp(12))
        b_sup.bind(on_press=self.supprimer_classe)
        ligne_gestion.add_widget(b_new)
        ligne_gestion.add_widget(b_ren)
        ligne_gestion.add_widget(b_sup)
        racine.add_widget(ligne_gestion)

        # ===== BOUTON MODE BARRÉ =====
        ligne_mode = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.btn_mode = Button(
            text="MODE NORMAL (clic -> change le statut)",
            background_color=get_color_from_hex("#9E9E9E"),
            color=(1, 1, 1, 1), bold=True, font_size=dp(13)
        )
        self.btn_mode.bind(on_press=self.toggle_mode)
        ligne_mode.add_widget(self.btn_mode)
        racine.add_widget(ligne_mode)

        # ===== Info =====
        self.lbl_info = Label(
            text="", size_hint_y=None, height=dp(20),
            font_size=dp(11), color=(0.3, 0.3, 0.3, 1)
        )
        racine.add_widget(self.lbl_info)

        # ===== Ajouter élève =====
        ligne_ajout = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
        self.champ_nom = TextInput(hint_text="Nom élève", multiline=False,
                                   size_hint_x=0.7)
        b_add_el = Button(text="+ Élève", size_hint_x=0.3,
                          background_color=get_color_from_hex("#2196F3"),
                          color=(1, 1, 1, 1), font_size=dp(12))
        b_add_el.bind(on_press=self.ajouter_eleve)
        ligne_ajout.add_widget(self.champ_nom)
        ligne_ajout.add_widget(b_add_el)
        racine.add_widget(ligne_ajout)

        # ===== Légende =====
        legende = BoxLayout(size_hint_y=None, height=dp(22), spacing=dp(4))
        legende.add_widget(Label(text="P = Présent", size_hint_x=0.25,
                                 font_size=dp(11),
                                 color=get_color_from_hex(C_PRESENT), bold=True))
        legende.add_widget(Label(text="A = Absent", size_hint_x=0.25,
                                 font_size=dp(11),
                                 color=get_color_from_hex(C_ABSENT), bold=True))
        legende.add_widget(Label(text="Barré = bleu", size_hint_x=0.25,
                                 font_size=dp(11),
                                 color=(0.13, 0.59, 0.95, 1), bold=True))
        legende.add_widget(Label(text="MT = libre", size_hint_x=0.25,
                                 font_size=dp(11), color=(0.4, 0.4, 0.4, 1)))
        racine.add_widget(legende)

        # ===== Zone du tableau =====
        self.scroll = ScrollView(do_scroll_x=True, do_scroll_y=True)
        self.tableau = BoxLayout(
            orientation="vertical", size_hint=(None, None), spacing=dp(1)
        )
        self.tableau.bind(minimum_width=self.tableau.setter("width"))
        self.tableau.bind(minimum_height=self.tableau.setter("height"))
        self.scroll.add_widget(self.tableau)
        racine.add_widget(self.scroll)

        self.rafraichir_spinner()
        self.rafraichir()

        return racine

    # ---------- MODE BARRÉ ----------
    def toggle_mode(self, *args):
        self.mode_barre = not self.mode_barre
        if self.mode_barre:
            self.btn_mode.text = "MODE BARRÉ (clic -> barre/débarre la case)"
            self.btn_mode.background_color = get_color_from_hex("#1976D2")
        else:
            self.btn_mode.text = "MODE NORMAL (clic -> change le statut)"
            self.btn_mode.background_color = get_color_from_hex("#9E9E9E")

    # ---------- GESTION CLASSES ----------
    def classe_actuelle(self):
        nom = self.data.get("classe_active")
        if nom and nom in self.data["classes"]:
            return nom
        return None

    def donnees_classe(self):
        nom = self.classe_actuelle()
        if nom:
            return self.data["classes"][nom]
        return None

    def rafraichir_spinner(self):
        classes = sorted(self.data["classes"].keys(), key=lambda x: x.lower())
        self.spinner_classe.values = classes
        active = self.classe_actuelle()
        if active:
            self.spinner_classe.text = active
        elif classes:
            self.data["classe_active"] = classes[0]
            self.spinner_classe.text = classes[0]
        else:
            self.spinner_classe.text = "-- Aucune --"

    def changer_classe(self, spinner, valeur):
        if valeur in self.data["classes"]:
            self.data["classe_active"] = valeur
            sauver(self.data)
            self.rafraichir()

    def nouvelle_classe(self, *args):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text="Nom de la nouvelle classe :",
                                 size_hint_y=None, height=dp(30)))
        champ = TextInput(multiline=False, hint_text="ex : 6ème A")
        contenu.add_widget(champ)
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_ok = Button(text="Créer",
                      background_color=get_color_from_hex("#4CAF50"),
                      color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Nouvelle classe", content=contenu, size_hint=(0.85, 0.4))

        def creer(*a):
            nom = champ.text.strip()
            if not nom:
                return
            if nom in self.data["classes"]:
                self.message("Info", "Cette classe existe déjà.")
                return
            self.data["classes"][nom] = structure_vide()
            self.data["classe_active"] = nom
            sauver(self.data)
            pop.dismiss()
            self.rafraichir_spinner()
            self.rafraichir()

        b_ok.bind(on_press=creer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    def renommer_classe(self, *args):
        ancien = self.classe_actuelle()
        if not ancien:
            self.message("Info", "Sélectionne d'abord une classe.")
            return
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=f"Nouveau nom pour « {ancien} » :",
                                 size_hint_y=None, height=dp(30)))
        champ = TextInput(text=ancien, multiline=False)
        contenu.add_widget(champ)
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_ok = Button(text="Renommer",
                      background_color=get_color_from_hex("#795548"),
                      color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Renommer la classe", content=contenu, size_hint=(0.85, 0.4))

        def renommer(*a):
            nouveau = champ.text.strip()
            if not nouveau or nouveau == ancien:
                pop.dismiss()
                return
            if nouveau in self.data["classes"]:
                self.message("Info", "Ce nom existe déjà.")
                return
            self.data["classes"][nouveau] = self.data["classes"].pop(ancien)
            self.data["classe_active"] = nouveau
            sauver(self.data)
            pop.dismiss()
            self.rafraichir_spinner()
            self.rafraichir()

        b_ok.bind(on_press=renommer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    def supprimer_classe(self, *args):
        nom = self.classe_actuelle()
        if not nom:
            self.message("Info", "Sélectionne d'abord une classe.")
            return
        nb = len(self.data["classes"][nom]["eleves"])
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(
            text=f"Supprimer « {nom} » ?\n({nb} élève(s) seront perdus)"
        ))
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_oui = Button(text="Oui, supprimer",
                       background_color=get_color_from_hex("#F44336"),
                       color=(1, 1, 1, 1))
        b_non = Button(text="Non")
        ligne.add_widget(b_oui)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Confirmer", content=contenu, size_hint=(0.85, 0.4))

        def supprimer(*a):
            del self.data["classes"][nom]
            restantes = list(self.data["classes"].keys())
            self.data["classe_active"] = restantes[0] if restantes else None
            sauver(self.data)
            pop.dismiss()
            self.rafraichir_spinner()
            self.rafraichir()

        b_oui.bind(on_press=supprimer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    # ---------- AJOUT ÉLÈVE ----------
    def ajouter_eleve(self, *args):
        donnees = self.donnees_classe()
        if not donnees:
            self.message("Info", "Crée d'abord une classe.")
            return
        nom = self.champ_nom.text.strip()
        if not nom:
            return
        if nom in donnees["eleves"]:
            self.message("Info", "Cet élève existe déjà dans cette classe.")
            return
        donnees["eleves"].append(nom)
        donnees["eleves"].sort(key=lambda x: x.lower())
        for seq in donnees["sequences"]:
            seq["presences"][nom] = [""] * SLOTS_PAR_SEQ
            seq["barres"][nom] = [False] * SLOTS_PAR_SEQ
            seq["mt"].setdefault(nom, "")
        self.champ_nom.text = ""
        sauver(self.data)
        self.rafraichir()

    # ---------- GESTION DATE ----------
    def clic_date(self, seq_idx, slot_idx):
        donnees = self.donnees_classe()
        if not donnees:
            return
        date_actuelle = donnees["sequences"][seq_idx]["dates"][slot_idx]

        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        titre_txt = "Modifier la date" if date_actuelle else "Ajouter une date"
        contenu.add_widget(Label(text=f"Séquence {seq_idx + 1} — Colonne {slot_idx + 1}",
                                 size_hint_y=None, height=dp(24), bold=True))
        contenu.add_widget(Label(text="Format : JJ/MM/AAAA ou JJ/MM",
                                 size_hint_y=None, height=dp(22), font_size=dp(12)))
        champ = TextInput(
            text=format_affichage(date_actuelle) if date_actuelle
                 else date.today().strftime("%d/%m/%Y"),
            multiline=False
        )
        contenu.add_widget(champ)

        ligne_rapide = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
        b_auj = Button(text="Aujourd'hui",
                       background_color=get_color_from_hex("#607D8B"),
                       color=(1, 1, 1, 1), font_size=dp(11))
        b_hier = Button(text="Hier",
                        background_color=get_color_from_hex("#607D8B"),
                        color=(1, 1, 1, 1), font_size=dp(11))
        b_dem = Button(text="Demain",
                       background_color=get_color_from_hex("#607D8B"),
                       color=(1, 1, 1, 1), font_size=dp(11))
        ligne_rapide.add_widget(b_auj)
        ligne_rapide.add_widget(b_hier)
        ligne_rapide.add_widget(b_dem)
        contenu.add_widget(ligne_rapide)

        ligne2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b_ok = Button(text="Valider",
                      background_color=get_color_from_hex("#009688"),
                      color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne2.add_widget(b_ok)
        ligne2.add_widget(b_non)
        contenu.add_widget(ligne2)

        if date_actuelle:
            b_eff = Button(text="Effacer cette date",
                           size_hint_y=None, height=dp(38),
                           background_color=get_color_from_hex("#B71C1C"),
                           color=(1, 1, 1, 1), font_size=dp(12))
            contenu.add_widget(b_eff)

        pop = Popup(title=titre_txt, content=contenu, size_hint=(0.9, 0.65))

        b_auj.bind(on_press=lambda *a: setattr(champ, "text", date.today().strftime("%d/%m/%Y")))
        b_hier.bind(on_press=lambda *a: setattr(champ, "text",
                                                (date.today() - timedelta(days=1)).strftime("%d/%m/%Y")))
        b_dem.bind(on_press=lambda *a: setattr(champ, "text",
                                               (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")))

        def valider(*a):
            iso = parse_date(champ.text)
            if iso is None:
                self.message("Erreur", "Format invalide.\nUtilise JJ/MM/AAAA")
                return
            donnees["sequences"][seq_idx]["dates"][slot_idx] = iso
            sauver(self.data)
            pop.dismiss()
            self.rafraichir()

        def effacer(*a):
            donnees["sequences"][seq_idx]["dates"][slot_idx] = ""
            seq = donnees["sequences"][seq_idx]
            for nom in donnees["eleves"]:
                if nom in seq["presences"]:
                    while len(seq["presences"][nom]) < SLOTS_PAR_SEQ:
                        seq["presences"][nom].append("")
                    seq["presences"][nom][slot_idx] = ""
                if nom in seq["barres"]:
                    while len(seq["barres"][nom]) < SLOTS_PAR_SEQ:
                        seq["barres"][nom].append(False)
                    seq["barres"][nom][slot_idx] = False
            sauver(self.data)
            pop.dismiss()
            self.rafraichir()

        b_ok.bind(on_press=valider)
        b_non.bind(on_press=pop.dismiss)
        if date_actuelle:
            b_eff.bind(on_press=effacer)
        pop.open()

    # ---------- MT (texte libre) ----------
    def clic_mt(self, nom, seq_idx):
        donnees = self.donnees_classe()
        if not donnees:
            return
        seq = donnees["sequences"][seq_idx]
        texte_actuel = seq["mt"].get(nom, "")

        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        contenu.add_widget(Label(text=f"{nom} — Séquence {seq_idx + 1}",
                                 size_hint_y=None, height=dp(24), bold=True))
        contenu.add_widget(Label(text="Texte libre (ex : 12, 15, Moy, etc.)",
                                 size_hint_y=None, height=dp(22), font_size=dp(12)))
        champ = TextInput(text=texte_actuel, multiline=False)
        contenu.add_widget(champ)

        ligne = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b_ok = Button(text="Valider",
                      background_color=get_color_from_hex("#009688"),
                      color=(1, 1, 1, 1))
        b_eff = Button(text="Effacer",
                       background_color=get_color_from_hex("#B71C1C"),
                       color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_eff)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)

        pop = Popup(title="MT — texte libre", content=contenu, size_hint=(0.9, 0.45))

        def valider(*a):
            seq["mt"][nom] = champ.text.strip()
            sauver(self.data)
            pop.dismiss()
            self.rafraichir()

        def effacer(*a):
            seq["mt"][nom] = ""
            sauver(self.data)
            pop.dismiss()
            self.rafraichir()

        b_ok.bind(on_press=valider)
        b_eff.bind(on_press=effacer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    # ---------- AFFICHAGE ----------
    def cellule_entete(self, texte, largeur, seq_idx=None, slot_idx=None, mt=False):
        if mt:
            return Button(
                text=texte, size_hint=(None, 1), width=largeur,
                background_color=get_color_from_hex(C_ENTETE_MT),
                color=(1, 1, 1, 1), bold=True, font_size=dp(12)
            )
        est_vide = texte == ""
        couleur = "#78909C" if est_vide else C_ENTETE
        txt = "+" if est_vide else texte
        btn = Button(
            text=txt, size_hint=(None, 1), width=largeur,
            background_color=get_color_from_hex(couleur),
            color=(1, 1, 1, 1), bold=True, font_size=dp(12)
        )
        if seq_idx is not None:
            btn.bind(on_press=lambda b, s=seq_idx, k=slot_idx: self.clic_date(s, k))
        return btn

    def rafraichir(self):
        self.tableau.clear_widgets()
        nom_classe = self.classe_actuelle()
        donnees = self.donnees_classe()

        if not nom_classe:
            self.lbl_info.text = "Aucune classe — crée-en une."
            self.tableau.add_widget(Label(
                text="Crée d'abord une classe.",
                size_hint=(None, None), size=(dp(250), dp(50))
            ))
            return

        eleves = donnees["eleves"]
        sequences = donnees["sequences"]
        self.lbl_info.text = f"Classe « {nom_classe} » — {len(eleves)} élève(s)"

        largeur_totale = (LARGEUR_NOM +
                          NB_SEQUENCES * (SLOTS_PAR_SEQ * LARGEUR_CELL + LARGEUR_MT + LARGEUR_SEP))

        # ===== EN-TÊTE =====
        entete = BoxLayout(orientation="horizontal", size_hint=(None, None),
                           height=HAUTEUR_ENTETE, spacing=0, width=largeur_totale)
        entete.add_widget(Button(
            text="Nom", size_hint=(None, 1), width=LARGEUR_NOM,
            background_color=get_color_from_hex(C_ENTETE_NOM),
            color=(1, 1, 1, 1), bold=True, font_size=dp(13)
        ))
        for s_idx, seq in enumerate(sequences):
            for k_idx in range(SLOTS_PAR_SEQ):
                d = seq["dates"][k_idx] if k_idx < len(seq["dates"]) else ""
                entete.add_widget(self.cellule_entete(
                    format_affichage(d) if d else "",
                    LARGEUR_CELL, s_idx, k_idx
                ))
            entete.add_widget(self.cellule_entete("MT", LARGEUR_MT, mt=True))
            entete.add_widget(Label(text="", size_hint=(None, 1), width=LARGEUR_SEP))

        self.tableau.add_widget(entete)

        # ===== LIGNES ÉLÈVES =====
        if not eleves:
            ligne = BoxLayout(orientation="horizontal", size_hint=(None, None),
                              height=HAUTEUR_LIGNE, spacing=0, width=largeur_totale)
            ligne.add_widget(Label(text="Ajoute un élève.", size_hint=(None, 1),
                                   width=dp(250)))
            self.tableau.add_widget(ligne)
            return

        for eleve in eleves:
            ligne = BoxLayout(orientation="horizontal", size_hint=(None, None),
                              height=HAUTEUR_LIGNE, spacing=0, width=largeur_totale)

            btn_nom = Button(
                text=eleve, size_hint=(None, 1), width=LARGEUR_NOM,
                background_color=(0.95, 0.95, 0.95, 1),
                color=(0.1, 0.1, 0.1, 1), font_size=dp(12)
            )
            btn_nom.bind(on_press=lambda b, n=eleve: self.confirmer_suppression(n))
            ligne.add_widget(btn_nom)

            for s_idx, seq in enumerate(sequences):
                slots = seq["presences"].get(eleve, [""] * SLOTS_PAR_SEQ)
                while len(slots) < SLOTS_PAR_SEQ:
                    slots.append("")
                barres = seq["barres"].get(eleve, [False] * SLOTS_PAR_SEQ)
                while len(barres) < SLOTS_PAR_SEQ:
                    barres.append(False)

                for k_idx in range(SLOTS_PAR_SEQ):
                    val = slots[k_idx]
                    est_barre = barres[k_idx]

                    if val == "P":
                        couleur = C_PRESENT
                        texte = "P"
                        txt_c = (1, 1, 1, 1)
                    elif val == "A":
                        couleur = C_ABSENT
                        texte = "A"
                        txt_c = (1, 1, 1, 1)
                    else:
                        couleur = C_VIDE
                        texte = ""
                        txt_c = (0.5, 0.5, 0.5, 1)

                    btn = CellButton(
                        barre=est_barre,
                        text=texte,
                        size_hint=(None, 1), width=LARGEUR_CELL,
                        background_color=get_color_from_hex(couleur),
                        color=txt_c, bold=True, font_size=dp(14)
                    )
                    btn.bind(on_press=lambda b, n=eleve, s=s_idx, k=k_idx:
                             self.clic_cellule(n, s, k))
                    ligne.add_widget(btn)

                # Colonne MT
                texte_mt = seq["mt"].get(eleve, "")
                if texte_mt:
                    couleur_mt = (1, 1, 1, 1)
                    fond_mt = "#ECEFF1"
                else:
                    couleur_mt = (0.6, 0.6, 0.6, 1)
                    fond_mt = "#FAFAFA"
                btn_mt = Button(
                    text=texte_mt, size_hint=(None, 1), width=LARGEUR_MT,
                    background_color=get_color_from_hex(fond_mt),
                    color=couleur_mt, bold=True, font_size=dp(12)
                )
                btn_mt.bind(on_press=lambda b, n=eleve, s=s_idx: self.clic_mt(n, s))
                ligne.add_widget(btn_mt)

                ligne.add_widget(Label(text="", size_hint=(None, 1), width=LARGEUR_SEP))

            self.tableau.add_widget(ligne)

    # ---------- ACTIONS ----------
    def clic_cellule(self, nom, seq_idx, slot_idx):
        donnees = self.donnees_classe()
        if not donnees:
            return
        seq = donnees["sequences"][seq_idx]

        if self.mode_barre:
            barres = seq["barres"].get(nom, [False] * SLOTS_PAR_SEQ)
            while len(barres) < SLOTS_PAR_SEQ:
                barres.append(False)
            barres[slot_idx] = not barres[slot_idx]
            seq["barres"][nom] = barres
        else:
            slots = seq["presences"].get(nom, [""] * SLOTS_PAR_SEQ)
            while len(slots) < SLOTS_PAR_SEQ:
                slots.append("")
            actuel = slots[slot_idx]
            ordre = ["", "P", "A"]
            idx = ordre.index(actuel) if actuel in ordre else 0
            slots[slot_idx] = ordre[(idx + 1) % len(ordre)]
            seq["presences"][nom] = slots

        sauver(self.data)
        self.rafraichir()

    def confirmer_suppression(self, nom):
        donnees = self.donnees_classe()
        if not donnees:
            return
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=f"Supprimer « {nom} » ?"))
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_oui = Button(text="Oui",
                       background_color=get_color_from_hex("#F44336"),
                       color=(1, 1, 1, 1))
        b_non = Button(text="Non")
        ligne.add_widget(b_oui)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Confirmer", content=contenu, size_hint=(0.85, 0.35))

        def supprimer(*a):
            donnees["eleves"].remove(nom)
            for seq in donnees["sequences"]:
                seq["presences"].pop(nom, None)
                seq["barres"].pop(nom, None)
                seq["mt"].pop(nom, None)
            sauver(self.data)
            pop.dismiss()
            self.rafraichir()

        b_oui.bind(on_press=supprimer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    def message(self, titre, msg):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=msg))
        btn = Button(text="OK", size_hint_y=None, height=dp(45))
        contenu.add_widget(btn)
        pop = Popup(title=titre, content=contenu, size_hint=(0.85, 0.4))
        btn.bind(on_press=pop.dismiss)
        pop.open()


if __name__ == "__main__":
    AppPresences().run()
