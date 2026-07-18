# Input / Output

`ProductionInputOutputModule` 是 Chat 的生产边界：在 Trace、持久化和
Harness 之前重新验证并规范化已限长的文本（Unicode NFKC、换行统一、去首尾空白、
拒绝控制字符和重复附件引用）；在 SSE 终态前重新验证 `AgentResponse`，只投影公开
文本、引用和安全决定。内部 `structured`、模型/工具状态、prompt 或计费元数据不能
通过该模块进入浏览器或语音通道。

该模块不调用 Provider、不解析文件、不作医疗判断。附件字节/MIME 验证、文档解析、
ASR/TTS 和临床 workflow 分别仍由其专属服务边界负责。单次 Chat 文本限制为 4,000
字符；语音公开文本限制为 4,000 字符。

## 维护与演进

**可安全改进。** 可新增版本化公开 DTO、Unicode 规则或输出格式；领域解释、附件二进制和 provider adapter 仍应留在其模块。每次新字段先写严格 schema、浏览器 Zod 与兼容/淘汰计划。

**不可破坏的契约。** 输入规范化必须在 Trace/持久化/Harness 之前，公开输出必须在 SSE 之前复验；不得让 `structured`、prompt、工具状态、计费或模型内部字段穿过此边界。4,000 字符限制及附件 UUID 去重不得由客户端绕过。

**性能与回归验收。** 对 Unicode、控制字符、超长文本、重复附件、未知输出字段和 SSE 投影做确定性回归；normalization 在最大合法输入下应线性且不阻塞 event loop。记录最大输入的 p95 和拒绝码分布，确保失败不回显内容。
