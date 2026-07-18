# Orchestration

`ChatTurnCoordinator` centralizes the durable shell of a chat turn:

```text
Trace start/replay → session lease → feature-owned turn → terminal Trace
```

Feature modules retain prompt/context construction and all domain work. The
coordinator receives callbacks for replay, execution and terminal failure so it
can enforce one owner and one terminal outcome without duplicating the Agent
Harness or introducing an additional model call.

## 维护与演进

**可安全改进。** 可增加协调指标、明确 checkpoint 恢复钩子和更丰富的 feature callback；领域 prompt、RAG、Memory、模型和临床副作用仍由 feature owner 实现，避免在 coordinator 复制第二个 workflow engine。

**不可破坏的契约。** 一次 turn 只能有一个 lease owner 和一个 terminal Trace；replay 不能再次付费/写消息，取消/失败不能覆盖新 owner。不得在本模块读取用户正文、图片或模型输出，也不得新增第二次模型调用。

**性能与回归验收。** 覆盖 trace start/replay、lease 竞争、owner 接管、取消、异常和唯一终态；与 Chat 集成测试一起运行。10 并发同 session 需证明最多一个执行者，其余可重放或受控拒绝；记录 lease 等待、终态提交和重放 p95。
