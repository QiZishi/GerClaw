# @gerclaw/voice

## 职责

为智能对话提供录音/音频上传转写和最终文本回复朗读；它不是独立业务页面。支持临时转写、最终确认、停止、取消和新输入打断，不保存原始音频。

## 复用、协议与配置

以 Apache-2.0 的 `dsh-talk@0.1.2` 及 `dsh-speech-plugin` 的生命周期设计为基线，来源与改动见 `NOTICE` 和 `LICENSES/`；新增 Qianwen realtime provider。服务端使用 `MODEL_ASR_*`、`MODEL_TTS_*`、`ASR_MODEL=qwen3-asr-flash-realtime`、`TTS_MODEL=qwen3-tts-instruct-flash-realtime`，绝不读取 `SILICONFLOW_*`。会话协议覆盖 ready、音频块、临时/最终转写、TTS 块、停止、打断、完成和错误。

## 数据、卸载与改进

只把最终转写、回复、模型名和耗时交给当前账号 session。上游 WebSocket、AbortController、流和浏览器音频节点在停止、页面卸载或 Cordis 卸载时释放。新增 provider 应复用同一打断协议并保持密钥只在服务端。运行 GerClaw contract test，再用浏览器真实录音、标准音频上传、朗读、停止和打断。非 localhost 录音要求可信 HTTPS。
