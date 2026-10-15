"""Nettoyage et controle de qualite de l'echantillon de voix, avant le clonage.

Le modele n'ecoute que les 6 a 10 premieres secondes de l'echantillon : elles doivent
contenir de la parole bien audible, pas du silence ni du souffle.
"""

import numpy as np
import noisereduce
import pyloudnorm
import librosa
from scipy.signal import butter, sosfilt

VOLUME_CIBLE = -20.0  # LUFS (volume "normal" d'une voix enregistree)
CRETE_MAX = -1.0  # dBFS, pour ne jamais saturer
PAUSE_GARDEE = 0.15  # secondes de silence gardees entre deux bouts de parole


def mesurer(audio, frequence):
    """Mesure la qualite d'un enregistrement : volume, bruit, part de parole."""
    trame = int(0.05 * frequence)
    energies = np.array([
        np.sqrt(np.mean(audio[i:i + trame] ** 2))
        for i in range(0, len(audio) - trame, trame)
    ])
    db = 20 * np.log10(energies + 1e-9)
    bruit, voix = np.percentile(db, 10), np.percentile(db, 90)
    parole = db > bruit + 0.5 * (voix - bruit)
    return {
        "volume_db": round(float(voix), 1),
        "signal_bruit_db": round(float(voix - bruit), 1),
        "duree_parole": round(float(parole.sum() * 0.05), 1),
        "parole_debut_pct": round(float(100 * parole[: int(6 / 0.05)].mean()), 0),
    }


def preparer(audio, frequence, debruiter=True):
    """Renvoie l'echantillon nettoye : sans grave parasite, sans souffle, sans silences,
    au bon volume."""
    audio = audio.astype(np.float32)

    # 1. Coupe les tres basses frequences (bruits de bureau, souffle dans le micro)
    audio = sosfilt(butter(4, 70, "highpass", fs=frequence, output="sos"), audio).astype(np.float32)

    # 2. Reduit le bruit de fond constant (ventilateur, souffle du micro)
    if debruiter:
        audio = noisereduce.reduce_noise(y=audio, sr=frequence, stationary=True, prop_decrease=0.85)

    # 3. Retire les silences : on ne garde que les bouts de parole, colles avec de courtes pauses
    bouts = librosa.effects.split(audio, top_db=35, frame_length=1024, hop_length=256)
    marge = int(0.08 * frequence)
    pause = np.zeros(int(PAUSE_GARDEE * frequence), dtype=np.float32)
    morceaux = []
    for debut, fin in bouts:
        if fin - debut < int(0.15 * frequence):  # clic ou bruit isole : on ignore
            continue
        morceaux += [audio[max(0, debut - marge): fin + marge], pause]
    if morceaux:
        audio = np.concatenate(morceaux[:-1])

    # 4. Met la voix a un volume normal, sans saturer
    mesureur = pyloudnorm.Meter(frequence)
    volume = mesureur.integrated_loudness(audio)
    if np.isfinite(volume):
        audio = audio * 10 ** ((VOLUME_CIBLE - volume) / 20)
    crete = np.abs(audio).max()
    if crete > 10 ** (CRETE_MAX / 20):
        audio = audio * (10 ** (CRETE_MAX / 20) / crete)
    return audio.astype(np.float32)


def conseils(mesures):
    """Transforme les mesures de l'enregistrement d'origine en conseils simples."""
    avis = []
    if mesures["volume_db"] < -40:
        avis.append("Ta voix est très faible : rapproche-toi du micro (20 cm) et parle normalement fort.")
    if mesures["signal_bruit_db"] < 25:
        avis.append("Il y a beaucoup de bruit de fond : éloigne-toi du ventilateur du PC, ferme la fenêtre.")
    if mesures["duree_parole"] < 8:
        avis.append("Pas assez de parole : lis le texte en entier, sans longues pauses.")
    return avis
