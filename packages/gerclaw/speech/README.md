# GerClaw Speech Service

本包只定义可替换的 `SpeechProvider` 服务、音频块类型和版本化语音事件，不连接任何模型，也不注册页面或网络路由。

提供方继承 `SpeechProvider` 并发布 `speech`；消费方通过 Cordis `inject` 声明依赖。服务包含 ASR upgrade 接管、TTS PCM 流和不含密钥的模型信息。依赖等待、级联卸载、失败回滚与恢复激活均由 DSH Loader 管理，禁止消费方直接导入或实例化具体提供方。

扩展时新增独立 provider 包与 Loader 行，不修改本定义。测试至少要证明缺失 provider 时消费方 pending、禁用时路由和流被清理、恢复时新 fiber 激活。
