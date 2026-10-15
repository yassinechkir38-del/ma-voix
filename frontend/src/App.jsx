import { useEffect, useState } from 'react'
import EnregistreurVoix from './EnregistreurVoix'
import GenerateurMessage from './GenerateurMessage'

export default function App() {
  const [statut, setStatut] = useState(null)
  const [horsLigne, setHorsLigne] = useState(false)

  async function chargerStatut() {
    try {
      const reponse = await fetch('/api/statut')
      setStatut(await reponse.json())
      setHorsLigne(false)
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
        <Badge statut={statut} horsLigne={horsLigne} />
      </header>

      <EnregistreurVoix
        voixEnregistree={statut?.voix_enregistree}
        onVoixEnregistree={chargerStatut}
      />
      <GenerateurMessage
        langues={statut?.langues ?? { fr: 'French' }}
        actif={Boolean(statut?.modele_pret && statut?.voix_enregistree)}
      />

      <footer>Tout est calculé sur ton ordinateur : ta voix ne quitte jamais ton PC.</footer>
    </main>
  )
}

function Badge({ statut, horsLigne }) {
  if (horsLigne) return <span className="badge erreur">Backend arrêté — lance « python app.py »</span>
  if (!statut) return <span className="badge">Connexion…</span>
  if (statut.erreur) return <span className="badge erreur">Erreur du modèle : {statut.erreur}</span>
  if (!statut.modele_pret)
    return <span className="badge attente">⏳ Chargement du modèle d'IA (1 à 2 min)…</span>
  return <span className="badge ok">✅ Modèle prêt</span>
}
