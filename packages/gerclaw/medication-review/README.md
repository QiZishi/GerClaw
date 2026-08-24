# @gerclaw/medication-review

## 职责

确定性执行 GerClaw `medication-rules-v4`：30 条精确 DDI、4 类剂量阈值、重复用药、多药联用和有限 Beers 信号；不使用模型猜测药物关系，也不负责处方生成。

## 接口、数据与生命周期

公开 `MedicationReviewRequest`、`MedicationFinding`、`MedicationReview` 与 `medicationReview` 服务。输入和结果由当前账号 App/session 管理，插件本身无持久化、网络连接或后台资源。

## 改进与测试

修改规则必须保留可审计规则编号、精确匹配和边界用例，并同步处方附录测试。运行 `pnpm exec vitest run packages/gerclaw/medication-review/tests/review.spec.ts`。结果仅为复核提示，用户应由专业人员结合实际情况判断。
