import { useEffect, useRef, useState } from 'react'
import { convertirEnWav } from './audio'

const DUREE_MIN = 8
const DUREE_MAX = 30

const TEXTE_A_LIRE = `Bonjour ! Aujourd'hui, j'enregistre ma voix pour créer mon propre message vocal.
Je parle calmement, d'une voix naturelle, comme si je racontais une histoire à un ami.
Le soleil brille, les oiseaux chantent, et tout se passe très bien.`

export default function EnregistreurVoix({ voixEnregistree, onVoixEnregistree }) {
  const [etat, setEtat] = useState('repos') // repos | enregistrement | apercu | envoi
  const [secondes, setSecondes] = useState(0)
  const [apercu, setApercu] = useState(null) // { blob, url, duree }
  const [consentement, setConsentement] = useState(false)
  const [message, setMessage] = useState(null) // { type: 'ok' | 'erreur', texte }
  const [versionVoix, setVersionVoix] = useState(Date.now())

  const enregistreurRef = useRef(null)
  const minuterieRef = useRef(null)

  // Arret automatique a DUREE_MAX secondes
  useEffect(() => {
    if (etat === 'enregistrement' && secondes >= DUREE_MAX) arreter()
  }, [secondes, etat])

  // Nettoyage si on quitte la page pendant un enregistrement
  useEffect(() => () => clearInterval(minuterieRef.current), [])

  async function demarrer() {
    setMessage(null)
    let flux
    try {
      flux = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, autoGainControl: false },
      })
    } catch {
      setMessage({ type: 'erreur', texte: "Impossible d'accéder au micro. Autorise-le dans le navigateur." })
      return
    }

    const morceaux = []
    const enregistreur = new MediaRecorder(flux)
    enregistreur.ondataavailable = (e) => morceaux.push(e.data)
    enregistreur.onstop = async () => {
      flux.getTracks().forEach((piste) => piste.stop())
      preparerApercu(await convertirEnWav(new Blob(morceaux, { type: enregistreur.mimeType })))
    }
    enregistreur.start()
    enregistreurRef.current = enregistreur

    setSecondes(0)
    setEtat('enregistrement')
    minuterieRef.current = setInterval(() => setSecondes((s) => s + 1), 1000)
  }

  function arreter() {
    clearInterval(minuterieRef.current)
    enregistreurRef.current?.stop()
  }

  async function importerFichier(evenement) {
    const fichier = evenement.target.files[0]
    evenement.target.value = ''
    if (!fichier) return
    setMessage(null)
    try {
      preparerApercu(await convertirEnWav(fichier, DUREE_MAX))
    } catch {
      setMessage({ type: 'erreur', texte: 'Ce fichier audio ne peut pas être lu.' })
    }
  }

  function preparerApercu({ blob, duree }) {
    if (apercu) URL.revokeObjectURL(apercu.url)
    setApercu({ blob, url: URL.createObjectURL(blob), duree })
    setEtat('apercu')
  }

  async function envoyer() {
    setEtat('envoi')
    const formulaire = new FormData()
    formulaire.append('audio', apercu.blob, 'ma_voix.wav')
    try {
      const reponse = await fetch('/api/voix', {
        method: 'POST',
        headers: { 'X-Ma-Voix': '1' }, // en-tete exige par le backend (anti autres sites)
        body: formulaire,
      })
      const donnees = await reponse.json()
      if (!reponse.ok) throw new Error(donnees.erreur)
      setMessage({ type: 'ok', texte: `${donnees.message} (${donnees.duree} s)` })
      URL.revokeObjectURL(apercu.url)
      setApercu(null)
      setEtat('repos')
      setVersionVoix(Date.now())
      onVoixEnregistree()
    } catch (e) {
      setMessage({ type: 'erreur', texte: e.message || 'Le serveur ne répond pas.' })
      setEtat('apercu')
    }
  }

  const tropCourt = apercu && apercu.duree < DUREE_MIN

  return (
    <section className="carte">
      <h2>
        <span className="numero">1</span> Ta voix
      </h2>
      <p className="aide">
        Enregistre-toi pendant 10 à 20 secondes, au calme, en lisant ce texte à voix haute :
      </p>
      <blockquote>{TEXTE_A_LIRE}</blockquote>

      {etat === 'enregistrement' ? (
        <div className="ligne">
          <button className="bouton danger" onClick={arreter}>
            ■ Arrêter
          </button>
          <span className="enregistrement">
            <span className="point-rouge" /> {secondes} s / {DUREE_MAX} s
          </span>
        </div>
      ) : (
        <div className="ligne">
          <button className="bouton principal" onClick={demarrer} disabled={etat === 'envoi'}>
            🎙️ {apercu ? 'Recommencer' : 'Enregistrer ma voix'}
          </button>
          <label className="bouton secondaire">
            📁 Importer un fichier
            <input type="file" accept="audio/*" onChange={importerFichier} hidden />
          </label>
        </div>
      )}

      {apercu && etat !== 'enregistrement' && (
        <div className="apercu">
          <p>
            Écoute ton enregistrement ({apercu.duree.toFixed(1)} s) :
          </p>
          <audio controls src={apercu.url} />
          {tropCourt && (
            <p className="message erreur">Trop court : il faut au moins {DUREE_MIN} secondes.</p>
          )}
          <label className="consentement">
            <input
              type="checkbox"
              checked={consentement}
              onChange={(e) => setConsentement(e.target.checked)}
            />
            Je confirme que c'est ma propre voix (ou que la personne a donné son accord).
          </label>
          <button
            className="bouton principal"
            onClick={envoyer}
            disabled={!consentement || tropCourt || etat === 'envoi'}
          >
            {etat === 'envoi' ? 'Envoi…' : '✔ Utiliser cette voix'}
          </button>
        </div>
      )}

      {message && <p className={`message ${message.type}`}>{message.texte}</p>}

      {voixEnregistree && !apercu && (
        <div className="apercu">
          <p>✅ Voix actuelle :</p>
          <audio controls src={`/api/voix?v=${versionVoix}`} />
        </div>
      )}
    </section>
  )
}

