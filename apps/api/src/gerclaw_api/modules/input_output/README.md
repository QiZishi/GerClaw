# Input / Output

`ProductionInputOutputModule` 是 Chat 的生产边界：在 Trace、持久化和
Harness 之前重新验证并规范化已限长的文本（Unicode NFKC、换行统一、去首尾空白、
拒绝控制字符和重复附件引用）；在 SSE 终态前重新验证 `AgentResponse`，只投影公开
文本、引用和安全决定。内部 `structured`、模型/工具状态、prompt 或计费元数据不能
通过该模块进入浏览器或语音通道。

该模块不调用 Provider、不解析文件、不作医疗判断。附件字节/MIME 验证、文档解析、
ASR/TTS 和临床 workflow 分别仍由其专属服务边界负责。单次 Chat 文本限制为 4,000
字符；语音公开文本限制为 4,000 字符。
