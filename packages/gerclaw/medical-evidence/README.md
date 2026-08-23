# @gerclaw/medical-evidence

## 职责

查询 PubMed、openFDA 和 MedlinePlus 的公开医学资料并规范化为统一证据；不引入 `dsh-medseek` 的 persona、职业限制、PHI 门禁或品牌，也不替代本地知识库。

## 来源、接口与数据

本插件从 Apache-2.0 的 `dsh-medseek@0.1.1` provider 思路裁剪，来源与修改记录见 `NOTICE`。公开 `MedicalEvidence` 与 `medicalEvidence` 服务。仅保存任务需要的标题、摘要、来源和公开链接，不持有账号医疗档案。

## 生命周期、改进与测试

请求受当前任务 AbortSignal 管理，卸载后不保留连接或定时器。新增数据源必须提供稳定公开链接、超时和明确失败语义。运行 GerClaw contract test，并真实打开三个来源的返回链接。外部服务故障会如实报错，不降级为模拟证据。
