"""API Flask de "ma-voix" : enregistre ta voix et transforme du texte en message vocal.

Securite (voir SECURITE.md) : application locale, sans compte.
Elle n'ecoute que sur 127.0.0.1 et refuse les requetes venant d'autres sites.
Version GPU sur Colab : joignable par un tunnel, chaque requete doit alors porter le jeton secret.
"""

import gc
import hmac
import io
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

import soundfile as sf
from flask import Flask, jsonify, request, send_file
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from moteur import ETAPES_SON, LANGUES, SUR_GPU, Moteur, decouper_texte
from preparation import conseils, mesurer, preparer

DOSSIER = Path(__file__).parent
DOSSIER_VOIX = DOSSIER / "voix"
DOSSIER_SORTIES = DOSSIER / "sorties"
DOSSIER_VOIX.mkdir(exist_ok=True)
DOSSIER_SORTIES.mkdir(exist_ok=True)

FICHIER_VOIX = DOSSIER_VOIX / "ma_voix.wav"
DUREE_MIN_VOIX = 5  # secondes
DUREE_MAX_VOIX = 60  # secondes (la page coupe deja a 30 s)
LONGUEUR_MAX_TEXTE = 2000  # caracteres
MAX_EN_ATTENTE = 3  # messages en file d'attente au maximum
MAX_TACHES_GARDEES = 20  # on oublie les plus anciennes

# Seuls ces noms d'hote sont acceptes (empeche le "DNS rebinding" : un site pirate
# qui ferait pointer son propre nom de domaine vers 127.0.0.1)
HOTES_LOCAUX = {"127.0.0.1:5000", "localhost:5000", "127.0.0.1:5173", "localhost:5173"}
# Les requetes POST doivent porter cet en-tete. Un autre site ouvert dans ton navigateur
# ne peut pas l'ajouter sans autorisation CORS (que ce serveur ne donne jamais).
ENTETE_ANTI_SITES = "X-Ma-Voix"
# Version GPU (Colab) : le serveur est joignable depuis Internet par un tunnel.
# Chaque requete doit alors porter le jeton secret dans cet en-tete (jamais dans l'URL).
ENTETE_JETON = "X-Ma-Voix-Jeton"
FORMAT_JETON = re.compile(r"^[A-Za-z0-9_-]{32,256}$")  # secrets.token_urlsafe(32) = 43 caracteres
FORMAT_HOTE = re.compile(r"^[a-z0-9.-]+(:\d{1,5})?$")

FORMAT_NOM_SORTIE = re.compile(r"^message_\d{8}_\d{6}\.wav$")


def lire_configuration(environ):
    """Lit le mode "a distance" dans les variables d'environnement (voir SECURITE.md, MV-7) :
    - MA_VOIX_HOTES : noms d'hote en plus des hotes locaux, separes par des virgules
      (l'adresse du tunnel, par exemple "abc-def.trycloudflare.com") ;
    - MA_VOIX_JETON : jeton secret exige sur chaque requete.
    Refuse de demarrer si un hote en plus est donne sans jeton solide."""
    hotes = {h.strip().lower() for h in environ.get("MA_VOIX_HOTES", "").split(",") if h.strip()}
    jeton = environ.get("MA_VOIX_JETON") or None
    for hote in hotes:
        if not FORMAT_HOTE.fullmatch(hote):
            raise RuntimeError(f"MA_VOIX_HOTES : nom d'hote invalide : {hote!r}")
    if jeton is not None and not FORMAT_JETON.fullmatch(jeton):
        raise RuntimeError("MA_VOIX_JETON doit faire au moins 32 caracteres (lettres, chiffres, - et _).")
    if hotes and jeton is None:
        raise RuntimeError("MA_VOIX_HOTES rend le serveur joignable de l'exterieur : MA_VOIX_JETON est obligatoire.")
    return HOTES_LOCAUX | hotes, jeton


HOTES_AUTORISES, JETON = lire_configuration(os.environ)

app = Flask(__name__)
# VAL-4 : taille maximale d'une requete. 8 Mo au lieu de 1 Mo, car un echantillon de voix
# de 30 s en WAV pese jusqu'a ~6 Mo (exception notee dans securite.md).
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

moteur = Moteur()

# Les generations en cours ou finies : { id: {...} }
taches = {}
# Les messages qui attendent leur tour
file_attente = queue.Queue()


