# GerClaw Library 服务定义

本包只定义三个可替换 Cordis 服务：账号私有资料库 `gerclawLibrary`、共享只读知识库 `gerclawSharedKnowledge` 与产品检索入口 `gerclawRag`。它不实现存储、索引、embedding、rerank、HTTP 路由或用户界面。

具体提供方必须由 DSH Loader/Profile 装配，消费方只注入这些服务，禁止跨包导入提供方实现。共享知识库与账号资料通过不同的 storage isolate 持久化；卸载、依赖等待与级联恢复由 Cordis 管理。
