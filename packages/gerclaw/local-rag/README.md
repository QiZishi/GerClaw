# @gerclaw/shared-knowledge

## 职责

把根目录固定 GerClaw 知识库建立为一份共享、版本化、只读索引，返回可回溯到原文的定位与片段；不处理账号上传资料，不实现文件上传、文档解析或跨账号索引。

## 复用、配置与接口

以固定版 `dsh-library@0.1.3` 为源码底座，复用其 `LibraryStore`、分块、embedding 和混合检索算法。存储由 Profile 内同名 isolate group 装配的 DSH storage、storage-sqlite 与 storage-domain 提供，本包不实例化 backend。SiliconFlow 只承担 embedding 与分片 rerank。公开 `gerclawSharedKnowledge` 服务。

## 数据、卸载与改进

索引数据位于根目录 `.gerclaw/shared-rag/index.sqlite`，内容清单与路由按 SHA-256 版本保存；新版本验证完成后原子更新 `current.json`，失败不会改动上一成功指针。domain、AbortSignal 与请求由 Cordis effect 回收。账号私有资料由 `@gerclaw/library-dsh` 独立保存，最终合并由 `@gerclaw/rag` 完成。外部 embedding/rerank 不可用时检索明确失败，不伪造结果。

`tests/shared-index.spec.ts` 核验 437 份原文清单和分片边界，`tests/loader-invariant.spec.ts` 验证真实 Loader 的 pending、级联卸载、恢复与回滚，`tests/real-rag.spec.ts` 使用真实 SiliconFlow 和 READY 索引验证来源回溯与账号私有资料隔离。
