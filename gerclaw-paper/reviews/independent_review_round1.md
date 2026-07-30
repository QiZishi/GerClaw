# Independent review — round 1

Reviewer: fresh-context Codex child agent
Recommendation: **Reject**

## 1. 论文摘要

本文提出 GerClaw，一个面向老年患者和老年科医生的预部署医疗智能体原型，并把验证拆成三个对象及时间尺度：

- `ClaimCheck`：临床主张与本轮证据记录绑定，无证据时改写或追问；
- `RunCommit`：Redis owner lease、PostgreSQL fencing token 与事务终态提交；
- `UpdateGate`：冻结候选、无网络沙箱、baseline/candidate 配对评测、sealed attestation、人工签名和原子晋升。

论文报告现有 40 个确定性回归样例全部通过，并反复强调它们只是软件合同检查，不是临床实验，也不证明诊断准确性、安全性或患者获益。

总体判断：三边界框架很适合 workshop，但论文把部分“接口/合同代码”写成了“已实现的独立验证机制”，且核心 `ClaimCheck` 的实际强制范围窄于论文定义。当前证据不足以支持主要实现贡献。

## 2. Strengths

1. **Venue fit 很强。** 将 agent verification 分成 claim、run、update 三个 commit boundary，直接回应“Who Verifies the Agents?”主题；“不同时间尺度上的 linked commit protocols”是清楚且有讨论价值的系统视角。
2. **临床证据边界在正文中总体克制。** 摘要、工程证据、限制和结论都明确排除了临床安全、诊断准确率和患者获益主张。
3. **40/40 没有被正文直接伪装成临床实验。** 论文明确称其为 curated software regressions、非独立临床样例，并说明不能做统计推断或跨系统比较。
4. **RunCommit 是三项中证据最扎实的一项。** 实际代码包含 Redis compare-and-renew、PostgreSQL fencing/trace 校验、共享事务中的消息/审计/Trace 提交，以及 commit 后才向客户端公开缓冲事件。
5. **限制和伦理讨论较完整。** 对 subgroup、隐私、部署 trust roots、datastore assumptions、误导性可信感和未来 clinician-authored evaluation 的讨论较具体。
6. **PDF 完整且没有裁切或重叠。** 四张正式图均嵌入主 PDF；整体阅读顺序清晰。

## 3. Weaknesses

### CRITICAL

1. **中心 `ClaimCheck` 主张超出实际强制能力。**

论文把 gate 定义为对“sentence-level direct clinical claim”逐项保留或不确定性改写，并称 unsupported statements 都会被 qualify。实际代码只对一组狭窄的确定性诊断正则做改写。对一般用药建议、风险判断或其他临床陈述，marker audit 可以将其记为 unbound，但终态并不会因此拒绝或改写。

此外，所谓 support 实际只验证同一 segment 内存在范围合法的 `[E/W]` marker，并不验证 marker 与主张的语义关系。论文承认不验证 entailment，但仍把“所有 unsupported direct claims 会被 qualify”写成已实现的软件不变量，边界不成立。

2. **UpdateGate 把签名合同写成了已实现的独立 verifier/effect。**

论文称实现了“out-of-process sealed evaluator independently recomputes the gate”和“distinct Ed25519 service”。实际情况是：

- `SealedGatePayload` 接收调用方预先构造的 hidden-case、threshold、latency 等布尔值；`AttestationKeyring.sign()` 只校验身份与公开 paired report 后签名，没有任何 sealed case runner 或 hidden threshold computation。
- `HumanApprovalSigner` 是同一 Python package 内可直接调用的类；“单独认证服务”只存在于 docstring/部署约定。
- 唯一真实 paired runner 只允许 `routing.strategy`，并仅运行四个硬编码路由样例——每个 slice 一个。
- 项目活跃计划仍将 sealed evaluator、offline evaluation 和 promotion control plane 列为进行中。

因此，当前源码支持“冻结、沙箱、公开 routing gate、签名 envelope 和 Git ref transaction 的合同库”，不支持论文所写的已集成独立验证效果。

### MAJOR

3. **40/40 没有覆盖论文最核心的 run/update 贡献。**

七个 family 是 emergency、output rewrite、privacy、medication、memory、runtime-profile 和 skill-draft；没有 stale-worker takeover、事务回滚、唯一终态、sealed evaluation、human approval 或 atomic promotion case。因此 40/40 不能作为三边界 architecture 的整体 executable safety case。

