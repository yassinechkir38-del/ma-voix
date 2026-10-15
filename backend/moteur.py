"""Moteur de clonage vocal : charge Chatterbox Multilingual et genere de l'audio avec ta voix."""

import gc
import re

import librosa
import numpy as np
import torch

from chatterbox.mtl_tts import ChatterboxMultilingualTTS, SUPPORTED_LANGUAGES

# Petit silence insere entre deux phrases (en secondes)
PAUSE_ENTRE_PHRASES = 0.25
# On genere phrase par phrase : des morceaux courts = le 1er son arrive plus vite
LONGUEUR_MAX_MORCEAU = 150
# Le 1er morceau est plus court encore, pour entendre le debut le plus tot possible
LONGUEUR_PREMIER_MORCEAU = 60

# Carte graphique (GPU NVIDIA, par exemple sur Google Colab) si elle existe, sinon processeur
SUR_GPU = torch.cuda.is_available()
APPAREIL = "cuda" if SUR_GPU else "cpu"

# Reglages de vitesse (mesures sur ton PC, sans carte graphique) :
# - 4 threads = tes 4 coeurs physiques (8 ne va pas plus vite)
# - etapes de generation du son : 5 = 2x plus rapide que 10, difference quasi inaudible
# Sur GPU, 10 etapes sont deja rapides : on garde toujours la meilleure qualite.
NB_THREADS = 4
# Pour chaque mode de qualite : etapes de generation du son, et nombre d'essais par phrase.
# En "precision", on genere plusieurs versions de chaque phrase et on garde celle qui
# ressemble le plus a ta voix (mesure par l'empreinte vocale du modele).
ETAPES_SON = {"rapide": 10 if SUR_GPU else 5, "max": 10, "precision": 10}
ESSAIS = {"rapide": 1, "max": 1, "precision": 3}


class Moteur:
    def __init__(self):
        self.modele = None
        self.erreur = None
        self.voix_chargee = None  # chemin de l'echantillon deja "appris"
        self.etapes_son = ETAPES_SON["rapide"]

    @property
    def pret(self):
        return self.modele is not None

    @property
    def frequence(self):
        return self.modele.sr if self.modele else 24000

    def charger(self):
        """Charge le modele (long : ~1 min, et telechargement de ~3 Go la 1ere fois)."""
        try:
            print(f"[moteur] Calcul sur : {torch.cuda.get_device_name(0) if SUR_GPU else 'processeur (CPU)'}")
            if not SUR_GPU:
                torch.set_num_threads(NB_THREADS)
            modele = ChatterboxMultilingualTTS.from_pretrained(device=APPAREIL)

            if not SUR_GPU:
                # Compression "int8" du transformeur (la partie qui lit le texte) :
                # ~1.8x plus rapide sur CPU, la voix reste quasiment aussi ressemblante.
                # (Cette compression ne fonctionne que sur CPU : sur GPU, on n'en a pas besoin.)
                torch.ao.quantization.quantize_dynamic(
                    modele.t3.tfmr, {torch.nn.Linear}, dtype=torch.qint8, inplace=True
                )

            # Chatterbox ne permet pas de choisir le nombre d'etapes du son dans generate() :
            # on "enveloppe" sa fonction pour lui passer notre reglage.
            inference_originale = modele.s3gen.inference
            modele.s3gen.inference = lambda *a, **k: inference_originale(
                *a, n_cfm_timesteps=self.etapes_son, **k
            )

            # Echauffement : le tout 1er passage est toujours tres lent, on le fait maintenant
            modele.generate("Bonjour.", language_id="fr")
            # Le chargement laisse ~2 Go de "dechets" en memoire : on les libere
            gc.collect()

            self.modele = modele
            print("[moteur] Modele pret.")
        except Exception as e:  # on garde l'erreur pour l'afficher dans la page
            self.erreur = str(e)
            print("[moteur] Erreur de chargement :", e)

    def generer_morceaux(self, morceaux, langue, chemin_voix, expressivite=0.5, qualite="rapide"):
        """Genere les morceaux de texte un par un et les renvoie (yield) des qu'ils sont prets.
        Toujours appele depuis le meme thread (l'ouvrier de app.py)."""
        self.etapes_son = ETAPES_SON[qualite]
        if self.voix_chargee != chemin_voix:
            # Analyse de ta voix (une seule fois, tant que tu ne la changes pas)
            self.modele.prepare_conditionals(chemin_voix, exaggeration=expressivite)
            self.voix_chargee = chemin_voix

        for morceau in morceaux:
            meilleur, meilleure_ressemblance = None, -1.0
            for essai in range(ESSAIS[qualite]):
                audio = self.modele.generate(
                    morceau, language_id=langue, exaggeration=expressivite
                ).squeeze(0).numpy()
                if ESSAIS[qualite] == 1:
                    meilleur = audio
                    break
                ressemblance = self.ressemblance(audio)
                print(f"[moteur] essai {essai + 1}/{ESSAIS[qualite]} : ressemblance {ressemblance:.3f}")
                if ressemblance > meilleure_ressemblance:
                    meilleur, meilleure_ressemblance = audio, ressemblance
            yield meilleur

    def ressemblance(self, audio):
        """Compare l'empreinte vocale d'un audio genere a celle de ton echantillon (1 = identique)."""
        audio_16k = librosa.resample(audio, orig_sr=self.frequence, target_sr=16000)
        empreinte = self.modele.ve.embeds_from_wavs([audio_16k], sample_rate=16000).mean(axis=0)
        reference = self.modele.conds.t3.speaker_emb[0].cpu().numpy()
        return float(np.dot(empreinte, reference) / (np.linalg.norm(empreinte) * np.linalg.norm(reference)))

    def assembler(self, audios):
        """Colle les morceaux audio avec une petite pause entre chacun."""
        pause = np.zeros(int(PAUSE_ENTRE_PHRASES * self.frequence), dtype=np.float32)
        avec_pauses = []
        for audio in audios:
            avec_pauses += [audio, pause]
        return np.concatenate(avec_pauses[:-1])


def decouper_texte(texte):
    """Coupe le texte en phrases, puis regroupe les phrases courtes (max LONGUEUR_MAX_MORCEAU)."""
    phrases = re.split(r"(?<=[.!?…؟。])\s+", texte.strip())
    morceaux = []
    courant = ""
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        # Phrase trop longue a elle seule : on la coupe aux virgules
        if len(phrase) > LONGUEUR_MAX_MORCEAU:
            if courant:
                morceaux.append(courant)
                courant = ""
            morceaux.extend(_couper_aux_virgules(phrase))
        elif len(courant) + len(phrase) + 1 <= (LONGUEUR_MAX_MORCEAU if morceaux else LONGUEUR_PREMIER_MORCEAU):
            courant = f"{courant} {phrase}".strip()
        elif not courant:
            courant = phrase
        else:
            morceaux.append(courant)
            courant = phrase
    if courant:
        morceaux.append(courant)
    return morceaux


def _couper_aux_virgules(phrase):
    morceaux = []
    courant = ""
    for bout in re.split(r"(?<=[,،;:])\s+", phrase):
        if len(courant) + len(bout) + 1 <= LONGUEUR_MAX_MORCEAU:
            courant = f"{courant} {bout}".strip()
        else:
            if courant:
                morceaux.append(courant)
            courant = bout
    if courant:
        morceaux.append(courant)
    return morceaux


LANGUES = SUPPORTED_LANGUAGES
