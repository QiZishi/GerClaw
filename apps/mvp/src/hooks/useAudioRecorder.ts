"use client";

import { useState, useRef, useCallback, useEffect } from "react";

interface UseAudioRecorderReturn {
  isRecording: boolean;
  recordingDuration: number;
  audioLevel: number;
  audioBlob: Blob | null;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob>;
  cancelRecording: () => void;
  error: string | null;
}

interface UseAudioRecorderOptions {
  /**
   * 仅在界面确实展示声波时采样音量。关闭后不创建 AudioContext 或每帧刷新 React 状态，
   * 避免简单的“开始/停止录音”控件造成无意义的持续重渲染。
   */
  captureAudioLevel?: boolean;
}

export function useAudioRecorder({
  captureAudioLevel = true,
}: UseAudioRecorderOptions = {}): UseAudioRecorderReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const durationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  const resolveStopRef = useRef<((blob: Blob) => void) | null>(null);
  const rejectStopRef = useRef<((err: Error) => void) | null>(null);
  const isCancelRef = useRef(false);

  const cleanup = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  const startRecording = useCallback(async () => {
    setError(null);
    setAudioBlob(null);
    chunksRef.current = [];

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("您的浏览器不支持录音功能");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      let mimeType = "";
      const preferredTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
      for (const type of preferredTypes) {
        if (MediaRecorder.isTypeSupported(type)) {
          mimeType = type;
          break;
        }
      }

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blobType = mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: blobType });
        setAudioBlob(blob);
        setIsRecording(false);
        setAudioLevel(0);
        setRecordingDuration(0);
        cleanup();
        if (isCancelRef.current) {
          isCancelRef.current = false;
        } else if (resolveStopRef.current) {
          resolveStopRef.current(blob);
        }
        resolveStopRef.current = null;
        rejectStopRef.current = null;
      };

      mediaRecorder.onerror = (e) => {
        const err = new Error("录音出错：" + (e instanceof Event ? "未知错误" : String(e)));
        setError(err.message);
        cleanup();
        if (rejectStopRef.current) {
          rejectStopRef.current(err);
          resolveStopRef.current = null;
          rejectStopRef.current = null;
        }
      };

      if (captureAudioLevel) {
        const audioContext = new AudioContext();
        audioContextRef.current = audioContext;
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        analyserRef.current = analyser;

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        const updateAudioLevel = () => {
          if (!analyserRef.current) return;
          analyserRef.current.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
          }
          const average = sum / dataArray.length;
          const level = Math.min(1, average / 128);
          setAudioLevel(level);
          animationFrameRef.current = requestAnimationFrame(updateAudioLevel);
        };
        updateAudioLevel();
      }

      startTimeRef.current = Date.now();
      setRecordingDuration(0);
      durationIntervalRef.current = setInterval(() => {
        setRecordingDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);

      mediaRecorder.start(100);
      setIsRecording(true);
    } catch (err: unknown) {
      cleanup();
      let message = "无法访问麦克风";
      if (err instanceof DOMException) {
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          message = "麦克风权限被拒绝，请在浏览器设置中允许麦克风访问";
        } else if (err.name === "NotFoundError") {
          message = "未检测到麦克风设备";
        } else {
          message = "麦克风访问失败：" + err.message;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setError(message);
      throw new Error(message);
    }
  }, [captureAudioLevel, cleanup]);

  const stopRecording = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
        if (audioBlob) {
          resolve(audioBlob);
        } else {
          reject(new Error("没有正在进行的录音"));
        }
        return;
      }

      isCancelRef.current = false;
      resolveStopRef.current = resolve;
      rejectStopRef.current = reject;
      mediaRecorderRef.current.stop();
    });
  }, [audioBlob]);

  const cancelRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      isCancelRef.current = true;
      resolveStopRef.current = null;
      rejectStopRef.current = null;
      mediaRecorderRef.current.stop();
    } else {
      setIsRecording(false);
      setAudioLevel(0);
      setRecordingDuration(0);
      cleanup();
    }
  }, [cleanup]);

  return {
    isRecording,
    recordingDuration,
    audioLevel,
    audioBlob,
    startRecording,
    stopRecording,
    cancelRecording,
    error,
  };
}
