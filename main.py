"""
================================================
  APPLICATION DE GESTION DES PRÉSENCES - V16
  - 20 séquences de (4 dates + 1 MT)
  - Barre de défilement horizontale fine
  - Adaptée Android plein écran
  - Mode barré avec trait bleu
  - Sauvegarde / Restauration des données
  - NOUVEAU : présences verrouillées après 1 jour (barrage toujours possible)
  - NOUVEAU : onglet MODIFIER protégé par mot de passe
  - NOUVEAU : envoi des données par mail (manuel + automatique 1x/jour)
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
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex, platform
from kivy.graphics import (PushMatrix, PopMatrix, Rotate, Rectangle,
                           Color as GColor)

import json
import os
import math
import shutil
import ssl
import smtplib
import hashlib
import hmac
import threading
from email.message import EmailMessage
from datetime import date, datetime, timedelta

# ---------- CONFIGURATION ----------
FICHIER = "presences.json"
FICHIER_CONFIG = "config.json"   # mot de passe (haché) + réglages mail

# Une présence reste modifiable le jour J et pendant DELAI_MODIF_JOURS jour(s)
# après. Ensuite elle est verrouillée (seul le barrage reste possible).
# 1 = modifiable aujourd'hui et hier ; 0 = modifiable le jour même seulement.
DELAI_MODIF_JOURS = 1
MDP_MIN = 4

NB_SEQUENCES = 20
SLOTS_PAR_SEQ = 4

LARGEUR_NOM = dp(80)
LARGEUR_CELL = dp(38)
LARGEUR_MT = dp(48)
LARGEUR_SEP = dp(6)
HAUTEUR_ENTETE = dp(42)
HAUTEUR_LIGNE = dp(48)

C_PRESENT = "#81C784"
C_ABSENT = "#E57373"
C_VIDE = "#E0E0E0"
C_PRESENT_VERR = "#A8C5AA"   # présent verrouillé (plus pâle)
C_ABSENT_VERR = "#D4A9A9"    # absent verrouillé (plus pâle)
C_MODIF = "#E65100"          # orange : onglet MODIFIER actif
C_ENTETE = "#455A64"
C_ENTETE_NOM = "#37474F"
C_ENTETE_MT = "#546E7A"

COULEUR_TRAIT = (0.13, 0.59, 0.95, 1)

if platform != "android":
    Window.size = (700, 750)


# ---------- DOSSIER DE SAUVEGARDES ----------
def dossier_sauvegardes():
    """Retourne le chemin du dossier de sauvegardes (créé si absent)."""
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sauvegardes")
    if platform == "android":
        d = "/storage/emulated/0/Download/Presences"
    else:
        d = local
    try:
        os.makedirs(d, exist_ok=True)
        test = os.path.join(d, ".test_ecriture")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return d
    except Exception:
        # Android récent : Download peut être inaccessible -> dossier privé de l'appli
        try:
            os.makedirs(local, exist_ok=True)
        except Exception:
            pass
        return local


def liste_sauvegardes():
    """Retourne la liste des fichiers de sauvegarde (triés du plus récent au plus ancien)."""
    dossier = dossier_sauvegardes()
    if not os.path.exists(dossier):
        return []
    fichiers = [f for f in os.listdir(dossier) if f.endswith(".json")]
    fichiers.sort(reverse=True)
    return fichiers


# ---------- WIDGET : case barrée ----------
class CellButton(Button):
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
        while len(c["sequences"]) < NB_SEQUENCES:
            c["sequences"].append({
                "dates": [""] * SLOTS_PAR_SEQ,
                "presences": {},
                "barres": {},
                "mt": {}
            })
        for seq in c["sequences"]:
            seq.setdefault("mt", {})
            seq.setdefault("barres", {})
            seq.setdefault("presences", {})
            seq.setdefault("dates", [""] * SLOTS_PAR_SEQ)
        return c

    nouveau = structure_vide()
    nouveau["eleves"] = c.get("eleves", [])
    anciennes_dates = c.get("dates", [])
    anciennes_pres = c.get("presences", [])
    if isinstance(anciennes_pres, dict):
        anciennes_pres = anciennes_pres or {}
    else:
        anciennes_pres = {}

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


# ---------- VERROUILLAGE DES PRÉSENCES ----------
def est_verrouille(iso, aujourdhui=None):
    """True si la date iso (AAAA-MM-JJ) est trop ancienne pour modifier les présences."""
    if not iso:
        return False
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except Exception:
        return False
    aujourdhui = aujourdhui or date.today()
    return (aujourdhui - d).days > DELAI_MODIF_JOURS


# ---------- CONFIG : MOT DE PASSE + MAIL ----------
CONFIG_DEFAUT = {
    "mdp_sel": "",
    "mdp_hash": "",
    "smtp_serveur": "smtp.gmail.com",
    "smtp_port": 465,
    "expediteur": "",
    "mdp_app": "",
    "destinataire": "",
    "envoi_auto": True,
    "dernier_envoi": "",
}


def charger_config():
    cfg = dict(CONFIG_DEFAUT)
    if os.path.exists(FICHIER_CONFIG):
        try:
            with open(FICHIER_CONFIG, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def sauver_config(cfg):
    with open(FICHIER_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _hacher(mdp, sel_hex):
    return hashlib.pbkdf2_hmac("sha256", mdp.encode("utf-8"),
                               bytes.fromhex(sel_hex), 100000).hex()


def definir_mdp(cfg, mdp):
    sel = os.urandom(16).hex()
    cfg["mdp_sel"] = sel
    cfg["mdp_hash"] = _hacher(mdp, sel)


def verifier_mdp(cfg, mdp):
    if not cfg.get("mdp_hash") or not cfg.get("mdp_sel"):
        return False
    return hmac.compare_digest(cfg["mdp_hash"], _hacher(mdp, cfg["mdp_sel"]))


# ---------- MAIL ----------
def mail_configure(cfg):
    return bool(cfg.get("expediteur") and cfg.get("mdp_app") and cfg.get("destinataire"))


def construire_corps_mail(data, aujourdhui=None):
    """Résumé texte des séances d'hier et d'aujourd'hui."""
    aujourdhui = aujourdhui or date.today()
    isos = [(aujourdhui - timedelta(days=1)).strftime("%Y-%m-%d"),
            aujourdhui.strftime("%Y-%m-%d")]
    lignes = [f"Rapport de présences - envoyé le {aujourdhui.strftime('%d/%m/%Y')}", ""]
    trouve = False
    for iso in isos:
        for nom_c in sorted(data.get("classes", {}), key=lambda x: x.lower()):
            c = data["classes"][nom_c]
            for s_idx, seq in enumerate(c["sequences"]):
                for k, d in enumerate(seq["dates"]):
                    if d != iso:
                        continue
                    trouve = True
                    presents, absents, vides = [], [], []
                    for el in c["eleves"]:
                        slots = seq["presences"].get(el, [])
                        v = slots[k] if k < len(slots) else ""
                        if v == "P":
                            presents.append(el)
                        elif v == "A":
                            absents.append(el)
                        else:
                            vides.append(el)
                    jour = datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
                    lignes.append(f"{jour} - {nom_c} (séquence {s_idx + 1}, colonne {k + 1})")
                    lignes.append(f"  Présents ({len(presents)}) : {', '.join(presents) or '-'}")
                    lignes.append(f"  Absents ({len(absents)}) : {', '.join(absents) or '-'}")
                    if vides:
                        lignes.append(f"  Non saisis ({len(vides)}) : {', '.join(vides)}")
                    lignes.append("")
    if not trouve:
        lignes.append("Aucune séance datée d'hier ou d'aujourd'hui.")
        lignes.append("")
    lignes.append("La sauvegarde complète (JSON) est en pièce jointe.")
    return "\n".join(lignes)


