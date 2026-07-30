"""Trusted object classification and component-charter manifest."""

# ruff: noqa: RUF001 -- Chinese charter text intentionally uses CJK punctuation.

from __future__ import annotations

from types import MappingProxyType

from gerclaw_api.modules.agent_harness.evolution_governance.contracts import (
    ComponentCharter,
    EvolutionObjectRule,
)


def _rule(
    object_kind: str,
    *,
    track: str,
    authority: str,
    owner: str,
    update_policy: str,
    allowed_target_prefixes: tuple[str, ...] = (),
    candidate_readable: bool = True,
    candidate_writable: bool = True,
) -> EvolutionObjectRule:
    return EvolutionObjectRule.model_validate(
        {
            "object_kind": object_kind,
            "track": track,
            "authority": authority,
            "owner": owner,
            "update_policy": update_policy,
            "allowed_target_prefixes": allowed_target_prefixes,
            "candidate_readable": candidate_readable,
            "candidate_writable": candidate_writable,
        }
    )


OBJECT_RULES = tuple(
    [
        _rule(
            "memory.preference",
            track="mutable",
            authority="presentation_only",
            owner="user",
            update_policy="online_revisioned",
            allowed_target_prefixes=("memory://preferences/",),
        ),
        _rule(
            "memory.workspace_habit",
            track="mutable",
            authority="presentation_only",
            owner="user",
            update_policy="online_revisioned",
            allowed_target_prefixes=("memory://workspace/",),
        ),
        _rule(
            "memory.clinical_fact",
            track="mutable",
            authority="untrusted_user_context",
            owner="user",
            update_policy="online_revisioned",
            allowed_target_prefixes=("memory://clinical/",),
        ),
        _rule(
            "skill.presentation",
            track="mutable",
            authority="presentation_only",
            owner="skill_owner",
            update_policy="online_revisioned",
            allowed_target_prefixes=("skill://presentation/",),
        ),
        _rule(
            "skill.retrieval",
            track="mutable",
            authority="bounded_retrieval",
            owner="skill_owner",
            update_policy="online_revisioned",
            allowed_target_prefixes=("skill://retrieval/",),
        ),
        *(
            _rule(
                kind,
                track="immutable",
                authority=authority,
                owner="trusted_offline_controller",
                update_policy="offline_proposal_only",
                allowed_target_prefixes=(prefix,),
            )
            for kind, authority, prefix in (
                ("skill.clinical", "clinical_guidance", "skill://clinical/"),
                ("skill.tooling", "control_plane", "skill://tooling/"),
                ("prompt.policy", "control_plane", "policy/prompt/"),
                ("routing.strategy", "control_plane", "policy/routing/"),
                ("planning.strategy", "control_plane", "policy/planning/"),
            )
        ),
        *(
            _rule(
                kind,
                track="immutable",
                authority="control_plane",
                owner="sealed_release_controller",
                update_policy="sealed_controller_only",
                candidate_readable=readable,
                candidate_writable=False,
            )
            for kind, readable in (
                ("harness.core", True),
                ("governance.policy", True),
                ("component.charter", True),
                ("safety.guardrail", True),
                ("runtime.permission", True),
                ("auth.policy", True),
                ("evaluator.sealed", False),
                ("sealed.case", False),
                ("approval.key", False),
                ("attestation.key", False),
                ("audit.log", False),
                ("release.ref", False),
                ("deployment.credential", False),
            )
        ),
    ]
)


def _charter(
    component: str,
    purpose: str,
    *,
    invariants: tuple[str, ...],
    mutable: tuple[str, ...],
    protected: tuple[str, ...],
    evaluator: str,
) -> ComponentCharter:
    return ComponentCharter(
        component=component,
        core_purpose=purpose,
        invariants=invariants,
        mutable_content=mutable,
        protected_mechanisms=protected,
        sealed_evaluator_ids=(evaluator,),
    )


