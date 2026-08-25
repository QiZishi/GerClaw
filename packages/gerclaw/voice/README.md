# @gerclaw/voice

## 职责

为智能对话提供麦克风录音转写和最终文本回复朗读；它不是独立业务页面。支持临时转写、最终确认、停止、取消和新输入打断，不保存原始音频，也不提供音频文件上传入口。

## 复用、协议与配置

以 Apache-2.0 的 `dsh-talk@0.1.3` 及 `dsh-speech-plugin` 的生命周期设计为基线，来源与改动见 `NOTICE` 和 `LICENSES/`。本包不保存供应商凭据，也不实现模型协议；它通过 Cordis `inject: speech` 消费 `@gerclaw/speech` 定义的可替换服务。当前提供方由独立 Loader 行 `@gerclaw/speech-qianwen` 提供。

本包注册账号 Host 内的 ASR upgrade、TTS 流式 HTTP、`talk` Remote 和 `talk:speech` projection。会话协议覆盖临时/最终转写、TTS 完成、停止、打断和错误。

## 数据、卸载与改进

只把最终转写、回复、模型名和耗时写入当前账号 session；原始音频不落盘。AbortController、HTTP 流、缓存和浏览器音频节点在停止、页面卸载或 Cordis 卸载时释放。禁用 `speech` 提供方时，本包由 Loader 级联卸载，恢复后自动重新激活。

运行 `packages/gerclaw/voice/tests` 后，再用真实账号 Host 验证录音、朗读、停止和打断。非 localhost 录音要求可信 HTTPS。