def contexte_ssl():
    # Sur Android, le magasin de certificats système n'est pas lisible par Python :
    # on utilise certifi s'il est présent.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def envoyer_mail_smtp(cfg, sujet, corps, nom_pj, octets_pj):
    if not mail_configure(cfg):
        raise ValueError("Réglages mail incomplets.")
    msg = EmailMessage()
    msg["From"] = cfg["expediteur"]
    msg["To"] = cfg["destinataire"]
    msg["Subject"] = sujet
    msg.set_content(corps)
    msg.add_attachment(octets_pj, maintype="application", subtype="json",
                       filename=nom_pj)
    serveur = cfg.get("smtp_serveur") or "smtp.gmail.com"
    port = int(cfg.get("smtp_port") or 465)
    mdp = cfg["mdp_app"].replace(" ", "")
    ctx = contexte_ssl()
    if port == 465:
        with smtplib.SMTP_SSL(serveur, port, context=ctx, timeout=30) as s:
            s.login(cfg["expediteur"], mdp)
            s.send_message(msg)
    else:
        with smtplib.SMTP(serveur, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(cfg["expediteur"], mdp)
            s.send_message(msg)


# ---------- APPLICATION ----------
class AppPresences(App):

    def build(self):
        self.title = "Présences"
        self.data = charger()
        self.cfg = charger_config()
        self.mode_barre = False
        self.admin = False            # True = onglet MODIFIER déverrouillé
        self.envoi_en_cours = False
        self.statut_mail = ""

        racine = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(4))

        # ===== Titre =====
        racine.add_widget(Label(
            text="GESTION DES PRÉSENCES",
            size_hint_y=None, height=dp(32),
            bold=True, font_size=dp(18)
        ))

        # ===== Onglets =====
        ligne_onglets = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.onglet_pres = Button(text="PRÉSENCES", bold=True, font_size=dp(13),
                                  color=(1, 1, 1, 1))
        self.onglet_modif = Button(text="MODIFIER (code)", bold=True, font_size=dp(13),
                                   color=(1, 1, 1, 1))
        self.onglet_pres.bind(on_press=self.aller_presences)
        self.onglet_modif.bind(on_press=self.aller_modifier)
        ligne_onglets.add_widget(self.onglet_pres)
        ligne_onglets.add_widget(self.onglet_modif)
        racine.add_widget(ligne_onglets)

        # ===== Sélecteur de classe =====
        ligne_classe = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        ligne_classe.add_widget(Label(text="Classe :", size_hint_x=0.22))
        self.spinner_classe = Spinner(
            text="-- Aucune --", values=[], size_hint_x=0.78,
            background_color=get_color_from_hex("#607D8B")
        )
        self.spinner_classe.bind(text=self.changer_classe)
        ligne_classe.add_widget(self.spinner_classe)
        racine.add_widget(ligne_classe)

        # ===== Boutons classes =====
        ligne_gestion = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        b_new = Button(text="+ Classe",
                       background_color=get_color_from_hex("#3F51B5"),
                       color=(1, 1, 1, 1), font_size=dp(13))
        b_new.bind(on_press=self.nouvelle_classe)
        b_ren = Button(text="Renommer",
                       background_color=get_color_from_hex("#795548"),
                       color=(1, 1, 1, 1), font_size=dp(13))
        b_ren.bind(on_press=self.renommer_classe)
        b_sup = Button(text="Suppr. classe",
                       background_color=get_color_from_hex("#B71C1C"),
                       color=(1, 1, 1, 1), font_size=dp(13))
        b_sup.bind(on_press=self.supprimer_classe)
        ligne_gestion.add_widget(b_new)
        ligne_gestion.add_widget(b_ren)
        ligne_gestion.add_widget(b_sup)
        racine.add_widget(ligne_gestion)

        # ===== Mode barré + Sauvegarde =====
        ligne_mode = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.btn_mode = Button(
            text="MODE NORMAL",
            background_color=get_color_from_hex("#9E9E9E"),
            color=(1, 1, 1, 1), bold=True, font_size=dp(13)
        )
        self.btn_mode.bind(on_press=self.toggle_mode)
        btn_sauvegarde = Button(
            text="Sauvegarde",
            background_color=get_color_from_hex("#00897B"),
            color=(1, 1, 1, 1), bold=True, font_size=dp(13),
            size_hint_x=0.3
        )
        btn_sauvegarde.bind(on_press=self.menu_sauvegarde)
        btn_mail = Button(
            text="Mail",
            background_color=get_color_from_hex("#5E35B1"),
            color=(1, 1, 1, 1), bold=True, font_size=dp(13),
            size_hint_x=0.2
        )
        btn_mail.bind(on_press=self.menu_mail)
        ligne_mode.add_widget(self.btn_mode)
        ligne_mode.add_widget(btn_sauvegarde)
        ligne_mode.add_widget(btn_mail)
        racine.add_widget(ligne_mode)

        # ===== Info =====
        self.lbl_info = Label(
            text="", size_hint_y=None, height=dp(22),
            font_size=dp(12), color=(0.3, 0.3, 0.3, 1)
        )
        racine.add_widget(self.lbl_info)

        # ===== Ajouter élève =====
        ligne_ajout = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.champ_nom = TextInput(hint_text="Nom élève", multiline=False,
                                   size_hint_x=0.7)
        b_add_el = Button(text="+ Élève", size_hint_x=0.3,
                          background_color=get_color_from_hex("#2196F3"),
                          color=(1, 1, 1, 1), font_size=dp(13))
        b_add_el.bind(on_press=self.ajouter_eleve)
        ligne_ajout.add_widget(self.champ_nom)
        ligne_ajout.add_widget(b_add_el)
        racine.add_widget(ligne_ajout)

        # ===== Légende =====
        legende = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(4))
        legende.add_widget(Label(text="P=Présent", size_hint_x=0.2,
                                 font_size=dp(11),
                                 color=get_color_from_hex(C_PRESENT), bold=True))
        legende.add_widget(Label(text="A=Absent", size_hint_x=0.2,
                                 font_size=dp(11),
                                 color=get_color_from_hex(C_ABSENT), bold=True))
        legende.add_widget(Label(text="Barré=bleu", size_hint_x=0.2,
                                 font_size=dp(11),
                                 color=(0.13, 0.59, 0.95, 1), bold=True))
        legende.add_widget(Label(text="Pâle=verrouillé", size_hint_x=0.25,
                                 font_size=dp(11), color=(0.4, 0.4, 0.4, 1)))
        legende.add_widget(Label(text="MT=libre", size_hint_x=0.15,
                                 font_size=dp(11), color=(0.4, 0.4, 0.4, 1)))
        racine.add_widget(legende)

        # ===== Zone du tableau =====
        self.scroll = ScrollView(
            do_scroll_x=True, do_scroll_y=True,
            scroll_type=['bars', 'content'],
            bar_width=dp(10),
            bar_color=(0.4, 0.5, 0.6, 1),
            bar_inactive_color=(0.88, 0.88, 0.88, 1)
        )
        self.tableau = BoxLayout(
            orientation="vertical", size_hint=(None, None), spacing=dp(1)
        )
        self.tableau.bind(minimum_width=self.tableau.setter("width"))
        self.tableau.bind(minimum_height=self.tableau.setter("height"))
        self.scroll.add_widget(self.tableau)
        racine.add_widget(self.scroll)

        self.rafraichir_spinner()
        self.maj_onglets()
        self.rafraichir()

        return racine

    # ============================================================
    #            DÉMARRAGE / REPRISE : ENVOI AUTO 1x/JOUR
    # ============================================================
    def on_start(self):
        Clock.schedule_once(self.envoi_auto_si_besoin, 2)

    def on_resume(self):
        Clock.schedule_once(self.envoi_auto_si_besoin, 2)

    def envoi_auto_si_besoin(self, *args):
        cfg = self.cfg
        if not cfg.get("envoi_auto") or not mail_configure(cfg):
            return
        if cfg.get("dernier_envoi") == date.today().strftime("%Y-%m-%d"):
            return
        if not self.data.get("classes"):
            return
        self.envoyer_mail(auto=True)

    # ============================================================
    #                 ONGLETS + MOT DE PASSE
    # ============================================================
    def maj_onglets(self):
        if self.admin:
            self.onglet_pres.background_color = get_color_from_hex("#9E9E9E")
            self.onglet_modif.background_color = get_color_from_hex(C_MODIF)
        else:
            self.onglet_pres.background_color = get_color_from_hex("#1565C0")
            self.onglet_modif.background_color = get_color_from_hex("#9E9E9E")

    def aller_presences(self, *args):
        if self.admin:
            self.admin = False
            self.maj_onglets()
            self.rafraichir()

    def aller_modifier(self, *args):
        if self.admin:
            return
        if not self.cfg.get("mdp_hash"):
            self.popup_nouveau_mdp("Créer le mot de passe", deverrouiller=True)
        else:
            self.popup_demander_mdp()

    def bloque_sans_admin(self, action):
        """True (et message) si l'action exige l'onglet MODIFIER."""
        if self.admin:
            return False
        self.message("Onglet MODIFIER",
                     f"{action}\nest réservé à l'onglet\nMODIFIER (mot de passe).")
        return True

    def popup_demander_mdp(self):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        contenu.add_widget(Label(text="Mot de passe :", size_hint_y=None, height=dp(26)))
        champ = TextInput(password=True, multiline=False,
                          size_hint_y=None, height=dp(42))
        contenu.add_widget(champ)
        lbl_err = Label(text="", size_hint_y=None, height=dp(24),
                        color=get_color_from_hex("#F44336"), font_size=dp(12))
        contenu.add_widget(lbl_err)
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_ok = Button(text="Valider", background_color=get_color_from_hex(C_MODIF),
                      color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Onglet MODIFIER", content=contenu, size_hint=(0.85, 0.42))

        def valider(*a):
            if verifier_mdp(self.cfg, champ.text):
                pop.dismiss()
                self.admin = True
                self.maj_onglets()
                self.rafraichir()
            else:
                champ.text = ""
                lbl_err.text = "Mot de passe incorrect."

        b_ok.bind(on_press=valider)
        champ.bind(on_text_validate=valider)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    def popup_nouveau_mdp(self, titre, deverrouiller=False):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        contenu.add_widget(Label(
            text=f"Choisis un mot de passe ({MDP_MIN} caractères min.)",
            size_hint_y=None, height=dp(26), font_size=dp(12)))
        champ1 = TextInput(password=True, multiline=False, hint_text="Mot de passe",
                           size_hint_y=None, height=dp(42))
        champ2 = TextInput(password=True, multiline=False, hint_text="Confirmer",
                           size_hint_y=None, height=dp(42))
        contenu.add_widget(champ1)
        contenu.add_widget(champ2)
        lbl_err = Label(text="", size_hint_y=None, height=dp(24),
                        color=get_color_from_hex("#F44336"), font_size=dp(12))
        contenu.add_widget(lbl_err)
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_ok = Button(text="Enregistrer", background_color=get_color_from_hex(C_MODIF),
                      color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title=titre, content=contenu, size_hint=(0.85, 0.55))

        def valider(*a):
            if len(champ1.text) < MDP_MIN:
                lbl_err.text = f"Minimum {MDP_MIN} caractères."
                return
            if champ1.text != champ2.text:
                lbl_err.text = "Les deux mots de passe diffèrent."
                return
            definir_mdp(self.cfg, champ1.text)
            sauver_config(self.cfg)
            pop.dismiss()
            if deverrouiller:
                self.admin = True
                self.maj_onglets()
                self.rafraichir()
            else:
                self.message("Mot de passe", "Mot de passe modifié.")

        b_ok.bind(on_press=valider)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    # ============================================================
    #                          MAIL
    # ============================================================
    def menu_mail(self, *args):
        cfg = self.cfg
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        if mail_configure(cfg):
            etat = (f"Destinataire : {cfg['destinataire']}\n"
                    f"Envoi auto (1x/jour) : {'OUI' if cfg.get('envoi_auto') else 'NON'}\n"
                    f"Dernier envoi : {cfg.get('dernier_envoi') or 'jamais'}")
        else:
            etat = ("Mail non configuré.\n"
                    "Onglet MODIFIER, puis Mail > Réglages.")
        contenu.add_widget(Label(text=etat, size_hint_y=None, height=dp(70),
                                 font_size=dp(12)))
        b_env = Button(text="Envoyer maintenant", size_hint_y=None, height=dp(48),
                       background_color=get_color_from_hex("#5E35B1"),
                       color=(1, 1, 1, 1), bold=True)
        contenu.add_widget(b_env)
        b_reg = b_mdp = None
        if self.admin:
            b_reg = Button(text="Réglages mail", size_hint_y=None, height=dp(44),
                           background_color=get_color_from_hex("#455A64"),
                           color=(1, 1, 1, 1))
            b_mdp = Button(text="Changer le mot de passe", size_hint_y=None,
                           height=dp(44),
                           background_color=get_color_from_hex("#455A64"),
                           color=(1, 1, 1, 1))
            contenu.add_widget(b_reg)
            contenu.add_widget(b_mdp)
        contenu.add_widget(Label())
        b_fermer = Button(text="Fermer", size_hint_y=None, height=dp(45))
        contenu.add_widget(b_fermer)
        pop = Popup(title="Envoi par mail", content=contenu, size_hint=(0.9, 0.7))

        def envoyer(*a):
            pop.dismiss()
            self.envoyer_mail(auto=False)

        def reglages(*a):
            pop.dismiss()
            self.reglages_mail()

        def changer(*a):
            pop.dismiss()
            self.popup_nouveau_mdp("Changer le mot de passe")

        b_env.bind(on_press=envoyer)
        if b_reg:
            b_reg.bind(on_press=reglages)
            b_mdp.bind(on_press=changer)
        b_fermer.bind(on_press=pop.dismiss)
        pop.open()

    def reglages_mail(self):
        if self.bloque_sans_admin("Les réglages mail"):
            return
        cfg = self.cfg
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        contenu.add_widget(Label(
            text="Gmail : crée un « mot de passe d'application »\n"
                 "(compte Google > Sécurité > validation en 2 étapes).",
            size_hint_y=None, height=dp(44), font_size=dp(11)))
        f_exp = TextInput(text=cfg.get("expediteur", ""), multiline=False,
                          hint_text="Adresse expéditeur (Gmail)",
                          size_hint_y=None, height=dp(40))
        f_mdp = TextInput(text="", multiline=False, password=True,
                          hint_text=("Mot de passe d'application (inchangé si vide)"
                                     if cfg.get("mdp_app")
                                     else "Mot de passe d'application"),
                          size_hint_y=None, height=dp(40))
        f_dest = TextInput(text=cfg.get("destinataire", ""), multiline=False,
                           hint_text="Adresse destinataire",
                           size_hint_y=None, height=dp(40))
        for w in (f_exp, f_mdp, f_dest):
            contenu.add_widget(w)
        etat_auto = [bool(cfg.get("envoi_auto", True))]
        b_auto = Button(text="", size_hint_y=None, height=dp(40),
                        background_color=get_color_from_hex("#607D8B"),
                        color=(1, 1, 1, 1))

        def maj_auto():
            b_auto.text = "Envoi auto 1x/jour : " + ("OUI" if etat_auto[0] else "NON")

        def basculer(*a):
            etat_auto[0] = not etat_auto[0]
            maj_auto()

        maj_auto()
        b_auto.bind(on_press=basculer)
        contenu.add_widget(b_auto)
        contenu.add_widget(Label())
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_ok = Button(text="Enregistrer", background_color=get_color_from_hex("#009688"),
                      color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_ok)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)
        pop = Popup(title="Réglages mail", content=contenu, size_hint=(0.95, 0.85))

        def enregistrer(*a):
            exp = f_exp.text.strip()
            dest = f_dest.text.strip()
            if "@" not in exp or "@" not in dest:
                self.message("Erreur", "Adresses mail invalides.")
                return
            cfg["expediteur"] = exp
            cfg["destinataire"] = dest
            if f_mdp.text.strip():
                cfg["mdp_app"] = f_mdp.text.strip()
            cfg["envoi_auto"] = etat_auto[0]
            if not cfg.get("mdp_app"):
                self.message("Erreur", "Mot de passe d'application manquant.")
                return
            sauver_config(cfg)
            pop.dismiss()
            self.message("Mail", "Réglages enregistrés.\nTeste avec « Envoyer maintenant ».")

        b_ok.bind(on_press=enregistrer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    def envoyer_mail(self, auto=False):
        if self.envoi_en_cours:
            if not auto:
                self.message("Mail", "Un envoi est déjà en cours.")
            return
        if not mail_configure(self.cfg):
            if not auto:
                self.message("Mail non configuré",
                             "Onglet MODIFIER, puis\nMail > Réglages mail.")
            return
        self.envoi_en_cours = True
        cfg = dict(self.cfg)
        copie = json.loads(json.dumps(self.data))
        aujourdhui = date.today()
        iso = aujourdhui.strftime("%Y-%m-%d")
        sujet = f"Présences {aujourdhui.strftime('%d/%m/%Y')}"
        corps = construire_corps_mail(copie, aujourdhui)
        octets = json.dumps(copie, ensure_ascii=False, indent=2).encode("utf-8")
        nom_pj = f"presences_{iso}.json"

        def travail():
            ok, err = True, ""
            try:
                envoyer_mail_smtp(cfg, sujet, corps, nom_pj, octets)
            except smtplib.SMTPAuthenticationError:
                ok = False
                err = ("Identifiants refusés.\nUtilise un mot de passe\n"
                       "d'application Gmail (pas ton mot de passe habituel).")
            except (OSError, smtplib.SMTPException) as e:
                ok = False
                err = f"Connexion impossible (internet ?)\n{e}"
            except Exception as e:
                ok = False
                err = str(e)
            Clock.schedule_once(lambda dt: self.fin_envoi(ok, err, auto, iso), 0)

        threading.Thread(target=travail, daemon=True).start()
        if not auto:
            self.statut_mail = "envoi du mail..."
            self.rafraichir()

    def fin_envoi(self, ok, err, auto, iso):
        self.envoi_en_cours = False
        heure = datetime.now().strftime("%H:%M")
        if ok:
            self.cfg["dernier_envoi"] = iso
            sauver_config(self.cfg)
            self.statut_mail = f"mail envoyé {heure}"
            if not auto:
                self.message("Mail envoyé", f"Envoyé à :\n{self.cfg['destinataire']}")
        else:
            self.statut_mail = "mail : échec"
            if not auto:
                self.message("Échec de l'envoi", err)
        self.rafraichir()

    # ============================================================
    #                    GESTION SAUVEGARDES
    # ============================================================
    def menu_sauvegarde(self, *args):
        """Ouvre le menu de gestion des sauvegardes."""
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        # Bouton pour créer une nouvelle sauvegarde
        b_sauver = Button(
            text="Créer une sauvegarde maintenant",
            size_hint_y=None, height=dp(50),
            background_color=get_color_from_hex("#4CAF50"),
            color=(1, 1, 1, 1), bold=True, font_size=dp(14)
        )
        contenu.add_widget(b_sauver)

        # Chemin du dossier
        dossier = dossier_sauvegardes()
        info = Label(
            text=f"Dossier : {dossier}",
            size_hint_y=None, height=dp(40),
            font_size=dp(10), color=(0.4, 0.4, 0.4, 1)
        )
        contenu.add_widget(info)

        # Titre liste
        contenu.add_widget(Label(
            text="Sauvegardes existantes (cliquez pour restaurer) :",
            size_hint_y=None, height=dp(28),
            bold=True, font_size=dp(12)
        ))

        # Liste des sauvegardes
        scroll = ScrollView()
        liste = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
        liste.bind(minimum_height=liste.setter("height"))

        fichiers = liste_sauvegardes()
        if not fichiers:
            liste.add_widget(Label(
                text="Aucune sauvegarde pour l'instant.",
                size_hint_y=None, height=dp(40),
                italic=True, color=(0.5, 0.5, 0.5, 1)
            ))
        else:
            for f in fichiers:
                # Extraire la date du nom de fichier
                nom_affiche = f.replace("presences_", "").replace(".json", "")
                btn = Button(
                    text=nom_affiche,
                    size_hint_y=None, height=dp(44),
                    background_color=get_color_from_hex("#546E7A"),
                    color=(1, 1, 1, 1), font_size=dp(12)
                )
                btn.bind(on_press=lambda b, nom=f: self.restaurer_sauvegarde(nom))
                liste.add_widget(btn)

        scroll.add_widget(liste)
        contenu.add_widget(scroll)

        # Bouton fermer
        b_fermer = Button(text="Fermer", size_hint_y=None, height=dp(45))
        contenu.add_widget(b_fermer)

        pop = Popup(
            title="Sauvegarde / Restauration",
            content=contenu,
            size_hint=(0.92, 0.85)
        )

        def creer_sauvegarde(*a):
            self.creer_sauvegarde()
            pop.dismiss()

        b_sauver.bind(on_press=creer_sauvegarde)
        b_fermer.bind(on_press=pop.dismiss)
        pop.open()

    def creer_sauvegarde(self):
        """Crée un fichier de sauvegarde horodaté."""
        # D'abord, s'assurer que les données actuelles sont bien sauvegardées
        sauver(self.data)

        # Créer le nom du fichier
        nom = "presences_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".json"
        chemin = os.path.join(dossier_sauvegardes(), nom)

        try:
            # Copier le fichier presences.json vers le dossier de sauvegardes
            if os.path.exists(FICHIER):
                shutil.copy2(FICHIER, chemin)
            else:
                # Si presences.json n'existe pas, écrire directement les données
                with open(chemin, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)

            self.message(
                "Sauvegarde créée",
                f"Fichier créé :\n{nom}\n\n"
                f"Dossier :\n{dossier_sauvegardes()}\n\n"
                f"Sur PC, tu peux copier ce fichier\n"
                f"via USB ou Google Drive."
            )
        except Exception as e:
            self.message("Erreur", f"Impossible de créer la sauvegarde :\n{e}")

    def restaurer_sauvegarde(self, nom_fichier):
        """Demande confirmation puis restaure les données."""
        if self.bloque_sans_admin("La restauration d'une sauvegarde"):
            return
        chemin = os.path.join(dossier_sauvegardes(), nom_fichier)

        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        contenu.add_widget(Label(
            text=f"Restaurer la sauvegarde ?\n\n{nom_fichier}\n\n"
                 f"ATTENTION : Les données actuelles\n"
                 f"seront remplacées !"
        ))
        ligne = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        b_oui = Button(text="Oui, restaurer",
                       background_color=get_color_from_hex("#F44336"),
                       color=(1, 1, 1, 1))
        b_non = Button(text="Annuler")
        ligne.add_widget(b_oui)
        ligne.add_widget(b_non)
        contenu.add_widget(ligne)

        pop = Popup(title="Confirmer la restauration",
                    content=contenu, size_hint=(0.9, 0.5))

        def restaurer(*a):
            try:
                with open(chemin, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Migration si nécessaire
                if "classes" in data:
                    for nom_c, c in list(data["classes"].items()):
                        data["classes"][nom_c] = migrer_classe(c)

                # Sauvegarder les données restaurées
                self.data = data
                sauver(self.data)

                pop.dismiss()
                self.rafraichir_spinner()
                self.rafraichir()

                self.message(
                    "Restauration réussie",
                    f"Les données ont été restaurées depuis :\n{nom_fichier}"
                )
            except Exception as e:
                pop.dismiss()
                self.message("Erreur", f"Impossible de restaurer :\n{e}")

        b_oui.bind(on_press=restaurer)
        b_non.bind(on_press=pop.dismiss)
        pop.open()

    # ============================================================
    #                    MODE BARRÉ
    # ============================================================
    def toggle_mode(self, *args):
        self.mode_barre = not self.mode_barre
        if self.mode_barre:
            self.btn_mode.text = "MODE BARRÉ"
            self.btn_mode.background_color = get_color_from_hex("#1976D2")
        else:
            self.btn_mode.text = "MODE NORMAL"
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
        if self.bloque_sans_admin("La suppression d'une classe"):
            return
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

        if est_verrouille(date_actuelle) and not self.admin:
            self.message("Date verrouillée",
                         f"Cette date a plus de {DELAI_MODIF_JOURS} jour(s).\n"
                         "Pour la changer, utilise\nl'onglet MODIFIER.")
            return

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
        self.lbl_info.color = (0.9, 0.32, 0.0, 1) if self.admin else (0.3, 0.3, 0.3, 1)
        suffixe = f" — {self.statut_mail}" if self.statut_mail else ""

        if not nom_classe:
            self.lbl_info.text = "Aucune classe — crée-en une."
            self.tableau.add_widget(Label(
                text="Crée d'abord une classe.",
                size_hint=(None, None), size=(dp(250), dp(50))
            ))
            return

        eleves = donnees["eleves"]
        sequences = donnees["sequences"]
        prefixe = "MODIFICATION — " if self.admin else ""
        self.lbl_info.text = (f"{prefixe}« {nom_classe} » — {len(eleves)} élève(s)"
                              f"{suffixe}")

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

                    verr = est_verrouille(seq["dates"][k_idx])
                    if val == "P":
                        couleur = C_PRESENT_VERR if verr else C_PRESENT
                        texte = "P"
                        txt_c = (0.2, 0.2, 0.2, 1) if verr else (1, 1, 1, 1)
                    elif val == "A":
                        couleur = C_ABSENT_VERR if verr else C_ABSENT
                        texte = "A"
                        txt_c = (0.2, 0.2, 0.2, 1) if verr else (1, 1, 1, 1)
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
            if est_verrouille(seq["dates"][slot_idx]) and not self.admin:
                self.message(
                    "Présence verrouillée",
                    f"Cette séance date de plus de {DELAI_MODIF_JOURS} jour(s).\n"
                    "Tu peux la barrer (MODE BARRÉ)\n"
                    "ou utiliser l'onglet MODIFIER.")
                return
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
        if self.bloque_sans_admin("La suppression d'un élève"):
            return
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
        pop = Popup(title=titre, content=contenu, size_hint=(0.85, 0.5))
        btn.bind(on_press=pop.dismiss)
        pop.open()


if __name__ == "__main__":
    AppPresences().run()
