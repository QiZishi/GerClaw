# @gerclaw/prescription

## 职责

生成用药、运动、营养、心理、康复五段式个体化建议，并附证据编号、免责声明、复核标识和确定性用药审查；不实现通用模型、RAG、文件或导出能力。

## 复用、接口与状态

复用 DSH LLM、`@gerclaw/local-rag` 和 `@gerclaw/medication-review`。公开 `PrescriptionRequest`、`PrescriptionReport`、`EvidenceSource` 等领域类型和 `prescription` 服务。模型只能引用请求传入的本账号证据；规范化报告由 App 写入 session events 和 deliverables。

五大处方在原生对话中收集资料，不使用独立表单。`PrescriptionIntakeState` 保存健康目标、当前问题、当前用药和至多 10 份上传资料引用；确定性状态机每轮只返回一个缺失问题，最多进行 5 轮。字段完整后才构造 `PrescriptionRequest`，模型输出必须通过药物、运动、营养、心理、康复五章固定结构和证据引用校验，否则重试一次后明确失败，不产生模拟结果。

## 生命周期、改进与测试

模型请求受 AbortSignal 管理，插件卸载会中止未完成工作。扩展输入字段时同时更新 intake 状态、缺失问题和 request 映射；不要把缺字段判断交给模型，也不要恢复独立表单。扩展输出时保持五段结构和证据约束，不得接受模型虚构引用。运行 GerClaw contract test，并用原 GerClaw 代表输入进行真实主模型对照。输出是辅助决策建议，不替代诊断或处方权。
