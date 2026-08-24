# GerClaw RAG

本包是 `gerclawRag` 的消费型 Cordis provider。它依次查询只读共享医学知识库与当前账号的私有资料库，避免一次请求产生竞争的 embedding 子进程；随后使用 `.env` 配置的 SiliconFlow rerank 合并结果，并保留 `knowledge-base`／`user` 来源。

它不创建 storage backend、不调用 `library_*` Tool、不读取其他账号目录，也不实现 embedding 或向量检索。缺失任一上游服务时由 Cordis 保持 pending；提供方卸载时本插件级联卸载，恢复后由 Loader 重新激活。所有在途 rerank 请求由插件 effect 的 `AbortController` 在卸载时取消。

真实检索验收由 `packages/gerclaw/local-rag/tests/real-rag.spec.ts` 承担。测试读取根目录 `.env`，使用 READY 共享索引和两个独立私有库，验证 SiliconFlow 检索、账号隔离以及 Loader 禁用和恢复；运行时设置 `GERCLAW_REAL_RAG=1`，测试不会把密钥写入配置、日志或产物。
