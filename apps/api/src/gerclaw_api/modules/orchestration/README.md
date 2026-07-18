# Orchestration

`ChatTurnCoordinator` centralizes the durable shell of a chat turn:

```text
Trace start/replay → session lease → feature-owned turn → terminal Trace
```

Feature modules retain prompt/context construction and all domain work. The
coordinator receives callbacks for replay, execution and terminal failure so it
can enforce one owner and one terminal outcome without duplicating the Agent
Harness or introducing an additional model call.
