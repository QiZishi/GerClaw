/**
 * 语音/音频类型定义
 * 对齐 gerclaw设计要求.md §4.3 语音模型调用规范 / §3.4.1 语音交互
 */

/** 音频格式 */
export type AudioFormat = "wav" | "mp3" | "pcm16";

/** ASR 转写结果 */
export interface ASRResult {
  text: string;
  confidence: number;
  language?: string;
  segments?: { text: string; start: number; end: number }[];
}

/** TTS 合成请求 */
export interface TTSRequest {
  text: string;
  voice?: string; // 默认 冰糖
  style?: string; // 风格描述
  format?: AudioFormat;
}

/** TTS 音色 */
export interface TTSVoice {
  id: string;
  name: string;
  language: "zh" | "en";
  gender: "male" | "female";
  description: string;
}

/** 录音状态 */
export type RecordingState =
  | "idle"
  | "requesting-permission"
  | "recording"
  | "stopped"
  | "transcribing"
  | "done"
  | "error";

/** 播放状态 */
export type PlaybackState = "idle" | "loading" | "playing" | "paused" | "ended" | "error";
