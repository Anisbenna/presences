"""
================================================
  APPLICATION DE GESTION DES PRÉSENCES - V17
  - Correction du plantage au démarrage (en-tête ajouté deux fois)
  - Tableau RecycleView réellement fonctionnel (lignes recyclées)
  - En-tête des dates synchronisé avec le défilement horizontal
  - Lignes dessinées d'un bloc (au lieu de 100 boutons) : ouverture rapide
  - Clic sur une case : mise à jour instantanée (plus de rechargement global)
  - Sauvegarde différée et atomique (pas de fichier corrompu)
  - Android : données dans le dossier privé de l'appli (non effacées
    lors d'une mise à jour), permissions demandées au démarrage
================================================
"""

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.effects.scroll import ScrollEffect
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import get_color_from_hex, platform
from kivy.graphics import Line, Rectangle, Color as GColor
from kivy.core.text import Label as CoreLabel

import json
import os
import shutil
from datetime import date, datetime

# ---------- CONFIGURATION ----------
NOM_FICHIER = "presences.json"
FICHIER = NOM_FICHIER          # chemin complet fixé au démarrage (voir build)
NB_SEQUENCES = 20
SLOTS_PAR_SEQ = 4
NB_CASES = NB_SEQUENCES * SLOTS_PAR_SEQ

LARGEUR_NOM = dp(80)
LARGEUR_CELL = dp(38)
LARGEUR_MT = dp(48)
LARGEUR_SEP = dp(6)
HAUTEUR_ENTETE = dp(42)
HAUTEUR_LIGNE = dp(48)
LARGEUR_TOTALE = LARGEUR_NOM + NB_SEQUENCES * (
    SLOTS_PAR_SEQ * LARGEUR_CELL + LARGEUR_MT + LARGEUR_SEP)

C_PRESENT = "#81C784"
C_ABSENT = "#E57373"
C_VIDE = "#E0E0E0"
C_ENTETE = "#455A64"
C_ENTETE_NOM = "#37474F"
C_ENTETE_MT = "#546E7A"

# Couleurs pré-calculées (évite des milliers de conversions au défilement)
COL_PRESENT = get_color_from_hex(C_PRESENT)
COL_ABSENT = get_color_from_hex(C_ABSENT)
COL_VIDE = get_color_from_hex(C_VIDE)
COL_DATE_OK = get_color_from_hex(C_ENTETE)
COL_DATE_VIDE = get_color_from_hex("#78909C")
COL_MT_PLEIN = get_color_from_hex("#CFD8DC")
COL_MT_VIDE = get_color_from_hex("#FAFAFA")
BLANC = (1, 1, 1, 1)
GRIS_TEXTE = (0.5, 0.5, 0.5, 1)
NOIR_TEXTE = (0.1, 0.1, 0.1, 1)

COULEUR_TRAIT = (0.13, 0.59, 0.95, 1)

if platform != "android":
    Window.size = (700, 750)


# ---------- DOSSIERS ----------
def _dossier_ecrivable(d):
    try:
        os.makedirs(d, exist_ok=True)
        test = os.path.join(d, ".test_ecriture")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return True
    except Exception:
        return False


def dossier_sauvegardes():
    if platform == "android":
        d = "/storage/emulated/0/Download/Presences"
        if _dossier_ecrivable(d):
            return d
        app = App.get_running_app()
        d = os.path.join(app.user_data_dir, "sauvegardes")
    else:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sauvegardes")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def liste_sauvegardes():
    dossier = dossier_sauvegardes()
    if not os.path.exists(dossier):
        return []
    fichiers = [f for f in os.listdir(dossier) if f.endswith(".json")]
    fichiers.sort(reverse=True)
    return fichiers


# ---------- TEXTES PRÉ-RENDUS (partagés par toutes les lignes) ----------
_CACHE_TEXTURES = {}


