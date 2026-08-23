# @gerclaw/prescription

## 职责

生成用药、运动、营养、心理、康复五段式个体化建议，并附证据编号、免责声明、复核标识和确定性用药审查；不实现通用模型、RAG、文件或导出能力。

## 复用、接口与状态

复用 DSH LLM、`@gerclaw/local-rag` 和 `@gerclaw/medication-review`。公开 `PrescriptionRequest`、`PrescriptionReport`、`EvidenceSource` 等领域类型和 `prescription` 服务。模型只能引用请求传入的本账号证据；规范化报告由 App 写入 session events 和 deliverables。

## 生命周期、改进与测试

模型请求受 AbortSignal 管理，插件卸载会中止未完成工作。扩展输出时保持五段结构和证据约束，不得接受模型虚构引用。运行 GerClaw contract test，并用原 GerClaw 代表输入进行真实主模型对照。输出是辅助决策建议，不替代诊断或处方权。
