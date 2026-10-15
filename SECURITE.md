# Règles de sécurité de ma-voix

Les numéros entre parenthèses (VAL-4, AUTH-7, CORS-1, SEC-5, AUTH-8, WH-1…) renvoient aux règles
générales du fichier `securite.md` du dépôt `dev`, dont ce projet est issu.
Toute modification d'une route ou d'un formulaire doit respecter les règles ci-dessous.

Par défaut, ma-voix tourne uniquement sur le PC de l'utilisateur : pas de base de données, pas
de compte, aucun service tiers (le modèle d'IA est téléchargé une fois depuis Hugging Face, puis
tout est calculé en local). Les données sensibles sont l'échantillon de voix
(`backend/voix/`) et les messages générés (`backend/sorties/`), tous deux ignorés par git.

Seule exception : la version GPU sur Google Colab (`colab/ma_voix_gpu.ipynb`), où le backend
tourne sur une machine de Google et peut être rendu joignable depuis Internet par un tunnel.
Elle est encadrée par la règle **MV-7**.

- **MV-1 OBLIGATOIRE** : le serveur écoute sur `127.0.0.1` uniquement, jamais `0.0.0.0`,
  y compris sur Colab (le tunnel tourne sur la même machine et s'y connecte en local).
- **MV-2** Exception à **AUTH-7** : en version locale, aucune route n'a d'authentification, car
  l'application n'a qu'un utilisateur, sur sa propre machine (dès que le serveur est joignable
  depuis Internet, le jeton de **MV-7** devient obligatoire). En compensation, `@app.before_request` :
  - refuse tout `Host` absent de l'allowlist `HOTES_AUTORISES` (`127.0.0.1`/`localhost`,
    ports 5000 et 5173) : protection contre le *DNS rebinding* ;
  - refuse tout `POST` sans l'en-tête `X-Ma-Voix: 1`. Un autre site ouvert dans le
    navigateur ne peut pas l'ajouter sans autorisation CORS, que le serveur ne donne jamais
    (pas de `flask-cors`, conforme à **CORS-1**).
- **MV-3** Exception à **VAL-4** : `MAX_CONTENT_LENGTH` = 8 Mo au lieu de 1 Mo, car un
  échantillon de voix de 30 s en WAV pèse jusqu'à ~6 Mo. La page coupe déjà l'audio à 30 s ;
  le serveur refuse un WAV de moins de 5 s ou de plus de 60 s.
- **MV-4** `POST /api/generer` est validé par le schéma Pydantic `DemandeGeneration`
  (`extra="forbid"`, texte 1 à 2000 caractères après `strip()`, `langue` et `qualite` en
  `Literal`, `expressivite` entre 0,25 et 2). Au plus 3 messages en file d'attente (429),
  et seulement les 20 dernières tâches gardées en mémoire.
- **MV-5** `GET /api/sorties/<nom>` n'accepte que les noms au format
  `message_AAAAMMJJ_HHMMSS.wav` (allowlist par expression régulière).
- **MV-6** Les erreurs renvoyées à la page sont génériques ; le détail ne va que dans le
  terminal du backend (**SEC-5**). `debug` seulement si `MA_VOIX_DEBUG=1` (**AUTH-8**).
- **MV-7 OBLIGATOIRE — version GPU sur Colab.** En mode B, le serveur Colab est joignable
  depuis Internet par un tunnel Cloudflare sans compte (`https://….trycloudflare.com`). Il est
  alors protégé par un secret partagé, comme un webhook (**WH-1**) :
  - `MA_VOIX_JETON` : jeton aléatoire de 43 caractères (`secrets.token_urlsafe(32)`), nouveau à
    chaque lancement de la cellule 3 du notebook. Quand il est défini, **toutes** les requêtes
    (y compris les GET : statut, voix, messages) doivent porter l'en-tête `X-Ma-Voix-Jeton`,
    comparé avec `hmac.compare_digest` ; sinon 403. INTERDIT : le mettre dans une URL (**SEC-3**)
    ou dans le journal du serveur. Le notebook l'affiche une seule fois, pour que l'utilisateur
    le recopie ; il ne sert plus à rien une fois la session terminée.
  - `MA_VOIX_HOTES` : ajoute à `HOTES_AUTORISES` l'hôte du tunnel, et lui seul (format
    `nom[:port]` vérifié, aucun joker).
  - Le serveur **refuse de démarrer** si `MA_VOIX_HOTES` est défini sans `MA_VOIX_JETON`, ou si
    le jeton fait moins de 32 caractères ou contient autre chose que `A-Z a-z 0-9 - _`
    (`lire_configuration` dans `app.py`).
  - L'en-tête `X-Ma-Voix: 1` reste exigé sur les `POST`, et toujours pas de CORS (**CORS-1**) :
    la page parle à son propre serveur Vite, qui relaie vers le tunnel.
  - Sur le PC, l'adresse et le jeton sont dans `frontend/.env.local` (ignoré par git via
    `*.local`). Le jeton s'appelle `MA_VOIX_JETON`, **sans** préfixe `VITE_` : c'est le proxy de
    Vite (`vite.config.js`) qui l'ajoute à chaque requête, il n'arrive donc jamais dans le code de
    la page (**SEC-1**). `VITE_API_URL` (adresse publique) doit être en `https://` (**HDR-3**).
  - cloudflared est téléchargé dans une version épinglée et vérifié par son empreinte SHA-256
    avant d'être lancé (**SEC-8**).
  - Pas de limite de débit (**AUTH-5**) : deviner un jeton de 256 bits est impossible en
    pratique, et le tunnel disparaît avec la session.
  - Vie privée : la voix et les textes partent chez Google Colab (et par Cloudflare en mode B).
    Le README et le bas de la page le disent ; le notebook fait cocher « c'est ma voix » avant
    l'envoi, et le fichier envoyé est supprimé dès qu'il a été transmis au serveur.

Tests négatifs : `backend/test_securite.py` (`.venv/Scripts/python -m pytest -q`), y compris
le jeton et le refus de démarrer de **MV-7**.
