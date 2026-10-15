# 🎙️ Ma Voix

Transforme n'importe quel texte en message vocal **avec ta propre voix**.
Tu t'enregistres une fois (~15 secondes), puis tu tapes un texte : l'IA le lit avec ta voix.

Tout tourne **en local** sur ton PC : ta voix n'est jamais envoyée sur Internet.

## Comment ça marche

```
Navigateur (React)                         Backend (Flask)
──────────────────                         ───────────────
1. Tu t'enregistres   ── WAV ────────────▶ POST /api/voix            → voix/ma_voix.wav
2. Tu tapes un texte  ── texte ──────────▶ POST /api/generer         → { id } (file d'attente)
3. Toutes les 1 s     ── "ou ca en est ?" ▶ GET  /api/taches/<id>     → { prets: 1, total: 3 }
4. Chaque phrase prete ◀── WAV ─────────── GET  /api/taches/<id>/morceaux/<n>  → jouee tout de suite
5. Message complet    ◀── WAV ─────────── GET  /api/sorties/message_*.wav     → historique + telecharger
```

Le texte est decoupe en phrases. Un seul « ouvrier » (thread) genere les phrases une par une
avec Chatterbox ; la page joue chaque phrase des qu'elle arrive, sans attendre la fin.

- **Modèle** : [Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) de Resemble AI
  (licence MIT, 23 langues dont le français et l'arabe). Il clone une voix à partir d'un court extrait,
  sans entraînement.
- **Backend** (`backend/`) :
  - `app.py` — l'API Flask (statut, enregistrement de la voix, génération).
  - `moteur.py` — charge le modèle, découpe les textes en phrases, colle les morceaux audio.
- **Frontend** (`frontend/src/`) :
  - `EnregistreurVoix.jsx` — enregistrement au micro (ou import d'un fichier), écoute, envoi.
  - `GenerateurMessage.jsx` — zone de texte, langue, expressivité, lecteur + téléchargement.
  - `audio.js` — convertit l'enregistrement du navigateur en WAV (pas besoin de ffmpeg).

## Lancer l'application

Il faut **deux terminaux** (Git Bash).

**Terminal 1 — backend :**

```bash
cd ~/Documents/dev/ma-voix/backend
```

```bash
.venv/Scripts/python app.py
```

La première fois, le modèle (~3 Go) se télécharge : ça peut prendre plusieurs minutes.
Ensuite il met environ 1 minute à charger à chaque démarrage.

**Terminal 2 — frontend :**

```bash
cd ~/Documents/dev/ma-voix/frontend
```

```bash
npm run dev
```

Puis ouvre http://localhost:5173 dans ton navigateur.

## Vitesse (PC sans carte graphique)

Mesuré sur ce PC (i7-8550U, 8 Go de RAM), pour une phrase de 6 secondes :

| Réglage | Temps |
|---|---|
| Modèle d'origine | 145 à 220 s |
| + transformeur compressé en **int8** | ~115 s |
| + son généré en **5 étapes** au lieu de 10 (mode « Rapide ») | **~50 s** |

La ressemblance de la voix reste quasi identique (0,93 → 0,92). Le mode « Qualité maximale »
de la page repasse à 10 étapes. Tester 8 threads au lieu de 4, ou compresser aussi la partie
« son » (`s3gen`), n'a rien fait gagner.

**Le plus important : la mémoire.** Le modèle utilise ~4,5 Go de RAM (jusqu'à 6,5 Go pendant
le chargement). Avec 8 Go, ferme Chrome et les autres applis lourdes pendant que tu l'utilises :
si Windows manque de RAM, tout devient 2 à 3 fois plus lent.

## Conseils pour un bon clonage

- Enregistre-toi **au calme**, sans musique ni ventilateur, à ~20 cm du micro.
- Parle **naturellement**, avec le ton que tu veux retrouver dans les messages.
- 10 à 20 secondes suffisent (le modèle n'utilise que les 10 premières).
- **Expressivité** : 0.5 = naturel ; plus haut = plus d'émotion (mais parfois moins stable).
- Écris la ponctuation : les points et virgules donnent les pauses.

## Réinstaller (nouveau PC)

```bash
cd ~/Documents/dev/ma-voix/backend
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -r requirements.txt
cd ../frontend
npm install
```

## Utilisation responsable

Clone uniquement **ta propre voix** (ou celle d'une personne qui a donné son accord).
Chaque audio généré contient un filigrane inaudible (Perth) qui permet de le reconnaître comme synthétique.

Règles de sécurité du code (routes, formulaire, tests) : voir [SECURITE.md](SECURITE.md).
