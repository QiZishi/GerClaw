"use client";

const TARGET_SAMPLE_RATE = 16000;

function floatTo16BitPCM(float32Array: Float32Array): Int16Array {
  const int16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16;
}

function encodeWAV(samples: Int16Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    view.setInt16(offset, samples[i], true);
  }

  return buffer;
}

function resampleAndMixToMono(
  audioBuffer: AudioBuffer,
  targetSampleRate: number
): Float32Array {
  const numChannels = audioBuffer.numberOfChannels;
  const originalRate = audioBuffer.sampleRate;
  const originalLength = audioBuffer.length;
  const targetLength = Math.round(originalLength * targetSampleRate / originalRate);

  const result = new Float32Array(targetLength);

  const channels: Float32Array[] = [];
  for (let ch = 0; ch < numChannels; ch++) {
    channels.push(audioBuffer.getChannelData(ch));
  }

  for (let i = 0; i < targetLength; i++) {
    const srcIndex = (i * originalRate) / targetSampleRate;
    const srcIndex0 = Math.floor(srcIndex);
    const srcIndex1 = Math.min(srcIndex0 + 1, originalLength - 1);
    const frac = srcIndex - srcIndex0;

    let sum = 0;
    for (let ch = 0; ch < numChannels; ch++) {
      const v0 = channels[ch][srcIndex0];
      const v1 = channels[ch][srcIndex1];
      sum += v0 + (v1 - v0) * frac;
    }
    result[i] = sum / numChannels;
  }

  return result;
}

export async function convertBlobToWavBase64(blob: Blob): Promise<{ base64: string; mimeType: string }> {
  const arrayBuffer = await blob.arrayBuffer();

  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const audioCtx = new AudioCtx();

  try {
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
    const monoFloat32 = resampleAndMixToMono(audioBuffer, TARGET_SAMPLE_RATE);
    const pcm16 = floatTo16BitPCM(monoFloat32);
    const wavBuffer = encodeWAV(pcm16, TARGET_SAMPLE_RATE);

    const base64 = arrayBufferToBase64(wavBuffer);
    return { base64, mimeType: "audio/wav" };
  } finally {
    audioCtx.close().catch(() => {});
  }
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, Array.from(chunk));
  }
  return btoa(binary);
}