class DemandeGeneration(BaseModel):
    """Schema strict de POST /api/generer (VAL-1) : tout autre champ est refuse."""

    model_config = ConfigDict(extra="forbid")

    texte: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LONGUEUR_MAX_TEXTE)]
    langue: Literal[tuple(LANGUES)] = "fr"
    expressivite: float = Field(default=0.5, ge=0.25, le=2.0)
    qualite: Literal[tuple(ETAPES_SON)] = "rapide"


def ouvrier():
    """Un seul thread fait TOUT le travail de l'IA : charger le modele, puis generer
    les messages un par un, dans l'ordre. (Avec un nouveau thread par message,
    PyTorch reservait a chaque fois de la memoire en plus : 7 Go au lieu de 4,5 Go.)"""
    moteur.charger()
    if not moteur.pret:
        return
    while True:
        executer_tache(*file_attente.get())


@app.before_request
def refuser_les_autres_sites():
    if request.host not in HOTES_AUTORISES:
        return jsonify(erreur="Hote non autorise."), 403
    # WH-1 : comparaison en temps constant (jamais == pour un secret)
    if JETON is not None and not hmac.compare_digest(
        request.headers.get(ENTETE_JETON, "").encode(), JETON.encode()
    ):
        return jsonify(erreur="Jeton manquant ou invalide."), 403
    if request.method == "POST" and request.headers.get(ENTETE_ANTI_SITES) != "1":
        return jsonify(erreur="Requete refusee."), 403


@app.after_request
def entetes_de_securite(reponse):
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


@app.errorhandler(413)
def trop_gros(_erreur):
    return jsonify(erreur="Fichier trop gros (8 Mo maximum)."), 413


@app.get("/api/statut")
def statut():
    return jsonify(
        modele_pret=moteur.pret,
        # Message generique (SEC-5) : le detail de l'erreur est dans le terminal du backend
        erreur="Le modele n'a pas pu se charger (details dans le terminal du backend)."
        if moteur.erreur else None,
        voix_enregistree=FICHIER_VOIX.exists(),
        langues=LANGUES,
        gpu=SUR_GPU,
    )


@app.post("/api/voix")
def enregistrer_voix():
    fichier = request.files.get("audio")
    if fichier is None:
        return jsonify(erreur="Aucun fichier audio recu.", champs=["audio"]), 400

    donnees = fichier.read()
    try:
        if sf.info(io.BytesIO(donnees)).format != "WAV":
            raise ValueError("pas un WAV")
        audio, frequence = sf.read(io.BytesIO(donnees), dtype="float32")
    except Exception:
        return jsonify(erreur="Fichier audio illisible (WAV attendu).", champs=["audio"]), 400

    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # stereo -> mono
    duree = len(audio) / frequence
    if not DUREE_MIN_VOIX <= duree <= DUREE_MAX_VOIX:
        return jsonify(
            erreur=f"L'enregistrement doit durer entre {DUREE_MIN_VOIX} et {DUREE_MAX_VOIX} secondes.",
            champs=["audio"],
        ), 400

    # Controle de qualite de l'enregistrement d'origine, puis nettoyage
    # (silences retires, souffle reduit, volume corrige) : voir preparation.py
    mesures = mesurer(audio, frequence)
    propre = preparer(audio, frequence)
    duree_propre = len(propre) / frequence
    if duree_propre < DUREE_MIN_VOIX:
        return jsonify(
            erreur="Pas assez de parole audible dans l'enregistrement.",
            champs=["audio"],
            conseils=conseils(mesures),
        ), 400

    sf.write(FICHIER_VOIX, propre, frequence)
    moteur.voix_chargee = None  # la prochaine generation analysera la nouvelle voix
    return jsonify(
        message="Voix enregistree et nettoyee !",
        duree=round(duree_propre, 1),
        mesures=mesures,
        conseils=conseils(mesures),
    )


@app.get("/api/voix")
def ecouter_voix():
    if not FICHIER_VOIX.exists():
        return jsonify(erreur="Aucune voix enregistree."), 404
    return send_file(FICHIER_VOIX, mimetype="audio/wav", max_age=0)


