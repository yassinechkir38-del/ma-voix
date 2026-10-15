// Convertit n'importe quel audio (enregistrement du micro, MP3, M4A...) en fichier WAV.
// Le navigateur sait decoder ces formats, on n'a donc pas besoin d'installer ffmpeg.
// Garde au plus dureeMax secondes (le serveur refuse les fichiers de plus de 8 Mo).
// Renvoie { blob, duree } (duree en secondes).

export async function convertirEnWav(blob, dureeMax = 30) {
  const contexte = new AudioContext()
  try {
    const tampon = await contexte.decodeAudioData(await blob.arrayBuffer())
    const echantillons = versMono(tampon).slice(0, Math.round(dureeMax * tampon.sampleRate))
    return {
      blob: encoderWav(echantillons, tampon.sampleRate),
      duree: echantillons.length / tampon.sampleRate,
    }
  } finally {
    contexte.close()
  }
}

// Melange tous les canaux (stereo -> mono)
function versMono(tampon) {
  const mono = new Float32Array(tampon.length)
  for (let c = 0; c < tampon.numberOfChannels; c++) {
    const canal = tampon.getChannelData(c)
    for (let i = 0; i < canal.length; i++) mono[i] += canal[i] / tampon.numberOfChannels
  }
  return mono
}

// Ecrit un fichier WAV PCM 16 bits (44 octets d'en-tete + les echantillons)
function encoderWav(echantillons, frequence) {
  const vue = new DataView(new ArrayBuffer(44 + echantillons.length * 2))
  const ecrireTexte = (position, texte) =>
    [...texte].forEach((lettre, i) => vue.setUint8(position + i, lettre.charCodeAt(0)))

  ecrireTexte(0, 'RIFF')
  vue.setUint32(4, 36 + echantillons.length * 2, true)
  ecrireTexte(8, 'WAVE')
  ecrireTexte(12, 'fmt ')
  vue.setUint32(16, 16, true) // taille du bloc "fmt"
  vue.setUint16(20, 1, true) // format PCM
  vue.setUint16(22, 1, true) // 1 canal (mono)
  vue.setUint32(24, frequence, true)
  vue.setUint32(28, frequence * 2, true) // octets par seconde
  vue.setUint16(32, 2, true) // octets par echantillon
  vue.setUint16(34, 16, true) // bits par echantillon
  ecrireTexte(36, 'data')
  vue.setUint32(40, echantillons.length * 2, true)

  echantillons.forEach((valeur, i) => {
    const borne = Math.max(-1, Math.min(1, valeur))
    vue.setInt16(44 + i * 2, borne < 0 ? borne * 0x8000 : borne * 0x7fff, true)
  })
  return new Blob([vue], { type: 'audio/wav' })
}
