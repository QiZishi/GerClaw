# @gerclaw/local-rag

## 职责

把随账号复制的固定 GerClaw 知识库和用户已解析资料接入本地检索，返回可回溯到原文的定位与片段；不实现文件上传、文档解析或跨账号索引。

## 复用、配置与接口

复用 `dsh-library@0.1.3`、DSH storage/subprocess，固定知识库来源为根目录 `knowledge-base`；用户资料使用 `gerclaw-user` library。SiliconFlow 仅承担 embedding 和 rerank，读取 `SILICONFLOW_API_KEY`、`SILICONFLOW_URL`、`EMBEDDING_MODEL`、`RERANK_MODEL`。公开 `LocalRagConfig`、`LocalRagHit`、`LocalRagStatus` 与 `localRag` 服务。

## 数据、卸载与改进

索引位于当前账号独立数据目录，状态可重建；命令、AbortSignal 和 storage domain 由 Cordis effect 回收。更新知识库时只补缺失文件并进行哈希核验，冲突必须人工处理。运行 GerClaw contract test、真实索引和引用回溯测试。外部 embedding/rerank 不可用时检索会明确失败，不伪造结果。