@app.post("/api/generer")
def generer():
    """Lance la generation en arriere-plan et renvoie tout de suite un numero de tache."""
    try:
        demande = DemandeGeneration.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        champs = sorted({".".join(str(x) for x in err["loc"]) or "corps" for err in e.errors()})
        return jsonify(erreur=f"Donnees invalides : {', '.join(champs)}.", champs=champs), 400

    if not moteur.pret:
        return jsonify(erreur="Le modele est encore en train de charger, patiente un peu."), 503
    if not FICHIER_VOIX.exists():
        return jsonify(erreur="Enregistre d'abord ta voix."), 400
    if file_attente.qsize() >= MAX_EN_ATTENTE:
        return jsonify(erreur="Trop de messages en attente, patiente un peu."), 429

    identifiant = uuid.uuid4().hex[:8]
    morceaux = decouper_texte(demande.texte)
    oublier_vieilles_taches()
    taches[identifiant] = {"total": len(morceaux), "audios": [], "fini": False, "erreur": None, "fichier": None}
    file_attente.put((identifiant, morceaux, demande.langue, demande.expressivite, demande.qualite))
    return jsonify(id=identifiant, total=len(morceaux))


def oublier_vieilles_taches():
    """Garde seulement les MAX_TACHES_GARDEES dernieres taches finies en memoire."""
    finies = [cle for cle, tache in taches.items() if tache["fini"]]
    for cle in finies[: max(0, len(finies) - MAX_TACHES_GARDEES + 1)]:
        del taches[cle]


def executer_tache(identifiant, morceaux, langue, expressivite, qualite):
    tache = taches[identifiant]
    debut = time.time()
    try:
        for audio in moteur.generer_morceaux(
            morceaux, langue, str(FICHIER_VOIX), expressivite, qualite
        ):
            tache["audios"].append(audio)
            print(f"[tache {identifiant}] morceau {len(tache['audios'])}/{tache['total']} "
                  f"pret apres {time.time() - debut:.0f} s")

        complet = moteur.assembler(tache["audios"])
        nom = time.strftime("message_%Y%m%d_%H%M%S.wav")
        sf.write(DOSSIER_SORTIES / nom, complet, moteur.frequence)
        tache["fichier"] = nom
        print(f"[tache {identifiant}] fini : {len(complet) / moteur.frequence:.1f} s d'audio "
              f"en {time.time() - debut:.0f} s")
    except Exception as e:
        tache["erreur"] = "La generation a echoue (details dans le terminal du backend)."
        print(f"[tache {identifiant}] erreur :", repr(e))
    finally:
        tache["fini"] = True
        gc.collect()  # libere la memoire de calcul entre deux messages


@app.get("/api/taches/<identifiant>")
def etat_tache(identifiant):
    tache = taches.get(identifiant)
    if tache is None:
        return jsonify(erreur="Tache inconnue."), 404
    return jsonify(
        total=tache["total"],
        prets=len(tache["audios"]),
        fini=tache["fini"],
        erreur=tache["erreur"],
        fichier=tache["fichier"],
    )


@app.get("/api/taches/<identifiant>/morceaux/<int:numero>")
def morceau_tache(identifiant, numero):
    """Renvoie un seul morceau (une phrase) pour l'ecouter sans attendre la fin."""
    tache = taches.get(identifiant)
    if tache is None or numero >= len(tache["audios"]):
        return jsonify(erreur="Morceau pas encore pret."), 404
    tampon = io.BytesIO()
    sf.write(tampon, tache["audios"][numero], moteur.frequence, format="WAV")
    tampon.seek(0)
    return send_file(tampon, mimetype="audio/wav")


@app.get("/api/sorties/<nom>")
def fichier_final(nom):
    # Allowlist du format de nom : impossible de demander un autre fichier du PC
    if not FORMAT_NOM_SORTIE.fullmatch(nom) or not (DOSSIER_SORTIES / nom).exists():
        return jsonify(erreur="Fichier introuvable."), 404
    return send_file(DOSSIER_SORTIES / nom, mimetype="audio/wav", download_name=nom)


if __name__ == "__main__":
    # Le modele met du temps a charger : on demarre l'ouvrier en arriere-plan
    # pour que le serveur reponde tout de suite.
    threading.Thread(target=ouvrier, daemon=True).start()
    if JETON is not None:
        print(f"[app] Jeton secret exige. Hotes en plus : {sorted(HOTES_AUTORISES - HOTES_LOCAUX) or 'aucun'}")
    # AUTH-8 : mode debug seulement si on le demande (MA_VOIX_DEBUG=1).
    # 127.0.0.1 : le serveur n'est joignable que depuis cette machine, jamais depuis le reseau
    # (sur Colab, seul le tunnel, lance sur la meme machine, peut l'atteindre).
    # use_reloader=False : sinon Flask chargerait le modele deux fois.
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("MA_VOIX_DEBUG") == "1", use_reloader=False)
