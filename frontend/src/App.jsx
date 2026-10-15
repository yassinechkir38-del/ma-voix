import { useEffect, useState } from 'react'
import EnregistreurVoix from './EnregistreurVoix'
import GenerateurMessage from './GenerateurMessage'

// Version GPU : la page passe par le tunnel vers Google Colab (voir README et vite.config.js)
const SUR_COLAB = Boolean(import.meta.env.VITE_API_URL)

export default function App() {
  const [statut, setStatut] = useState(null)
  const [horsLigne, setHorsLigne] = useState(false)
  const [refuse, setRefuse] = useState(false)

  async function chargerStatut() {
    try {
      const reponse = await fetch('/api/statut')
      const donnees = await reponse.json()
      setHorsLigne(false)
      // 403 : mauvais jeton ou mauvaise adresse du tunnel (on reessaie toutes les 3 s)
      setRefuse(reponse.status === 403)
      if (reponse.ok) setStatut(donnees)
    } catch {
      setHorsLigne(true)
    }
  }

  // On redemande le statut toutes les 3 s tant que le modele charge
  useEffect(() => {
    chargerStatut()
    if (statut?.modele_pret || statut?.erreur) return
    const minuterie = setInterval(chargerStatut, 3000)
    return () => clearInterval(minuterie)
  }, [statut?.modele_pret, statut?.erreur])

  return (
    <main>
      <header>
        <h1>🎙️ Ma Voix</h1>
        <p>Transforme n'importe quel texte en message vocal… avec ta propre voix.</p>
        <Badge statut={statut} horsLigne={horsLigne} refuse={refuse} />
      </header>

      <EnregistreurVoix
        voixEnregistree={statut?.voix_enregistree}
        onVoixEnregistree={chargerStatut}
      />
      <GenerateurMessage
        langues={statut?.langues ?? { fr: 'French' }}
        actif={Boolean(statut?.modele_pret && statut?.voix_enregistree)}
      />

      <footer>
        {SUR_COLAB
          ? 'Mode GPU : ta voix et tes textes partent sur le serveur Google Colab (effacé à la fin de la session).'
          : 'Tout est calculé sur ton ordinateur : ta voix ne quitte jamais ton PC.'}
      </footer>
    </main>
  )
}

function Badge({ statut, horsLigne, refuse }) {
  if (horsLigne && SUR_COLAB)
    return <span className="badge erreur">Colab injoignable — le notebook tourne-t-il encore ?</span>
  if (horsLigne) return <span className="badge erreur">Backend arrêté — lance « python app.py »</span>
  if (refuse)
    return (
      <span className="badge erreur">
        Accès refusé — recopie l'adresse et le jeton du notebook dans frontend/.env.local
      </span>
    )
  if (!statut) return <span className="badge">Connexion…</span>
  if (statut.erreur) return <span className="badge erreur">Erreur du modèle : {statut.erreur}</span>
  if (!statut.modele_pret)
    return <span className="badge attente">⏳ Chargement du modèle d'IA (1 à 2 min)…</span>
  return <span className="badge ok">✅ Modèle prêt{statut.gpu ? ' (carte graphique)' : ''}</span>
}
