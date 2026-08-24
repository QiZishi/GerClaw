# Qianwen Speech Provider

本包是 `SpeechProvider` 的 Qianwen-only 提供方，固定使用 `qwen3-asr-flash-realtime` 和 `qwen3-tts-instruct-flash-realtime`。它保留 `dsh-talk@0.1.3` 与 `dsh-speech-plugin` 的流式连接、打断与资源释放设计，并适配 Qianwen 官方实时协议；来源、固定提交和许可证见 `NOTICE` 与 `LICENSES/`。

配置只接收 `MODEL_ASR_*`、`MODEL_TTS_*`、两个固定模型名、音色和朗读指令。SiliconFlow、MiMo、浏览器语音、Edge、Piper、Whisper、FunASR 与自动 fallback 均不在此代码路径。

ASR 接收最多 60 秒的 16 kHz 单声道 PCM16LE，TTS 输出 24 kHz 单声道 PCM16LE。原始音频只在实时连接中流动；完成事件由消费方写入账号 session。Cordis 卸载会中断全部 controller、上游 WebSocket 和浏览器连接。

运行 `packages/gerclaw/speech-qianwen/tests` 验证事件协议、分句和限制；真实验收还必须使用 `.env` 的 Qianwen 服务完成一次标准音频转写和一次 TTS 流。
