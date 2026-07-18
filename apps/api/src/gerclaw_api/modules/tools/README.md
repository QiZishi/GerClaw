# Tools

外部工具调用的策略、安全检查和审计边界；实现必须在调用前后执行安全检查并写入 allowlisted Trace 事件。

## 维护与演进

**可安全改进。** 新工具应先在此定义最小 Protocol、输入/输出 schema、风险、幂等语义和可观测字段，再由 `runtime` registry 注入实际 delegate；保留 feature owner 的领域逻辑，不在工具层复制 workflow。

**不可破坏的契约。** 不得直接从模型或路由调用外部工具；所有调用必须经 Runtime capability、permit、timeout、大小校验和 allowlisted Trace。工具不得输出 credential、原始 provider body、PHI 或未经验证的副作用成功声明。

**性能与回归验收。** 每个工具必测 schema 拒绝、权限 deny/ask、超时、幂等重放、输出上限和审计字段；副作用工具还需 10 并发至多一次执行证明。记录 delegate p95、超时率和 permit 拒绝率。