4. **工程审计不可独立复现，且 provenance 过弱。**

提交不提供匿名代码；内部 audit 没有 commit SHA、依赖锁摘要、环境、原始 CLI 输出或输出哈希；`external_model_or_rag=false` 是 CLI 直接写死的字段，不是通过 egress interception 得出的审计结论。

5. **缺少集中、可检验的 threat model。**

需要明确 candidate、controller、Docker host、Git refs、Redis/PostgreSQL、signing key、audit mirror 分别可能被谁控制，以及哪些性质在 key compromise、host compromise、network partition 下不成立。

6. **Related Work 不足以支撑新颖性定位。**

缺少与 fencing/linearizability、transactional outbox/event sourcing、software supply-chain attestation、TUF/in-toto/SLSA、assurance cases、ML regression gating 和 signed release ledger 的系统比较。

7. **图 1、2、4 含有会扩大主张的视觉语义。**

- 图 1 把 Claim→Run→Update 画成同一条串行 per-turn pipeline，但 Update 实际是生产 API 之外的离线域。
- 图 2 使用 “Safe Terminal Output” 和 “Validated SSE response”，与“只验证结构、不能证明临床安全或 entailment”的正文冲突。
- 图 4 把 sealed evaluator 与 human approver 画成已运行的独立角色，源码只实现 envelope/class contract。

### MINOR

8. **若干术语与计数不够精确。**

`retain-qualified` 容易让人误以为做过语义资格审查。正文说“五个 recognized emergency patterns”，实际是五个 positive cases、六个 red-flag code pattern，胸痛/呼吸困难共处一个 case。PDF 中图 2、3 的小标签在正常缩放下也偏小。

## 4. Claim–evidence 边界核验结论

| 论文主张 | 判定 |
|---|---|
| 面向老年患者/医生的 Web prototype | 部分支持：是产品与架构事实，不是部署证据 |
| Browser→server-only BFF→FastAPI/AgentScope | 支持为当前架构描述 |
| Claim 与当前证据逐句绑定，unsupported claim 必改写 | 不支持完整口径；一般临床主张未 fail closed |
| 红旗可在模型前短路 | 支持窄口径 |
| Stale worker 不能提交终态 | 较强支持 |
| Frozen commit 在无网络只读 Docker 中运行 | 支持合同和 routing 实现 |
| Baseline/candidate 同 runner、四 slices | 仅支持 routing |
| Sealed evaluator 独立运行隐藏用例并重算 gate | 不支持 |
| 独立人工服务批准 exact artifact | 仅支持签名 envelope |
| Promotion/rollback 使用签名记录和原子 Git refs | 支持库级合同 |
| 40/40 across seven families | 数量支持，解释需收窄 |
| CGA/voice/prescription 未统一、整体未 release complete | 支持且披露正确 |

## 5. 评分

- 新颖性：5/10
- Venue fit：9/10
- 清晰度：7/10
- 可复现性：3/10
- 伦理：8/10

## 6. 建议结论

**Reject**

理由不是缺少临床实验；对该 workshop，预临床 systems blueprint 完全可以成立。主要问题是两项中心实现贡献与源码不一致：`ClaimCheck` 没有对论文所定义的所有 unsupported clinical claims 执行 qualify/fail-closed；`UpdateGate` 的 sealed evaluator、独立人工服务和一般 candidate coverage 主要仍是合同/类型，而非论文叙述的已实现独立执行链。

若把论文明确降格为“reference contracts + partial implementation case study”，或补齐真实独立 evaluator 和端到端证据，稿件会很适合本 workshop。

## 7. 优先修改建议

1. 修正 ClaimCheck 的真实性：收窄为“确定性诊断措辞改写 + citation-marker audit”。
2. 把 UpdateGate 分层写清：已执行 routing runner、已实现签名/晋升合同、尚未实现或部署的 sealed evaluator 与 human approval service。
3. 补充中央机制证据；若本稿不做新增实验，则不得声称 40/40 覆盖三边界。
4. 升级 40/40 audit provenance，或把可复现性限制写得更明确。
5. 重画图 1、2、4，区分不同时间尺度、结构验证与临床安全、implemented 与 contract-only。
6. 增加集中 threat model 和 trusted-computing-base 表。
7. 扩展 fencing/transaction finality、attested software supply chain、assurance cases 和 ML regression gating 相关工作。
8. 修正 checklist 与术语计数。
