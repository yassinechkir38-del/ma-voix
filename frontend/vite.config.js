import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Version GPU (Colab) : le fichier frontend/.env.local donne l'adresse du tunnel
  // (VITE_API_URL) et le jeton secret (MA_VOIX_JETON). Sans ce fichier : backend local.
  const env = loadEnv(mode, process.cwd(), ['VITE_', 'MA_VOIX_'])
  return {
    plugins: [react()],
    server: {
      // Les appels a /api sont rediriges vers le backend Flask (local ou Colab)
      proxy: { '/api': cibleApi(env) },
    },
  }
})

function cibleApi({ VITE_API_URL: url, MA_VOIX_JETON: jeton }) {
  if (!url) return 'http://127.0.0.1:5000'
  if (!/^https:\/\/[a-z0-9.-]+(:\d+)?\/?$/i.test(url))
    throw new Error('VITE_API_URL doit ressembler a https://xxxx.trycloudflare.com (voir README)')
  if (!jeton) throw new Error('MA_VOIX_JETON manque dans frontend/.env.local (voir README)')
  return {
    target: url.replace(/\/$/, ''),
    changeOrigin: true, // le serveur Colab n'accepte que l'adresse du tunnel (MV-7)
    secure: true, // HTTPS avec un certificat verifie
    // Le jeton est ajoute ICI, par Vite sur ton PC : il n'arrive jamais dans le navigateur.
    // (Une variable VITE_... serait visible dans le code de la page : SEC-1.)
    headers: { 'X-Ma-Voix-Jeton': jeton },
  }
}
