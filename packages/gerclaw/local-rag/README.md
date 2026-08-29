# @gerclaw/shared-knowledge

## 职责

把根目录固定 GerClaw 知识库建立为一份共享、版本化、只读索引，返回可回溯到原文的定位与片段；不处理账号上传资料，不实现文件上传、文档解析或跨账号索引。

## 复用、配置与接口

以固定版 `dsh-library@0.1.3` 为算法底座，由同一 isolate 内的 `@gerclaw/library-dsh-runtime` 注入并复用其分块、embedding 和混合检索。存储、SQLite、storage-domain 和 subprocess 由 Profile/Loader 装配，本包不导入或实例化 `LibraryStore` 或 backend。SiliconFlow 只承担 embedding 与分片 rerank。公开 `gerclawSharedKnowledge` 服务。

## 数据、卸载与改进

索引数据位于根目录 `.gerclaw/shared-rag/index.sqlite`，内容清单与路由按 SHA-256 版本保存；新版本验证完成后原子更新 `current.json`，失败不会改动上一成功指针。共享索引和账号私有资料分别由独立 isolate 内的 runtime provider 持有，`local-rag` 只注入 `gerclawLibraryRuntime`；AbortSignal 与请求由 Cordis effect 回收。账号私有资料由 `@gerclaw/library-dsh` 独立保存，最终合并由 `@gerclaw/rag` 完成。外部 embedding/rerank 不可用时检索明确失败，不伪造结果。

`tests/shared-index.spec.ts` 核验 437 份原文清单和分片边界，`tests/loader-invariant.spec.ts` 验证真实 Loader 的 pending、级联卸载、恢复与回滚，`tests/real-rag.spec.ts` 使用真实 SiliconFlow 和 READY 索引验证来源回溯与账号私有资料隔离。