def texture_texte(texte, taille, couleur, gras=True):
    """Rend un texte une seule fois puis le réutilise partout (P, A, notes MT...)."""
    cle = (texte, taille, couleur, gras)
    tex = _CACHE_TEXTURES.get(cle)
    if tex is None:
        lab = CoreLabel(text=texte, font_size=taille, bold=gras, color=couleur)
        lab.refresh()
        tex = lab.texture
        if len(_CACHE_TEXTURES) < 2000:
            _CACHE_TEXTURES[cle] = tex
    return tex


LARGEUR_SEQ = SLOTS_PAR_SEQ * LARGEUR_CELL + LARGEUR_MT + LARGEUR_SEP


# ---------- WIDGET : Ligne recyclée, dessinée d'un bloc ----------
class LigneEleve(RecycleDataViewBehavior, RelativeLayout):
    """Une ligne du tableau. Au lieu de 100 boutons Kivy (lents à créer sur
    téléphone), les cases sont de simples rectangles dessinés sur le canvas ;
    le toucher est localisé par sa position. RelativeLayout : coordonnées
    locales fixes, rien à recalculer pendant le défilement."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (LARGEUR_TOTALE, HAUTEUR_LIGNE)
        self.index = None
        self._data = None
        self.textes_cases = [""] * NB_CASES     # ce qui est affiché (utile aux tests)
        self.textes_mt = [""] * NB_SEQUENCES
        self.barres_visibles = [False] * NB_CASES

        h = HAUTEUR_LIGNE
        self._c_fond, self._r_texte, self._ln = [], [], []
        self._mt_fond, self._mt_texte = [], []
        with self.canvas:
            for s in range(NB_SEQUENCES):
                x0 = LARGEUR_NOM + s * LARGEUR_SEQ
                for k in range(SLOTS_PAR_SEQ):
                    x = x0 + k * LARGEUR_CELL
                    self._c_fond.append(GColor(*COL_VIDE))
                    Rectangle(pos=(x + 1, 1), size=(LARGEUR_CELL - 2, h - 2))
                    GColor(1, 1, 1, 1)
                    self._r_texte.append(Rectangle(pos=(x, 0), size=(0, 0)))
                    GColor(*COULEUR_TRAIT)
                    self._ln.append(Line(points=[], width=dp(1)))
                xm = x0 + SLOTS_PAR_SEQ * LARGEUR_CELL
                self._mt_fond.append(GColor(*COL_MT_VIDE))
                Rectangle(pos=(xm + 1, 1), size=(LARGEUR_MT - 2, h - 2))
                GColor(1, 1, 1, 1)
                self._mt_texte.append(Rectangle(pos=(xm, 0), size=(0, 0)))

        self.btn_nom = Button(
            text="", size_hint=(None, None), size=(LARGEUR_NOM, h), pos=(0, 0),
            background_color=(0.95, 0.95, 0.95, 1), color=NOIR_TEXTE,
            font_size=dp(12), shorten=True, shorten_from="right",
            text_size=(LARGEUR_NOM - dp(4), None), halign="center")
        self.btn_nom.bind(on_release=self.on_supprimer)
        self.add_widget(self.btn_nom)

    # --- dessin ---
    @staticmethod
    def _poser_texte(rect, x, largeur, tex):
        if tex is None:
            rect.size = (0, 0)
            return
        w, hh = tex.size
        rect.texture = tex
        rect.size = (w, hh)
        rect.pos = (x + (largeur - w) / 2, (HAUTEUR_LIGNE - hh) / 2)

    def afficher_case(self, i, val, barre):
        s, k = divmod(i, SLOTS_PAR_SEQ)
        x = LARGEUR_NOM + s * LARGEUR_SEQ + k * LARGEUR_CELL
        if val == "P":
            self._c_fond[i].rgba = COL_PRESENT
        elif val == "A":
            self._c_fond[i].rgba = COL_ABSENT
        else:
            self._c_fond[i].rgba = COL_VIDE
            val = ""
        self._poser_texte(self._r_texte[i], x, LARGEUR_CELL,
                          texture_texte(val, dp(14), BLANC) if val else None)
        m = 3
        self._ln[i].points = ([x + m, m, x + LARGEUR_CELL - m, HAUTEUR_LIGNE - m]
                              if barre else [])
        self.textes_cases[i] = val
        self.barres_visibles[i] = bool(barre)

    def afficher_mt(self, s, texte):
        xm = LARGEUR_NOM + s * LARGEUR_SEQ + SLOTS_PAR_SEQ * LARGEUR_CELL
        self._mt_fond[s].rgba = COL_MT_PLEIN if texte else COL_MT_VIDE
        self._poser_texte(self._mt_texte[s], xm, LARGEUR_MT,
                          texture_texte(texte, dp(12), NOIR_TEXTE) if texte else None)
        self.textes_mt[s] = texte

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self._data = data
        self.btn_nom.text = data["nom"]
        cases, barres, mt = data["cases"], data["barres"], data["mt"]
        for i in range(NB_CASES):
            self.afficher_case(i, cases[i], barres[i])
        for s in range(NB_SEQUENCES):
            self.afficher_mt(s, mt[s])

    # --- toucher ---
    def _zone(self, touch):
        """Renvoie ('case', i), ('mt', s) ou None selon l'endroit touché."""
        lx = touch.x - self.x - LARGEUR_NOM
        if lx < 0 or not (self.y <= touch.y <= self.top):
            return None
        s = int(lx // LARGEUR_SEQ)
        if s >= NB_SEQUENCES:
            return None
        r = lx - s * LARGEUR_SEQ
        if r < SLOTS_PAR_SEQ * LARGEUR_CELL:
            return ("case", s * SLOTS_PAR_SEQ + int(r // LARGEUR_CELL))
        if r < SLOTS_PAR_SEQ * LARGEUR_CELL + LARGEUR_MT:
            return ("mt", s)
        return None

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self._zone(touch):
            touch.grab(self)
            touch.ud[id(self)] = self._zone(touch)
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            zone = touch.ud.get(id(self))
            if zone and self.collide_point(*touch.pos) and self._zone(touch) == zone:
                if zone[0] == "case":
                    self.on_click_case(zone[1])
                else:
                    self.on_click_mt(zone[1])
            return True
        return super().on_touch_up(touch)

    def on_supprimer(self, *args):
        App.get_running_app().confirmer_suppression(self._data["nom"])

    def on_click_case(self, i):
        app = App.get_running_app()
        s, k = divmod(i, SLOTS_PAR_SEQ)
        val, barre = app.clic_cellule(self._data["nom"], s, k)
        # Mise à jour locale : uniquement la case touchée
        self._data["cases"][i] = val
        self._data["barres"][i] = barre
        self.afficher_case(i, val, barre)

    def on_click_mt(self, s_idx):
        App.get_running_app().clic_mt(self._data["nom"], s_idx)


# ---------- FICHIERS ----------
def sequence_vide():
    return {"dates": [""] * SLOTS_PAR_SEQ, "presences": {}, "barres": {}, "mt": {}}


def structure_vide():
    return {"eleves": [], "sequences": [sequence_vide() for _ in range(NB_SEQUENCES)]}


def migrer_classe(c):
    c.setdefault("eleves", [])
    c.setdefault("sequences", [])
    while len(c["sequences"]) < NB_SEQUENCES:
        c["sequences"].append(sequence_vide())
    for seq in c["sequences"]:
        seq.setdefault("mt", {})
        seq.setdefault("barres", {})
        seq.setdefault("presences", {})
        seq.setdefault("dates", [""] * SLOTS_PAR_SEQ)
        while len(seq["dates"]) < SLOTS_PAR_SEQ:
            seq["dates"].append("")
    return c


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
    """Écriture atomique : fichier temporaire puis remplacement."""
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, FICHIER)


def format_affichage(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m")
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


def _complet(lst, n, defaut):
    lst = list(lst) if lst else []
    while len(lst) < n:
        lst.append(defaut)
    return lst


# ---------- APPLICATION ----------
class AppPresences(App):

    def build(self):
        self.title = "Présences"
        self._preparer_fichier()
        self.data = charger()
        self.mode_barre = False
        self._sauvegarde_differee = Clock.create_trigger(self._sauver_maintenant, 0.8)

        racine = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(4))

        racine.add_widget(Label(text="GESTION DES PRÉSENCES", size_hint_y=None,
                                height=dp(32), bold=True, font_size=dp(18)))

        # ===== Classe =====
        ligne_classe = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        ligne_classe.add_widget(Label(text="Classe :", size_hint_x=0.22))
        self.spinner_classe = Spinner(text="-- Aucune --", values=[], size_hint_x=0.78,
                                      background_color=get_color_from_hex("#607D8B"))
        self.spinner_classe.bind(text=self.changer_classe)
        ligne_classe.add_widget(self.spinner_classe)
        racine.add_widget(ligne_classe)

        # ===== Gestion Classes =====
        ligne_gestion = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        for texte, coul, action in (("+ Classe", "#3F51B5", self.nouvelle_classe),
                                    ("Renommer", "#795548", self.renommer_classe),
                                    ("Suppr. classe", "#B71C1C", self.supprimer_classe)):
            b = Button(text=texte, background_color=get_color_from_hex(coul),
                       color=BLANC, font_size=dp(13))
            b.bind(on_release=action)
            ligne_gestion.add_widget(b)
        racine.add_widget(ligne_gestion)

        # ===== Modes et Sauvegarde =====
        ligne_mode = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.btn_mode = Button(text="MODE NORMAL", background_color=get_color_from_hex("#9E9E9E"),
                               color=BLANC, bold=True, font_size=dp(13))
        self.btn_mode.bind(on_release=self.toggle_mode)
        btn_sauvegarde = Button(text="Sauvegarde", background_color=get_color_from_hex("#00897B"),
                                color=BLANC, bold=True, font_size=dp(13), size_hint_x=0.4)
        btn_sauvegarde.bind(on_release=self.menu_sauvegarde)
        ligne_mode.add_widget(self.btn_mode)
        ligne_mode.add_widget(btn_sauvegarde)
        racine.add_widget(ligne_mode)

        # ===== Info =====
        self.lbl_info = Label(text="", size_hint_y=None, height=dp(22),
                              font_size=dp(12), color=(0.7, 0.7, 0.7, 1))
        racine.add_widget(self.lbl_info)

        # ===== Ajouter élève =====
        ligne_ajout = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.champ_nom = TextInput(hint_text="Nom élève", multiline=False, size_hint_x=0.7)
        self.champ_nom.bind(on_text_validate=self.ajouter_eleve)
        b_add_el = Button(text="+ Élève", size_hint_x=0.3, background_color=get_color_from_hex("#2196F3"),
                          color=BLANC, font_size=dp(13))
        b_add_el.bind(on_release=self.ajouter_eleve)
        ligne_ajout.add_widget(self.champ_nom)
        ligne_ajout.add_widget(b_add_el)
        racine.add_widget(ligne_ajout)

        # ===== Légende =====
        legende = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(4))
        legende.add_widget(Label(text="P=Présent", font_size=dp(11), color=COL_PRESENT, bold=True))
        legende.add_widget(Label(text="A=Absent", font_size=dp(11), color=COL_ABSENT, bold=True))
        legende.add_widget(Label(text="Barré=bleu", font_size=dp(11), color=COULEUR_TRAIT, bold=True))
        legende.add_widget(Label(text="MT=libre", font_size=dp(11), color=(0.6, 0.6, 0.6, 1)))
        racine.add_widget(legende)

        # ===== EN-TÊTE (dates) : défile horizontalement avec le tableau =====
        self.scroll_entete = ScrollView(do_scroll_x=False, do_scroll_y=False,
                                        size_hint_y=None, height=HAUTEUR_ENTETE,
                                        bar_width=0)
        cadre_entete = RelativeLayout(size_hint=(None, None),
                                      size=(LARGEUR_TOTALE, HAUTEUR_ENTETE))
        entete_box = BoxLayout(orientation="horizontal", spacing=0)
        cadre_entete.add_widget(entete_box)
        entete_box.add_widget(Button(text="Nom", size_hint=(None, 1), width=LARGEUR_NOM,
                                     background_color=get_color_from_hex(C_ENTETE_NOM),
                                     color=BLANC, bold=True, font_size=dp(13)))
        self.liste_entetes = []
        for s_idx in range(NB_SEQUENCES):
            for k_idx in range(SLOTS_PAR_SEQ):
                btn = Button(text="", size_hint=(None, 1), width=LARGEUR_CELL,
                             background_color=COL_DATE_VIDE, color=BLANC,
                             bold=True, font_size=dp(12))
                btn.bind(on_release=lambda b, s=s_idx, k=k_idx: self.clic_date(s, k))
                entete_box.add_widget(btn)
                self.liste_entetes.append(btn)
            entete_box.add_widget(Button(text=f"MT{s_idx + 1}", size_hint=(None, 1), width=LARGEUR_MT,
                                         background_color=get_color_from_hex(C_ENTETE_MT),
                                         color=BLANC, bold=True, font_size=dp(11)))
            entete_box.add_widget(Label(text="", size_hint=(None, 1), width=LARGEUR_SEP))
        self.scroll_entete.add_widget(cadre_entete)
        racine.add_widget(self.scroll_entete)

        # ===== TABLEAU (RecycleView : seules les lignes visibles existent) =====
        self.rv = RecycleView(do_scroll_x=True, do_scroll_y=True,
                              scroll_type=["bars", "content"], bar_width=dp(10),
                              bar_color=(0.4, 0.5, 0.6, 1), effect_cls=ScrollEffect)
        disposition = RecycleBoxLayout(orientation="vertical",
                                       default_size=(LARGEUR_TOTALE, HAUTEUR_LIGNE),
                                       default_size_hint=(None, None),
                                       size_hint=(None, None), width=LARGEUR_TOTALE)
        disposition.bind(minimum_height=disposition.setter("height"))
        self.rv.add_widget(disposition)
        self.rv.viewclass = LigneEleve   # APRÈS add_widget, sinon aucune ligne n'apparaît
        self.rv.bind(scroll_x=self._synchro_entete)
        racine.add_widget(self.rv)

        self.rafraichir_spinner()
        self.rafraichir()
        return racine

    # ---------- CYCLE DE VIE ----------
    def _preparer_fichier(self):
        """Android : le dossier de l'appli est effacé à chaque mise à jour de
        l'APK ; on stocke donc les données dans user_data_dir."""
        global FICHIER
        if platform == "android":
            FICHIER = os.path.join(self.user_data_dir, NOM_FICHIER)
            ancien = os.path.abspath(NOM_FICHIER)
            if not os.path.exists(FICHIER) and os.path.exists(ancien):
                try:
                    shutil.copy2(ancien, FICHIER)
                except Exception:
                    pass
        else:
            FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), NOM_FICHIER)

    def on_start(self):
        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE,
                                     Permission.READ_EXTERNAL_STORAGE])
            except Exception:
                pass

    def on_pause(self):
        self._sauver_maintenant()
        return True

    def on_stop(self):
        self._sauver_maintenant()

    def _synchro_entete(self, rv, valeur):
        self.scroll_entete.scroll_x = valeur

    def planifier_sauvegarde(self):
        self._sauvegarde_differee()

    def _sauver_maintenant(self, *args):
        try:
            sauver(self.data)
        except Exception as e:
            print("Erreur de sauvegarde :", e)

    # ---------- MISE A JOUR ----------
    def rafraichir(self):
        nom_classe = self.classe_actuelle()
        donnees = self.donnees_classe()

        if not nom_classe:
            self.lbl_info.text = "Aucune classe — crée-en une."
            for btn in self.liste_entetes:
                btn.text = "+"
                btn.background_color = COL_DATE_VIDE
            self.rv.data = []
            return

        eleves = donnees["eleves"]
        sequences = donnees["sequences"]
        self.lbl_info.text = f"Classe « {nom_classe} » — {len(eleves)} élève(s)"

        idx = 0
        for seq in sequences[:NB_SEQUENCES]:
            for k_idx in range(SLOTS_PAR_SEQ):
                d = seq["dates"][k_idx]
                self.liste_entetes[idx].text = format_affichage(d) if d else "+"
                self.liste_entetes[idx].background_color = COL_DATE_OK if d else COL_DATE_VIDE
                idx += 1

        rv_data = []
        for eleve in eleves:
            cases, barres, mt_vals = [], [], []
            for seq in sequences[:NB_SEQUENCES]:
                cases.extend(_complet(seq["presences"].get(eleve), SLOTS_PAR_SEQ, "")[:SLOTS_PAR_SEQ])
                barres.extend(_complet(seq["barres"].get(eleve), SLOTS_PAR_SEQ, False)[:SLOTS_PAR_SEQ])
                mt_vals.append(seq["mt"].get(eleve, ""))
            rv_data.append({"nom": eleve, "cases": cases, "barres": barres, "mt": mt_vals})
        self.rv.data = rv_data

    def classe_actuelle(self):
        nom = self.data.get("classe_active")
        if nom and nom in self.data["classes"]:
            return nom
        return None

    def donnees_classe(self):
        nom = self.classe_actuelle()
        return self.data["classes"][nom] if nom else None

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
        if valeur in self.data["classes"] and valeur != self.data.get("classe_active"):
            self.data["classe_active"] = valeur
            self.planifier_sauvegarde()
            self.rafraichir()
            self.rv.scroll_y = 1

    def toggle_mode(self, *args):
        self.mode_barre = not self.mode_barre
        self.btn_mode.text = "MODE BARRÉ" if self.mode_barre else "MODE NORMAL"
        self.btn_mode.background_color = get_color_from_hex("#1976D2" if self.mode_barre else "#9E9E9E")

    def ajouter_eleve(self, *args):
        donnees = self.donnees_classe()
        if not donnees:
            return self.message("Info", "Crée d'abord une classe.")
        nom = self.champ_nom.text.strip()
        if not nom:
            return
        if nom in donnees["eleves"]:
            return self.message("Info", f"« {nom} » existe déjà.")
        donnees["eleves"].append(nom)
        donnees["eleves"].sort(key=lambda x: x.lower())
        for seq in donnees["sequences"]:
            seq["presences"][nom] = [""] * SLOTS_PAR_SEQ
            seq["barres"][nom] = [False] * SLOTS_PAR_SEQ
            seq["mt"].setdefault(nom, "")
        self.champ_nom.text = ""
        self._sauver_maintenant()
        self.rafraichir()

    def clic_cellule(self, nom, seq_idx, slot_idx):
        """Modifie la donnée et renvoie (valeur, barré) ; pas de rechargement global."""
        seq = self.donnees_classe()["sequences"][seq_idx]
        slots = _complet(seq["presences"].get(nom), SLOTS_PAR_SEQ, "")
        barres = _complet(seq["barres"].get(nom), SLOTS_PAR_SEQ, False)
        if self.mode_barre:
            barres[slot_idx] = not barres[slot_idx]
        else:
            ordre = ["", "P", "A"]
            actuel = slots[slot_idx]
            idx = ordre.index(actuel) if actuel in ordre else 0
            slots[slot_idx] = ordre[(idx + 1) % len(ordre)]
        seq["presences"][nom] = slots
        seq["barres"][nom] = barres
        self.planifier_sauvegarde()
        return slots[slot_idx], barres[slot_idx]

    def confirmer_suppression(self, nom):
        donnees = self.donnees_classe()
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=f"Supprimer « {nom} » ?"))
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_oui = Button(text="Oui", background_color=get_color_from_hex("#F44336"), color=BLANC)
        b_non = Button(text="Non")
        ligne.add_widget(b_oui)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Confirmer", content=contenu, size_hint=(0.85, 0.35))

        def supprimer(*a):
            if nom in donnees["eleves"]:
                donnees["eleves"].remove(nom)
            for seq in donnees["sequences"]:
                seq["presences"].pop(nom, None)
                seq["barres"].pop(nom, None)
                seq["mt"].pop(nom, None)
            self._sauver_maintenant()
            pop.dismiss()
            self.rafraichir()
        b_oui.bind(on_release=supprimer)
        b_non.bind(on_release=pop.dismiss)
        pop.open()

    # ---------- SAUVEGARDE ----------
    def menu_sauvegarde(self, *args):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        b_sauver = Button(text="Créer une sauvegarde", size_hint_y=None, height=dp(50),
                          background_color=get_color_from_hex("#4CAF50"), color=BLANC, bold=True)
        contenu.add_widget(b_sauver)
        contenu.add_widget(Label(text=f"Dossier :\n{dossier_sauvegardes()}", size_hint_y=None,
                                 height=dp(40), font_size=dp(10), color=(0.7, 0.7, 0.7, 1)))
        contenu.add_widget(Label(text="Sauvegardes (toucher pour restaurer) :",
                                 size_hint_y=None, height=dp(28), bold=True))
        scroll = ScrollView()
        liste = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
        liste.bind(minimum_height=liste.setter("height"))
        fichiers = liste_sauvegardes()
        if not fichiers:
            liste.add_widget(Label(text="Aucune.", size_hint_y=None, height=dp(40)))
        else:
            for f in fichiers:
                btn = Button(text=f.replace("presences_", "").replace(".json", ""),
                             size_hint_y=None, height=dp(44),
                             background_color=get_color_from_hex("#546E7A"), color=BLANC)
                btn.bind(on_release=lambda b, nom=f: self.confirmer_restauration(nom, pop))
                liste.add_widget(btn)
        scroll.add_widget(liste)
        contenu.add_widget(scroll)
        b_fermer = Button(text="Fermer", size_hint_y=None, height=dp(45))
        contenu.add_widget(b_fermer)
        pop = Popup(title="Sauvegarde", content=contenu, size_hint=(0.92, 0.85))
        b_sauver.bind(on_release=lambda x: [pop.dismiss(), self.creer_sauvegarde()])
        b_fermer.bind(on_release=pop.dismiss)
        pop.open()

    def creer_sauvegarde(self):
        self._sauver_maintenant()
        nom = "presences_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".json"
        chemin = os.path.join(dossier_sauvegardes(), nom)
        try:
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            self.message("Sauvegarde OK", f"Créée : {nom}")
        except Exception as e:
            self.message("Erreur", str(e))

    def confirmer_restauration(self, nom_fichier, pop_parent):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=f"Remplacer les données actuelles par\n{nom_fichier} ?",
                                 halign="center"))
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_oui = Button(text="Restaurer", background_color=get_color_from_hex("#F44336"), color=BLANC)
        b_non = Button(text="Annuler")
        ligne.add_widget(b_oui)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Confirmer", content=contenu, size_hint=(0.9, 0.35))

        def ok(*a):
            pop.dismiss()
            pop_parent.dismiss()
            self.restaurer_sauvegarde(nom_fichier)
        b_oui.bind(on_release=ok)
        b_non.bind(on_release=pop.dismiss)
        pop.open()

    def restaurer_sauvegarde(self, nom_fichier):
        chemin = os.path.join(dossier_sauvegardes(), nom_fichier)
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "classes" not in data:
                raise ValueError("Fichier de sauvegarde invalide.")
            for c in data["classes"].values():
                migrer_classe(c)
            data.setdefault("classe_active", None)
            self.data = data
            self._sauver_maintenant()
            self.rafraichir_spinner()
            self.rafraichir()
            self.message("OK", "Données restaurées.")
        except Exception as e:
            self.message("Erreur", str(e))

    def message(self, titre, msg):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=msg, halign="center"))
        btn = Button(text="OK", size_hint_y=None, height=dp(45))
        contenu.add_widget(btn)
        pop = Popup(title=titre, content=contenu, size_hint=(0.85, 0.5))
        btn.bind(on_release=pop.dismiss)
        pop.open()

    def _popup_saisie(self, titre, texte_label, texte_init, texte_ok, couleur, action, hauteur=0.4):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        if texte_label:
            contenu.add_widget(Label(text=texte_label, size_hint_y=None, height=dp(26)))
        champ = TextInput(text=texte_init, multiline=False, size_hint_y=None, height=dp(44))
        contenu.add_widget(champ)
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_ok = Button(text=texte_ok, background_color=get_color_from_hex(couleur), color=BLANC)
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title=titre, content=contenu, size_hint=(0.9, hauteur))

        def valider(*a):
            if action(champ.text.strip()) is not False:
                pop.dismiss()
        b_ok.bind(on_release=valider)
        champ.bind(on_text_validate=valider)
        b_non.bind(on_release=pop.dismiss)
        pop.open()
        return pop

    def nouvelle_classe(self, *args):
        def creer(nom):
            if not nom or nom in self.data["classes"]:
                return False
            self.data["classes"][nom] = structure_vide()
            self.data["classe_active"] = nom
            self._sauver_maintenant()
            self.rafraichir_spinner()
            self.rafraichir()
        self._popup_saisie("Nouvelle classe", "Nom de la classe :", "", "Créer", "#4CAF50", creer)

    def renommer_classe(self, *args):
        ancien = self.classe_actuelle()
        if not ancien:
            return

        def renommer(nouveau):
            if not nouveau or nouveau == ancien or nouveau in self.data["classes"]:
                return False
            self.data["classes"][nouveau] = self.data["classes"].pop(ancien)
            self.data["classe_active"] = nouveau
            self._sauver_maintenant()
            self.rafraichir_spinner()
            self.rafraichir()
        self._popup_saisie("Renommer", "Nouveau nom :", ancien, "Renommer", "#795548", renommer)

    def supprimer_classe(self, *args):
        nom = self.classe_actuelle()
        if not nom:
            return
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(text=f"Supprimer la classe « {nom} » ?"))
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_oui = Button(text="Oui", background_color=get_color_from_hex("#F44336"), color=BLANC)
        b_non = Button(text="Non")
        ligne.add_widget(b_oui)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Confirmer", content=contenu, size_hint=(0.85, 0.4))

        def supprimer(*a):
            del self.data["classes"][nom]
            restantes = sorted(self.data["classes"].keys(), key=lambda x: x.lower())
            self.data["classe_active"] = restantes[0] if restantes else None
            self._sauver_maintenant()
            pop.dismiss()
            self.rafraichir_spinner()
            self.rafraichir()
        b_oui.bind(on_release=supprimer)
        b_non.bind(on_release=pop.dismiss)
        pop.open()

    def clic_date(self, seq_idx, slot_idx):
        donnees = self.donnees_classe()
        if not donnees:
            return self.message("Info", "Crée d'abord une classe.")
        date_actuelle = donnees["sequences"][seq_idx]["dates"][slot_idx]
        init = (datetime.strptime(date_actuelle, "%Y-%m-%d").strftime("%d/%m/%Y")
                if date_actuelle else date.today().strftime("%d/%m/%Y"))

        def valider(txt):
            if txt == "":
                donnees["sequences"][seq_idx]["dates"][slot_idx] = ""
            else:
                iso = parse_date(txt)
                if not iso:
                    self.message("Date invalide", "Format attendu : JJ/MM/AAAA")
                    return False
                donnees["sequences"][seq_idx]["dates"][slot_idx] = iso
            self._sauver_maintenant()
            self.rafraichir()
        self._popup_saisie(f"Date (séquence {seq_idx + 1})",
                           "JJ/MM/AAAA — laisser vide pour effacer",
                           init, "Valider", "#009688", valider, hauteur=0.45)

    def clic_mt(self, nom, seq_idx):
        seq = self.donnees_classe()["sequences"][seq_idx]

        def valider(txt):
            seq["mt"][nom] = txt
            self._sauver_maintenant()
            for d in self.rv.data:
                if d["nom"] == nom:
                    d["mt"][seq_idx] = txt
                    break
            for ligne in self.rv.layout_manager.children:
                if ligne._data and ligne._data["nom"] == nom:
                    ligne.afficher_mt(seq_idx, txt)
        self._popup_saisie(f"MT{seq_idx + 1} — {nom}", "", seq["mt"].get(nom, ""),
                           "Valider", "#009688", valider, hauteur=0.35)


if __name__ == "__main__":
    AppPresences().run()
