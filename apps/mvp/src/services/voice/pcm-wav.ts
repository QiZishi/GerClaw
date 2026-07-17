/** Wrap trusted little-endian PCM16 audio from FastAPI in a browser-playable WAV container. */
export function pcm16leToWav(pcm: ArrayBuffer, sampleRate = 24_000): Blob {
  if (!Number.isInteger(sampleRate) || sampleRate < 8_000 || sampleRate > 48_000) {
    throw new Error("TTS 音频采样率不正确");
  }
  if (pcm.byteLength === 0 || pcm.byteLength % 2 !== 0) {
    throw new Error("TTS 返回的音频格式不正确");
  }
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const writeText = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + pcm.byteLength, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, pcm.byteLength, true);
  return new Blob([header, pcm], { type: "audio/wav" });
}
