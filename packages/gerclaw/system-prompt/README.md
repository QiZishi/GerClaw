# @gerclaw/system-prompt

## 职责

提供 GerClaw 专属 system prompt，定义健康助手定位、五大处方流程、CGA、安全提示、证据引用、Plan/Goal 协作和辅助决策边界；不继承 DSH 开发者提示语，也不实现业务计算。

## 接口、状态与生命周期

公开 `GERCLAW_SYSTEM_PROMPT` 并向 DSH system-prompt 服务提供 GerClaw persona。Profile 停用默认提示语插件，App 也以该常量作为唯一兜底。提示语不保存账号数据，卸载无外部资源。

## 改进与测试

变更时检查是否影响医疗边界、引用规则、医患功能一致性及工具调用。运行 GerClaw contract test 和真实模型对话，确认回答不出现 DSH 开发者身份或内部结构。
