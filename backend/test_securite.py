"""Tests negatifs des routes de ma-voix (checklist de securite.md).

Lancer : .venv/Scripts/python -m pytest -q
Le modele d'IA n'est pas charge pendant les tests (l'ouvrier ne demarre qu'avec "python app.py").
"""

import io

import numpy as np
import pytest
import soundfile as sf

import app as module_app

ENTETES = {"X-Ma-Voix": "1"}
DEMANDE_VALIDE = {"texte": "Bonjour tout le monde.", "langue": "fr", "expressivite": 0.5, "qualite": "rapide"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Les tests ecrivent dans un dossier temporaire, jamais dans ta vraie voix
    monkeypatch.setattr(module_app, "DOSSIER_VOIX", tmp_path)
    monkeypatch.setattr(module_app, "FICHIER_VOIX", tmp_path / "ma_voix.wav")
    # Le client de test de Flask envoie toujours "Host: localhost" (sans port)
    monkeypatch.setattr(module_app, "HOTES_AUTORISES", module_app.HOTES_AUTORISES | {"localhost"})
    module_app.app.config["TESTING"] = True
    with module_app.app.test_client() as c:
        yield c


def wav(secondes, frequence=16000, parole=True):
    """Faux enregistrement : 0,8 s de "voix" (sons) puis 0,2 s de pause, en boucle."""
    t = np.arange(int(secondes * frequence)) / frequence
    audio = 0.2 * np.sin(2 * np.pi * 150 * t) * ((t % 1.0) < 0.8)
    if not parole:
        audio[int(frequence):] = 0  # une seule seconde de son, puis silence
    tampon = io.BytesIO()
    sf.write(tampon, audio.astype(np.float32), frequence, format="WAV")
    tampon.seek(0)
    return tampon


# --- Requetes venant d'autres sites -------------------------------------------------------

def test_post_sans_entete_refuse(client):
    reponse = client.post("/api/generer", json=DEMANDE_VALIDE)
    assert reponse.status_code == 403


def test_hote_etranger_refuse(client):
    # DNS rebinding : un site pirate qui pointe vers 127.0.0.1
    reponse = client.get("/api/statut", headers={"Host": "pirate.example:5000"})
    assert reponse.status_code == 403


def test_hote_local_accepte(client):
    assert client.get("/api/statut").status_code == 200


def test_entetes_de_securite(client):
    reponse = client.get("/api/statut")
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["Cache-Control"] == "no-store"


# --- POST /api/generer : schema strict -----------------------------------------------------

@pytest.mark.parametrize("modif, champ", [
    ({"texte": ""}, "texte"),
    ({"texte": "   "}, "texte"),
    ({"texte": "a" * 2001}, "texte"),
    ({"texte": 42}, "texte"),
    ({"langue": "xx"}, "langue"),
    ({"expressivite": "abc"}, "expressivite"),
    ({"expressivite": 5}, "expressivite"),
    ({"qualite": "ultra"}, "qualite"),
    ({"pirate": True}, "pirate"),
])
def test_generer_entree_invalide(client, modif, champ):
    reponse = client.post("/api/generer", json={**DEMANDE_VALIDE, **modif}, headers=ENTETES)
    assert reponse.status_code == 400
    assert champ in reponse.get_json()["champs"]


def test_generer_corps_non_json(client):
    reponse = client.post("/api/generer", data="pas du json", headers=ENTETES)
    assert reponse.status_code == 400


def test_generer_valide_attend_le_modele(client):
    # Entree valide : passe la validation, puis 503 car le modele n'est pas charge
    reponse = client.post("/api/generer", json=DEMANDE_VALIDE, headers=ENTETES)
    assert reponse.status_code == 503


# --- POST /api/voix : fichier ---------------------------------------------------------------

def test_voix_sans_fichier(client):
    assert client.post("/api/voix", headers=ENTETES).status_code == 400


def test_voix_pas_un_wav(client):
    donnees = {"audio": (io.BytesIO(b"ceci n'est pas un son"), "voix.wav")}
    assert client.post("/api/voix", data=donnees, headers=ENTETES).status_code == 400


def test_voix_trop_courte(client):
    donnees = {"audio": (wav(2), "voix.wav")}
    assert client.post("/api/voix", data=donnees, headers=ENTETES).status_code == 400


def test_voix_trop_longue(client):
    donnees = {"audio": (wav(61, frequence=8000), "voix.wav")}
    assert client.post("/api/voix", data=donnees, headers=ENTETES).status_code == 400


def test_voix_trop_grosse(client):
    donnees = {"audio": (io.BytesIO(b"0" * (9 * 1024 * 1024)), "voix.wav")}
    assert client.post("/api/voix", data=donnees, headers=ENTETES).status_code == 413


def test_voix_presque_muette(client):
    # 10 s d'enregistrement mais 1 s de parole : refuse apres nettoyage, avec des conseils
    donnees = {"audio": (wav(10, parole=False), "voix.wav")}
    reponse = client.post("/api/voix", data=donnees, headers=ENTETES)
    assert reponse.status_code == 400
    assert reponse.get_json()["conseils"]


def test_voix_valide(client):
    donnees = {"audio": (wav(12), "voix.wav")}
    reponse = client.post("/api/voix", data=donnees, headers=ENTETES)
    assert reponse.status_code == 200
    assert module_app.FICHIER_VOIX.exists()
    assert {"volume_db", "signal_bruit_db", "duree_parole"} <= reponse.get_json()["mesures"].keys()


# --- GET /api/sorties/<nom> : pas d'acces aux autres fichiers -----------------------------

@pytest.mark.parametrize("nom", ["app.py", "..%2Fapp.py", "message_x.wav", "message_20261015_141325.py"])
def test_sorties_nom_refuse(client, nom):
    assert client.get(f"/api/sorties/{nom}").status_code == 404


def test_tache_inconnue(client):
    assert client.get("/api/taches/inconnue").status_code == 404
    assert client.get("/api/taches/inconnue/morceaux/0").status_code == 404
