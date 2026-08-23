# @gerclaw/cga

## 职责

提供 PHQ-9、SAS、PSQI、Mini-Cog、MMSE 五种量表的题目定义、确定性计分、分级、安全提示和历史比较；不调用模型、RAG 或外部服务，也不负责页面和持久化。

## 接口、数据与生命周期

公开 `CgaKind`、`CgaAssessment`、`CgaResult` 与 `cga` 服务。答案由当前账号的 App/session 保存，插件自身不建立跨账号存储、监听或定时器，卸载时无外部资源残留。

## 改进与测试

更新量表时必须同步题序、取值边界、计分版本和风险阈值，并保留来源说明；不要用模型替代确定性计算。运行 `pnpm exec vitest run packages/gerclaw/cga/tests/cga.spec.ts` 和浏览器逐题边界回归。结果用于辅助筛查，不替代诊断。
