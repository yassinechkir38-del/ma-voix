# Règles de sécurité de ma-voix

Les numéros entre parenthèses (VAL-4, AUTH-7, CORS-1, SEC-5, AUTH-8) renvoient aux règles
générales du fichier `securite.md` du dépôt `dev`, dont ce projet est issu.
Toute modification d'une route ou d'un formulaire doit respecter les règles ci-dessous.

ma-voix tourne uniquement sur le PC de l'utilisateur : pas de base de données, pas de
compte, aucun service tiers (le modèle d'IA est téléchargé une fois depuis Hugging Face, puis
tout est calculé en local). Les données sensibles sont l'échantillon de voix
(`backend/voix/`) et les messages générés (`backend/sorties/`), tous deux ignorés par git.

- **MV-1 OBLIGATOIRE** : le serveur écoute sur `127.0.0.1` uniquement, jamais `0.0.0.0`.
- **MV-2** Exception à **AUTH-7** : aucune route n'a d'authentification, car l'application
  n'a qu'un utilisateur, sur sa propre machine. En compensation, `@app.before_request` :
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

Tests négatifs : `backend/test_securite.py` (`.venv/Scripts/python -m pytest -q`).
