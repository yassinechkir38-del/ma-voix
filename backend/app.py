"""API Flask de "ma-voix" : enregistre ta voix et transforme du texte en message vocal."""

import gc
import io
import queue
import threading
import time
import uuid
from pathlib import Path

import soundfile as sf
from flask import Flask, jsonify, request, send_file

from moteur import ETAPES_SON, LANGUES, Moteur, decouper_texte

DOSSIER = Path(__file__).parent
DOSSIER_VOIX = DOSSIER / "voix"
DOSSIER_SORTIES = DOSSIER / "sorties"
DOSSIER_VOIX.mkdir(exist_ok=True)
DOSSIER_SORTIES.mkdir(exist_ok=True)

FICHIER_VOIX = DOSSIER_VOIX / "ma_voix.wav"
DUREE_MIN_VOIX = 5  # secondes
LONGUEUR_MAX_TEXTE = 2000  # caracteres

app = Flask(__name__)
moteur = Moteur()

# Les generations en cours ou finies : { id: {...} }
taches = {}
# Les messages qui attendent leur tour
file_attente = queue.Queue()


def ouvrier():
    """Un seul thread fait TOUT le travail de l'IA : charger le modele, puis generer
    les messages un par un, dans l'ordre. (Avec un nouveau thread par message,
    PyTorch reservait a chaque fois de la memoire en plus : 7 Go au lieu de 4,5 Go.)"""
    moteur.charger()
    if not moteur.pret:
        return
    while True:
        executer_tache(*file_attente.get())


@app.get("/api/statut")
def statut():
    return jsonify(
        modele_pret=moteur.pret,
        erreur=moteur.erreur,
        voix_enregistree=FICHIER_VOIX.exists(),
        langues=LANGUES,
    )


@app.post("/api/voix")
def enregistrer_voix():
    fichier = request.files.get("audio")
    if fichier is None:
        return jsonify(erreur="Aucun fichier audio recu."), 400

    temporaire = DOSSIER_VOIX / "nouvelle_voix.wav"
    fichier.save(temporaire)
    try:
        infos = sf.info(temporaire)
    except Exception:
        temporaire.unlink(missing_ok=True)
        return jsonify(erreur="Fichier audio illisible (WAV attendu)."), 400

    if infos.duration < DUREE_MIN_VOIX:
        temporaire.unlink()
        return jsonify(erreur=f"Enregistrement trop court : au moins {DUREE_MIN_VOIX} secondes."), 400

    temporaire.replace(FICHIER_VOIX)
    moteur.voix_chargee = None  # la prochaine generation analysera la nouvelle voix
    return jsonify(message="Voix enregistree !", duree=round(infos.duration, 1))


@app.get("/api/voix")
def ecouter_voix():
    if not FICHIER_VOIX.exists():
        return jsonify(erreur="Aucune voix enregistree."), 404
    return send_file(FICHIER_VOIX, mimetype="audio/wav", max_age=0)


@app.post("/api/generer")
def generer():
    """Lance la generation en arriere-plan et renvoie tout de suite un numero de tache."""
    if not moteur.pret:
        return jsonify(erreur="Le modele est encore en train de charger, patiente un peu."), 503
    if not FICHIER_VOIX.exists():
        return jsonify(erreur="Enregistre d'abord ta voix."), 400

    donnees = request.get_json(silent=True) or {}
    texte = (donnees.get("texte") or "").strip()
    langue = donnees.get("langue", "fr")
    expressivite = float(donnees.get("expressivite", 0.5))
    qualite = donnees.get("qualite", "rapide")

    if not texte:
        return jsonify(erreur="Le texte est vide."), 400
    if len(texte) > LONGUEUR_MAX_TEXTE:
        return jsonify(erreur=f"Texte trop long (max {LONGUEUR_MAX_TEXTE} caracteres)."), 400
    if langue not in LANGUES:
        return jsonify(erreur=f"Langue inconnue : {langue}"), 400
    if qualite not in ETAPES_SON:
        return jsonify(erreur=f"Qualite inconnue : {qualite}"), 400
    expressivite = min(max(expressivite, 0.25), 2.0)

    identifiant = uuid.uuid4().hex[:8]
    morceaux = decouper_texte(texte)
    taches[identifiant] = {"total": len(morceaux), "audios": [], "fini": False, "erreur": None, "fichier": None}
    file_attente.put((identifiant, morceaux, langue, expressivite, qualite))
    return jsonify(id=identifiant, total=len(morceaux))


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
        tache["erreur"] = str(e)
        print(f"[tache {identifiant}] erreur :", e)
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
    chemin = DOSSIER_SORTIES / Path(nom).name  # .name : empeche de sortir du dossier
    if not chemin.exists():
        return jsonify(erreur="Fichier introuvable."), 404
    return send_file(chemin, mimetype="audio/wav", download_name=chemin.name)


if __name__ == "__main__":
    # Le modele met du temps a charger : on demarre l'ouvrier en arriere-plan
    # pour que le serveur reponde tout de suite.
    threading.Thread(target=ouvrier, daemon=True).start()
    # use_reloader=False : sinon Flask chargerait le modele deux fois
    app.run(port=5000, debug=True, use_reloader=False)
