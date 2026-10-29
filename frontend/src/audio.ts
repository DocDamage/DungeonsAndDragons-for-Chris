/**
 * Procedural Web Audio Ambient Sound Generator
 * Synthesizes Gothic Rain & Castle Wind without external audio files.
 */

let audioCtx: AudioContext | null = null;
let masterGain: GainNode | null = null;
let isPlaying = false;
let rainSource: AudioBufferSourceNode | null = null;
let windOsc: OscillatorNode | null = null;
let windFilter: BiquadFilterNode | null = null;

export function toggleAmbiance(): boolean {
  if (isPlaying) {
    stopAmbiance();
    return false;
  } else {
    startAmbiance();
    return true;
  }
}

export function startAmbiance() {
  if (isPlaying) return;

  try {
    const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    audioCtx = new AudioContextClass();
    masterGain = audioCtx.createGain();
    masterGain.gain.setValueAtTime(0.35, audioCtx.currentTime);
    masterGain.connect(audioCtx.destination);

    // 1. Procedural Rain (filtered white noise)
    const bufferSize = audioCtx.sampleRate * 2;
    const noiseBuffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
    const output = noiseBuffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      output[i] = Math.random() * 2 - 1;
    }

    rainSource = audioCtx.createBufferSource();
    rainSource.buffer = noiseBuffer;
    rainSource.loop = true;

    const rainFilter = audioCtx.createBiquadFilter();
    rainFilter.type = 'lowpass';
    rainFilter.frequency.setValueAtTime(800, audioCtx.currentTime);

    const rainGain = audioCtx.createGain();
    rainGain.gain.setValueAtTime(0.2, audioCtx.currentTime);

    rainSource.connect(rainFilter);
    rainFilter.connect(rainGain);
    rainGain.connect(masterGain);
    rainSource.start();

    // 2. Procedural Gothic Wind (modulated pink noise / sine resonance)
    windOsc = audioCtx.createOscillator();
    windFilter = audioCtx.createBiquadFilter();
    windFilter.type = 'bandpass';
    windFilter.frequency.setValueAtTime(320, audioCtx.currentTime);
    windFilter.Q.setValueAtTime(3.0, audioCtx.currentTime);

    const windGain = audioCtx.createGain();
    windGain.gain.setValueAtTime(0.12, audioCtx.currentTime);

    windOsc.type = 'sine';
    windOsc.frequency.setValueAtTime(140, audioCtx.currentTime);

    windOsc.connect(windFilter);
    windFilter.connect(windGain);
    windGain.connect(masterGain);
    windOsc.start();

    isPlaying = true;
  } catch (err) {
    console.error("Web Audio ambiance error:", err);
  }
}

export function stopAmbiance() {
  if (!isPlaying || !audioCtx) return;
  try {
    rainSource?.stop();
    windOsc?.stop();
    audioCtx.close();
  } catch {
    // Ignore close errors
  }
  audioCtx = null;
  isPlaying = false;
}