COMPONENT_CHARTERS = (
    _charter(
        "harness",
        "组合已治理组件并投影公开事件，不复制任何领域能力或持久化事实源。",
        invariants=("只经 Protocol/依赖注入组合", "不公开 private chain-of-thought"),
        mutable=("公开阶段摘要文案",),
        protected=("领域所有权边界", "安全与终态门禁"),
        evaluator="charter.harness.v1",
    ),
    _charter(
        "routing",
        "在首次模型调用前按风险与复杂度选择 Quick、Standard、Deep 或 Emergency。",
        invariants=("Emergency 永远优先于 Quick", "红旗路径禁止模型调用"),
        mutable=("非安全路由阈值候选",),
        protected=("红旗检测", "Emergency 优先级"),
        evaluator="charter.routing.v1",
    ),
    _charter(
        "planning",
        "生成有界、无环、依赖可验证且受预算约束的动态执行计划。",
        invariants=(
            "依赖无环",
            "节点状态持久化后才能执行",
            "执行前预算预检",
            "恢复只继续 pending/failed 节点",
            "必问项和治疗前提不能跳过",
        ),
        mutable=("离线评测后的规划策略",),
        protected=("预算门禁", "fallback/checkpoint 语义"),
        evaluator="charter.planning.v1",
    ),
    _charter(
        "clinical_state",
        "保存有来源的临床事实、未知项与冲突，维持确认状态的语义边界。",
        invariants=("unknown 不等于 negative", "冲突不能静默覆盖", "模型推测不能成为 confirmed"),
        mutable=("受信来源支持的事实内容",),
        protected=("provenance", "确认与冲突状态机"),
        evaluator="charter.clinical_state.v1",
    ),
    _charter(
        "context_snapshot",
        "冻结一次 Run 足以解释、恢复和容量审计的 actor-scoped 上下文。",
        invariants=(
            "恢复不重读当前可变状态",
            "模型前盘点全部来源",
            "只压缩历史与摘要",
            "冻结 source_hash 和 before/after budget",
            "模型压缩失败使用确定性降级",
        ),
        mutable=("在线会话内容",),
        protected=("快照身份校验", "安全输入与输出预留"),
        evaluator="charter.context_snapshot.v1",
    ),
    _charter(
        "run_lifecycle",
        "维护单调事件、唯一真正终态、中断恢复、取消幂等和 worker fencing。",
        invariants=(
            "真正终态无出边",
            "interrupted 可恢复且非终态",
            "sequence 单调",
            "取消和恢复幂等",
            "旧 worker 禁止写终态",
            "非致命后处理失败保留正文",
        ),
        mutable=("公开恢复摘要",),
        protected=("状态机", "sequence/fencing"),
        evaluator="charter.run_lifecycle.v1",
    ),
    _charter(
        "evidence",
        "把每项医学主张绑定到实际采用文本、locator、来源、状态与适用范围。",
        invariants=("任意证据不能解锁无关主张", "无法核验时不得伪造 citation"),
        mutable=("经 admission 的证据内容",),
        protected=("主张绑定校验器", "最低相关性门禁"),
        evaluator="charter.evidence.v1",
    ),
    _charter(
        "plugin_runtime",
        "按可执行 Manifest 组合能力，并在 owner 调用前后验证输入、输出与复用范围。",
        invariants=("Manifest schema 必须实际执行", "能力不能扩大 Runtime 权限"),
        mutable=("低风险能力内容版本",),
        protected=("owner/schema/共享结果边界",),
        evaluator="charter.plugin_runtime.v1",
    ),
    _charter(
        "evolution_signals",
        "在线只记录去内容化运行信号，为隔离离线评测提供非内容输入。",
        invariants=("不记录对话/证据/身份正文", "信号 sink 无生产行为修改权限"),
        mutable=("去内容化度量值",),
        protected=("隐私 allowlist",),
        evaluator="charter.evolution_signals.v1",
    ),
    _charter(
        "memory",
        "随用户使用在线 CRUD 有来源、有版本的长期事实和偏好，并安全召回。",
        invariants=("内容可在线 CRUD", "用户删除立即停止召回", "推测不能升级 confirmed"),
        mutable=("用户事实", "偏好", "工作区习惯"),
        protected=("隔离/加密", "确认/冲突/revision/tombstone", "低权限注入"),
        evaluator="charter.memory.v1",
    ),
    _charter(
        "skill",
        "注册、加载、执行和版本化专业程序性知识，同时维持工具与数据权限边界。",
        invariants=(
            "低风险内容可在线版本化",
            "Skill 不能自行扩大工具/数据/临床权限",
            "在线变更验证 schema/allowlist/预算/来源",
            "危险变更自动转 immutable 提案",
        ),
        mutable=("表达策略", "受限检索策略", "用户工作区流程"),
        protected=("风险分类器", "工具许可", "签名与 sealed tests"),
        evaluator="charter.skill.v1",
    ),
    _charter(
        "runtime",
        "作为唯一真实工具执行边界校验 schema、权限、permit、预算、超时与审批。",
        invariants=("未知工具/版本 fail closed", "每次调用执行前后校验"),
        mutable=("显式受限工具配置",),
        protected=("权限引擎", "审批与预算门禁"),
        evaluator="charter.runtime.v1",
    ),
)

REQUIRED_CHARTERS_BY_OBJECT_KIND = MappingProxyType(
    {
        "routing.strategy": ("charter.routing.v1",),
        "planning.strategy": ("charter.planning.v1",),
        "prompt.policy": ("charter.harness.v1", "charter.planning.v1"),
        "skill.clinical": ("charter.plugin_runtime.v1", "charter.skill.v1"),
        "skill.tooling": ("charter.plugin_runtime.v1", "charter.skill.v1"),
    }
)
