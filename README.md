# 🎙️ Ma Voix

Transforme n'importe quel texte en message vocal **avec ta propre voix**.
Tu t'enregistres une fois (~15 secondes), puis tu tapes un texte : l'IA le lit avec ta voix.

Par défaut, tout tourne **en local** sur ton PC : ta voix n'est jamais envoyée sur Internet.
(Exception : la [version rapide sur GPU](#-version-rapide-sur-gpu-colab), qui tourne chez Google Colab.)

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
  - `moteur.py` — charge le modèle (sur la carte graphique s'il y en a une, sinon sur le
    processeur), découpe les textes en phrases, colle les morceaux audio, et en mode
    « Précision maximale » garde la version la plus ressemblante.
  - `preparation.py` — nettoie ton enregistrement (silences, souffle, volume) et mesure sa qualité.
- **Frontend** (`frontend/src/`) :
  - `EnregistreurVoix.jsx` — enregistrement au micro (ou import d'un fichier), écoute, envoi.
  - `GenerateurMessage.jsx` — zone de texte, langue, expressivité, lecteur + téléchargement.
  - `audio.js` — convertit l'enregistrement du navigateur en WAV (pas besoin de ffmpeg).
- **Colab** (`colab/ma_voix_gpu.ipynb`) — le notebook de la version rapide sur GPU.

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

La ressemblance de la voix reste quasi identique (0,93 → 0,92). Le mode « Haute qualité »
de la page repasse à 10 étapes. Tester 8 threads au lieu de 4, ou compresser aussi la partie
« son » (`s3gen`), n'a rien fait gagner.

**Le plus important : la mémoire.** Le modèle utilise ~4,5 Go de RAM (jusqu'à 6,5 Go pendant
le chargement). Avec 8 Go, ferme Chrome et les autres applis lourdes pendant que tu l'utilises :
si Windows manque de RAM, tout devient 2 à 3 fois plus lent.

## Pourquoi ton enregistrement est nettoyé

Le modèle n'écoute que les **6 à 10 premières secondes** de ton échantillon. S'il y a du silence
ou du souffle dedans, il copie le bruit au lieu de ta voix et le résultat sonne « robot ».
Le serveur nettoie donc chaque enregistrement (`preparation.py`) :

1. coupe les très basses fréquences (bruits de bureau) ;
2. réduit le bruit de fond constant (ventilateur, souffle du micro) ;
3. retire les silences, pour que le début soit rempli de parole ;
4. met la voix à un volume normal (-20 LUFS).

Mesuré sur un vrai enregistrement (volume -48 dB, 28 % de parole dans les 6 premières secondes) :
la ressemblance de la voix générée passe de **0,77 à 0,81–0,87**.

## Modes de qualité

| Mode | Ce qu'il fait | Temps (phrase de 8 s) |
|---|---|---|
| Rapide | son en 5 étapes, 1 essai | ~1 min 30 |
| Haute qualité | son en 10 étapes, 1 essai | ~2 min |
| Précision maximale | 10 étapes, **3 essais par phrase**, garde le plus ressemblant | ~8 min |

D'un essai à l'autre, la ressemblance varie (0,81 à 0,87 sur le même texte) : la précision
maximale évite les mauvais tirages.

Sur carte graphique (Colab), « Rapide » utilise déjà 10 étapes : il donne le même son que
« Haute qualité ».

## Conseils pour un bon clonage

- Enregistre-toi **au calme**, sans musique ni ventilateur, à ~20 cm du micro.
- **Commence à parler dès que tu cliques** : les premières secondes comptent le plus.
- Surveille la **barre de volume** pendant l'enregistrement : elle doit rester verte.
- Après l'envoi, lis les conseils affichés et recommence si ta voix était trop faible ou bruitée.
- Parle **naturellement**, avec le ton que tu veux retrouver dans les messages.
- 10 à 20 secondes suffisent (le modèle n'utilise que les 10 premières).
- **Expressivité** : 0.5 = naturel ; plus haut = plus d'émotion (mais parfois moins stable).
- Écris la ponctuation : les points et virgules donnent les pauses.

## ⚡ Version rapide sur GPU (Colab)

Ton PC n'a pas de carte graphique : une phrase prend plus d'une minute. **Google Colab** prête
gratuitement un ordinateur avec une carte graphique NVIDIA T4, où chaque phrase devrait sortir
en quelques secondes (pas encore mesuré). Il te faut seulement un compte Google.

> ⚠️ **Vie privée.** Dans cette version, ta voix et tes textes **quittent ton PC** : ils sont
> envoyés sur un ordinateur de Google pendant la session, et en mode B ils passent aussi par le
> tunnel de Cloudflare (chiffré en HTTPS). Tout est effacé à la fin de la session Colab, ou tout de
> suite avec **Exécution → Déconnecter et supprimer l'environnement d'exécution**.
> Si tu ne veux pas que ta voix sorte de ton PC, garde la version locale.

**Les règles de Colab à connaître :**

- Les *deepfakes* sont interdits : clone **uniquement ta propre voix**.
- Avec Colab **gratuit**, il faut utiliser le notebook lui-même (**mode A**). Passer surtout par
  une page web (**mode B**, ta page habituelle) y est interdit : Google peut couper la session
  sans prévenir. Le mode B est fait pour un compte Colab avec des unités de calcul (payant).
- Une session gratuite dure au maximum 12 heures, et s'arrête plus tôt si tu ne touches plus
  au notebook. Ton ordinateur Colab repart de zéro à chaque session (il faut réinstaller et
  renvoyer ta voix).

### Étape 1 — Ouvrir le notebook

1. Ouvre ce lien dans ton navigateur :
   https://colab.research.google.com/github/yassinechkir38-del/ma-voix/blob/main/colab/ma_voix_gpu.ipynb
2. Connecte-toi avec ton compte Google si on te le demande.
3. Menu **Exécution → Modifier le type d'exécution** : vérifie que **GPU T4** est choisi,
   puis **Enregistrer**.

### Étape 2 — Installer et démarrer (cellules 1, 2 et 3)

Une « cellule » est un bloc du notebook. Pour la lancer, clique sur le bouton **▶** à sa gauche,
puis attends le **✓ vert** avant de passer à la suivante.

1. **Cellule 1** : ▶. Si Colab affiche « ce notebook n'a pas été créé par Google », clique sur
   **Exécuter quand même**. Tu dois voir `✅ Carte graphique trouvée`.
2. **Cellule 2** : ▶, puis attends 3 à 5 minutes. Tu dois voir `✅ Installation terminée`.
3. **Cellule 3** : laisse le mode **A - dans le notebook** et clique sur ▶. La première fois,
   le modèle (~3 Go) se télécharge. Tu dois voir `✅ Modèle prêt`.

### Étape 3 (mode A) — Créer tes messages dans le notebook

1. **Cellule 4** : coche la case **c_est_ma_voix**, clique sur ▶, puis sur **Parcourir…**
   (ou **Choisir des fichiers**) et choisis un enregistrement de ta voix de 10 à 20 secondes.
   Tous les formats marchent. Si tu as déjà utilisé ma-voix sur ton PC, ta voix nettoyée est ici :
   `Documents\dev\ma-voix\backend\voix\ma_voix.wav`.
2. **Cellule 5** : écris ton texte dans le champ **texte**, choisis la langue, puis ▶.
   Le message se joue dans le notebook et se télécharge sur ton PC.
3. Pour un autre message : change le texte et clique de nouveau sur ▶ (cellule 5 seulement).

### Mode B — Avec ta page habituelle (compte Colab payant)

1. Dans la **cellule 3**, choisis **B - avec ma page (tunnel)** et clique sur ▶.
   À la fin, elle affiche deux lignes qui ressemblent à ça :

   ```
   VITE_API_URL=https://mots-au-hasard-1234.trycloudflare.com
   MA_VOIX_JETON=un-long-code-secret
   ```

2. Sur ton PC, ouvre **Git Bash** et va dans le dossier de la page :

   ```bash
   cd ~/Documents/dev/ma-voix/frontend
   ```

3. Ouvre (ou crée) le fichier `.env.local` avec le Bloc-notes :

   ```bash
   notepad .env.local
   ```

   Si le Bloc-notes demande s'il faut créer le fichier, réponds **Oui**. Colle les deux lignes
   du notebook (en remplaçant les anciennes s'il y en a), enregistre avec **Ctrl+S** et ferme.

4. Lance la page (pas besoin de lancer le backend sur ton PC) :

   ```bash
   npm run dev
   ```

5. Ouvre http://localhost:5173. En haut, tu dois voir **✅ Modèle prêt (carte graphique)**, et en
   bas « Mode GPU ». Enregistre ta voix une fois (l'ordinateur Colab est vide au départ),
   puis utilise la page comme d'habitude.

**À chaque nouvelle session Colab** (ou si tu relances la cellule 3), l'adresse et le jeton
changent : remplace les deux lignes dans `.env.local`, puis dans le terminal de `npm run dev`,
appuie sur **Ctrl+C** et relance `npm run dev`. Si tu oublies, la page affiche
« Accès refusé » ou « Colab injoignable ».

Garde l'onglet Colab ouvert pendant que tu utilises la page.

**Revenir à la version locale** : supprime le fichier `.env.local`,

```bash
rm .env.local
```

puis lance le backend et la page comme dans [Lancer l'application](#lancer-lapplication).

**Pourquoi un jeton secret ?** Le tunnel rend le serveur Colab joignable depuis tout Internet.
Sans le jeton, le serveur refuse toutes les requêtes. Le jeton reste dans `.env.local` sur ton PC
(ce fichier n'est jamais envoyé sur GitHub) et c'est Vite qui l'ajoute à chaque requête : il
n'apparaît jamais dans la page. Ne le partage avec personne. Détails : [SECURITE.md](SECURITE.md) (MV-7).

> Le notebook télécharge le code depuis GitHub : une modification faite sur ton PC n'arrive sur
> Colab qu'une fois envoyée sur GitHub (`git push`).

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
