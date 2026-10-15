import { useEffect, useRef, useState } from 'react'

const LONGUEUR_MAX = 2000

// Noms des langues en francais (les codes viennent du backend)
const NOMS_LANGUES = {
  fr: 'Français', ar: 'Arabe', en: 'Anglais', es: 'Espagnol', de: 'Allemand',
  it: 'Italien', pt: 'Portugais', nl: 'Néerlandais', tr: 'Turc', ru: 'Russe',
  zh: 'Chinois', ja: 'Japonais', ko: 'Coréen', hi: 'Hindi', pl: 'Polonais',
  sv: 'Suédois', da: 'Danois', no: 'Norvégien', fi: 'Finnois', el: 'Grec',
  he: 'Hébreu', ms: 'Malais', sw: 'Swahili',
}

export default function GenerateurMessage({ langues, actif }) {
  const [texte, setTexte] = useState('')
  const [langue, setLangue] = useState('fr')
  const [expressivite, setExpressivite] = useState(0.5)
  const [qualite, setQualite] = useState('rapide')
  const [enCours, setEnCours] = useState(false)
  const [secondes, setSecondes] = useState(0)
  const [progression, setProgression] = useState(null) // { prets, total }
  const [erreur, setErreur] = useState(null)
  const [messages, setMessages] = useState([]) // { id, texte, url, nom }

  const minuterieRef = useRef(null)
  const lecteurRef = useRef(null) // lecteur audio "en direct"
  const fileAttenteRef = useRef([]) // morceaux prets mais pas encore joues
  const monteRef = useRef(true)

  useEffect(() => {
    monteRef.current = true
    return () => {
      monteRef.current = false
      clearInterval(minuterieRef.current)
    }
  }, [])

  // Lecture progressive : on joue chaque phrase des qu'elle arrive, l'une apres l'autre
  function jouerSuivant() {
    const lecteur = lecteurRef.current
    if (!lecteur || !(lecteur.paused || lecteur.ended) || fileAttenteRef.current.length === 0) return
    if (lecteur.src.startsWith('blob:')) URL.revokeObjectURL(lecteur.src)
    lecteur.src = fileAttenteRef.current.shift()
    lecteur.play().catch(() => {})
  }

  async function generer() {
    setErreur(null)
    setEnCours(true)
    setSecondes(0)
    setProgression(null)
    fileAttenteRef.current = []
    minuterieRef.current = setInterval(() => setSecondes((s) => s + 1), 1000)
    try {
      // 1. On demande au backend de lancer la generation
      const reponse = await fetch('/api/generer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texte, langue, expressivite, qualite }),
      })
      const tache = await reponse.json().catch(() => ({}))
      if (!reponse.ok) throw new Error(tache.erreur || `Erreur du serveur (${reponse.status})`)
      setProgression({ prets: 0, total: tache.total })

      // 2. On demande ou ca en est toutes les secondes, et on recupere chaque nouvelle phrase
      let recus = 0
      while (monteRef.current) {
        await attendre(1000)
        const etat = await (await fetch(`/api/taches/${tache.id}`)).json()
        if (etat.erreur) throw new Error(etat.erreur)

        for (; recus < etat.prets; recus++) {
          const morceau = await fetch(`/api/taches/${tache.id}/morceaux/${recus}`)
          fileAttenteRef.current.push(URL.createObjectURL(await morceau.blob()))
          jouerSuivant()
        }
        setProgression({ prets: etat.prets, total: etat.total })

        // 3. Fini : on ajoute le message complet a l'historique
        if (etat.fini) {
          setMessages((anciens) => [
            { id: tache.id, texte, url: `/api/sorties/${etat.fichier}`, nom: etat.fichier },
            ...anciens,
          ])
          break
        }
      }
    } catch (e) {
      setErreur(e.message === 'Failed to fetch' ? 'Le serveur ne répond pas.' : e.message)
    } finally {
      clearInterval(minuterieRef.current)
      setEnCours(false)
    }
  }

  const codes = Object.keys(langues).sort((a, b) =>
    (NOMS_LANGUES[a] ?? a).localeCompare(NOMS_LANGUES[b] ?? b),
  )

  return (
    <section className="carte">
      <h2>
        <span className="numero">2</span> Ton message
      </h2>

      <textarea
        value={texte}
        onChange={(e) => setTexte(e.target.value)}
        maxLength={LONGUEUR_MAX}
        rows={6}
        placeholder="Tape ici le texte que ta voix doit lire…"
        dir="auto"
      />
      <div className="compteur">
        {texte.length} / {LONGUEUR_MAX}
      </div>

      <div className="reglages">
        <label>
          Langue
          <select value={langue} onChange={(e) => setLangue(e.target.value)}>
            {codes.map((code) => (
              <option key={code} value={code}>
                {NOMS_LANGUES[code] ?? langues[code]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Qualité
          <select value={qualite} onChange={(e) => setQualite(e.target.value)}>
            <option value="rapide">Rapide (recommandé)</option>
            <option value="max">Maximale (2× plus lent)</option>
          </select>
        </label>
        <label>
          Expressivité : {expressivite.toFixed(2)}
          <input
            type="range"
            min="0.25"
            max="1.5"
            step="0.05"
            value={expressivite}
            onChange={(e) => setExpressivite(Number(e.target.value))}
          />
          <small>calme ← → expressif</small>
        </label>
      </div>

      <button
        className="bouton principal large"
        onClick={generer}
        disabled={!actif || enCours || !texte.trim()}
      >
        {enCours ? `⏳ Génération… ${secondes} s` : '🔊 Générer le message vocal'}
      </button>
      {progression && enCours && (
        <div className="progression">
          <div className="barre">
            <div
              className="remplissage"
              style={{ width: `${(100 * progression.prets) / progression.total}%` }}
            />
          </div>
          <small>
            Phrase {Math.min(progression.prets + 1, progression.total)} sur {progression.total} en
            cours… Chaque phrase est jouée dès qu'elle est prête.
          </small>
        </div>
      )}
      <audio
        ref={lecteurRef}
        onEnded={jouerSuivant}
        controls
        hidden={!progression || !enCours}
      />
      {erreur && <p className="message erreur">{erreur}</p>}

      {messages.length > 0 && (
        <ul className="historique">
          {messages.map((m) => (
            <li key={m.id}>
              <p dir="auto">{m.texte}</p>
              <audio controls src={m.url} />
              <a className="bouton secondaire petit" href={m.url} download={m.nom}>
                ⬇ Télécharger
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function attendre(ms) {
  return new Promise((resoudre) => setTimeout(resoudre, ms))
}
