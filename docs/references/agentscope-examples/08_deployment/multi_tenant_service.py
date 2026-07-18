"""
GerClaw 老年医疗 AI 平台 — 多租户 AgentService 示例

演示内容：
1. 多租户模式：家庭(family) / 社区(community) / 医院(hospital) 三类租户
2. 不同 tenant_id 使用不同的 Agent 配置（system_prompt、工具集、知识库）
3. 租户级并发限制（Semaphore）防止某租户耗尽资源
4. 租户隔离：租户间 Agent 实例、会话上下文、知识库互不干扰
5. DashScopeChatModel 从环境变量读取 API Key，不硬编码

运行：
    DASHSCOPE_API_KEY=sk-xxx python multi_tenant_service.py

租户场景说明：
    - family    : 家庭场景，老人/家属使用，侧重日常健康咨询、用药提醒、紧急呼救指引
    - community : 社区卫生服务中心，侧重慢病随访、健康档案查询、预约挂号
    - hospital  : 医院场景，医生使用，侧重 CGA 评估、用药审查、转诊建议
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# 1. 环境配置：DashScope API Key 从环境变量读取
# ---------------------------------------------------------------------------

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
if not DASHSCOPE_API_KEY:
    print("[WARN] 未设置 DASHSCOPE_API_KEY，将使用 mock 模式演示多租户逻辑")


# ---------------------------------------------------------------------------
# 2. 租户配置定义
# ---------------------------------------------------------------------------

@dataclass
class TenantConfig:
    """单个租户的配置，决定 Agent 行为。"""

    tenant_type: str                 # family / community / hospital
    tenant_id: str                   # 具体租户 ID，如 family:f001
    system_prompt: str               # 该租户 Agent 的系统提示词
    knowledge_base: list[str]        # 该租户可访问的知识库名称列表
    available_tools: list[str]       # 该租户可用的工具名列表
    max_concurrent_sessions: int     # 最大并发会话数
    temperature: float = 0.3         # 医疗场景温度偏低
    model_name: str = "qwen-plus"    # 默认模型；医院场景可用更强模型


# 三类租户的预设配置模板
TENANT_TEMPLATES: dict[str, dict[str, Any]] = {
    "family": {
        "system_prompt": (
            "你是 GerClaw 家庭健康助手，服务于居家老人及其家属。"
            "你的回答应该：\n"
            "1. 使用简单易懂的语言，避免专业术语，字号/语音场景友好；\n"
            "2. 优先回答日常健康问题（饮食、运动、用药提醒）；\n"
            "3. 遇到紧急情况（胸痛、呼吸困难、突然晕倒）立即指引拨打120；\n"
            "4. 不做诊断，只提供健康建议和就医指引；\n"
            "5. 每次回答末尾提醒『以上建议仅供参考，不能替代医生诊断』。"
        ),
        "knowledge_base": ["home_care_guide", "medication_reminder", "emergency_first_aid"],
        "available_tools": ["medication_reminder", "vital_signs_log", "emergency_call"],
        "max_concurrent_sessions": 10,
        "temperature": 0.5,
        "model_name": "qwen-plus",
    },
    "community": {
        "system_prompt": (
            "你是 GerClaw 社区健康管理助手，服务于社区卫生服务中心的医护人员。"
            "你的职责包括：\n"
            "1. 协助社区医生进行慢病随访（高血压、糖尿病、慢阻肺）；\n"
            "2. 提供健康档案查询和随访计划生成；\n"
            "3. 协助预约上级医院挂号、双向转诊；\n"
            "4. 生成健康教育内容和慢病管理报告；\n"
            "5. 回答公共卫生问题（疫苗接种、传染病防控）。"
        ),
        "knowledge_base": [
            "chronic_disease_management", "followup_protocols",
            "health_education", "referral_guidelines",
        ],
        "available_tools": [
            "health_record_query", "followup_schedule",
            "appointment_booking", "report_generator",
        ],
        "max_concurrent_sessions": 30,
        "temperature": 0.3,
        "model_name": "qwen-plus",
    },
    "hospital": {
        "system_prompt": (
            "你是 GerClaw 临床辅助助手，服务于医院医生。你的回答需要：\n"
            "1. 提供专业的医学信息支持（CGA老年综合评估、药物相互作用审查）；\n"
            "2. 辅助生成诊断建议和治疗方案参考；\n"
            "3. 引用临床指南和循证医学证据；\n"
            "4. 明确标注信息来源，提醒医生结合临床判断；\n"
            "5. 不直接下诊断结论，所有建议标记为『临床参考』。"
        ),
        "knowledge_base": [
            "cga_assessment", "drug_interaction", "clinical_guidelines",
            "geriatric_syndromes", "medication_review",
        ],
        "available_tools": [
            "cga_assessment", "drug_interaction_check",
            "lab_result_analysis", "referral_letter_gen",
            "prescription_support",
        ],
        "max_concurrent_sessions": 50,
        "temperature": 0.1,   # 临床场景温度最低
        "model_name": "qwen-max",  # 医院场景使用更强模型
    },
}


# ---------------------------------------------------------------------------
# 3. 租户管理器：管理租户配置、Agent 实例、并发控制
# ---------------------------------------------------------------------------

class TenantManager:
    """
    多租户管理器：
    - 注册/获取租户配置
    - 为每个租户维护独立的会话信号量（并发控制）
    - 模拟租户级 Agent 实例缓存
    """

    def __init__(self) -> None:
        self._tenants: dict[str, TenantConfig] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._agent_cache: dict[str, Any] = {}

    def register_tenant(self, tenant_type: str, tenant_id: str) -> TenantConfig:
        """注册一个租户实例。"""
        if tenant_type not in TENANT_TEMPLATES:
            raise ValueError(f"未知租户类型: {tenant_type}，支持: {list(TENANT_TEMPLATES.keys())}")

        template = TENANT_TEMPLATES[tenant_type]
        config = TenantConfig(
            tenant_type=tenant_type,
            tenant_id=tenant_id,
            system_prompt=template["system_prompt"],
            knowledge_base=list(template["knowledge_base"]),
            available_tools=list(template["available_tools"]),
            max_concurrent_sessions=template["max_concurrent_sessions"],
            temperature=template["temperature"],
            model_name=template["model_name"],
        )
        self._tenants[tenant_id] = config
        self._semaphores[tenant_id] = asyncio.Semaphore(config.max_concurrent_sessions)
        return config

    def get_tenant(self, tenant_id: str) -> TenantConfig:
        if tenant_id not in self._tenants:
            raise KeyError(f"租户未注册: {tenant_id}")
        return self._tenants[tenant_id]

    def get_semaphore(self, tenant_id: str) -> asyncio.Semaphore:
        return self._semaphores[tenant_id]

    def list_tenants(self) -> list[TenantConfig]:
        return list(self._tenants.values())

    async def get_or_create_agent(self, tenant_id: str, session_id: str):
        """
        获取或创建租户级 Agent（真实环境使用 agentscope.Agent）。
        这里用 mock 对象演示隔离逻辑：每个租户的 Agent 持有独立配置。
        """
        cache_key = f"{tenant_id}:{session_id}"
        if cache_key in self._agent_cache:
            return self._agent_cache[cache_key]

        config = self.get_tenant(tenant_id)

        # 尝试构建真实 Agent（如果 agentscope 可用且有 API Key）
        agent = None
        if DASHSCOPE_API_KEY:
            try:
                from agentscope.agent import Agent
                from agentscope.credential import DashScopeCredential
                from agentscope.model import DashScopeChatModel
                from agentscope.tool import Toolkit

                model = DashScopeChatModel(
                    credential=DashScopeCredential(api_key=DASHSCOPE_API_KEY),
                    model=config.model_name,
                    stream=True,
                    temperature=config.temperature,
                )
                agent = Agent(
                    name=f"gerclaw-{config.tenant_type}-agent",
                    system_prompt=config.system_prompt,
                    model=model,
                    toolkit=Toolkit(),  # 实际可注入 config.available_tools
                )
            except ImportError:
                agent = None

        if agent is None:
            # Mock Agent：仅记录配置，实际 reply 返回模拟回答
            agent = MockMedicalAgent(config)

        self._agent_cache[cache_key] = agent
        return agent


# ---------------------------------------------------------------------------
# 4. Mock Agent：模拟不同租户的医疗回答行为
# ---------------------------------------------------------------------------

class MockMedicalAgent:
    """模拟医疗 Agent，根据租户配置返回差异化回答。"""

    def __init__(self, config: TenantConfig) -> None:
        self.config = config
        self.name = f"gerclaw-{config.tenant_type}-agent"

    async def reply(self, message: str, session_id: str) -> str:
        """模拟非流式回复。"""
        await asyncio.sleep(0.05)  # 模拟 LLM 推理延迟
        return self._generate_reply(message)

    async def reply_stream(self, message: str, session_id: str):
        """模拟流式回复，逐字 yield。"""
        reply = self._generate_reply(message)
        for char in reply:
            yield char
            await asyncio.sleep(0.005)

    def _generate_reply(self, message: str) -> str:
        """根据租户类型生成差异化回复。"""
        msg = message.strip()
        tenant_type = self.config.tenant_type

        if tenant_type == "family":
            return self._family_reply(msg)
        elif tenant_type == "community":
            return self._community_reply(msg)
        elif tenant_type == "hospital":
            return self._hospital_reply(msg)
        return "您好，请问有什么可以帮助您的？"

    def _family_reply(self, msg: str) -> str:
        if "血压" in msg:
            return (
                "爷爷/奶奶您好！关于血压的问题，我给您几个简单建议：\n"
                "1. 先坐下休息10分钟，别紧张，再量一次血压；\n"
                "2. 如果高压超过160或低压超过100，或者有头晕头痛，赶紧叫家人带您去医院；\n"
                "3. 平时要按时吃降压药，不要自己停药；\n"
                "4. 少吃咸菜，每天盐不要超过一啤酒盖。\n"
                "以上建议仅供参考，不能替代医生诊断。"
            )
        if "药" in msg and ("忘" in msg or "漏" in msg):
            return (
                "忘记吃药了怎么办？很简单：\n"
                "1. 如果离下次吃药还有2小时以上，可以现在补上；\n"
                "2. 如果快到下次吃药时间了，就跳过这次，千万别吃两次；\n"
                "3. 降压药、降糖药漏服后要注意量血压/测血糖；\n"
                "4. 定个闹钟提醒自己，或者让家人帮忙提醒。\n"
                "以上建议仅供参考，不能替代医生诊断。"
            )
        return (
            "您好！我是您的家庭健康小助手 GerClaw。\n"
            "我可以帮您：\n"
            "- 解答日常健康小问题\n"
            "- 提醒按时吃药\n"
            "- 紧急情况告诉您怎么办\n"
            "您有什么不舒服，慢慢告诉我就好。\n"
            "以上建议仅供参考，不能替代医生诊断。"
        )

    def _community_reply(self, msg: str) -> str:
        if "随访" in msg or "慢病" in msg:
            return (
                "【社区慢病随访助手】\n"
                "根据慢病随访规范，建议本次随访包含以下内容：\n"
                "1. 测量血压、血糖、体重等基本体征；\n"
                "2. 询问用药依从性（是否按时按量服药）；\n"
                "3. 评估生活方式（饮食、运动、烟酒、睡眠）；\n"
                "4. 筛查并发症相关症状；\n"
                "5. 更新健康档案，预约下次随访时间（建议1-3个月）。\n"
                "如需预约上级医院转诊，可使用预约挂号工具。"
            )
        if "档案" in msg or "健康" in msg:
            return (
                "【健康档案查询】\n"
                "该居民健康档案已关联：高血压管理、2型糖尿病管理。\n"
                "最近一次随访：2026-06-15，血压138/82，血糖空腹6.8mmol/L。\n"
                "用药情况：氨氯地平5mg qd、二甲双胍500mg bid。\n"
                "建议：继续当前方案，3个月后复查糖化血红蛋白。"
            )
        return (
            "【社区健康管理助手】\n"
            "我可以协助社区医生进行：慢病随访、健康档案管理、预约挂号、健康教育。\n"
            "请提供居民姓名/档案号或具体操作需求。"
        )

    def _hospital_reply(self, msg: str) -> str:
        if "CGA" in msg or "评估" in msg or "综合评估" in msg:
            return (
                "【CGA老年综合评估 - 临床参考】\n"
                "建议从以下6个维度进行评估：\n"
                "1. 日常生活能力（ADL/IADL量表）\n"
                "2. 认知功能（MMSE/MoCA量表）\n"
                "3. 情绪状态（GDS老年抑郁量表）\n"
                "4. 营养状况（MNA-SF量表）\n"
                "5. 跌倒风险（Morse跌倒量表）\n"
                "6. 共病与多重用药（用药审查）\n"
                "参考依据：《中国老年综合评估技术应用专家共识》。\n"
                "【临床参考】请结合临床实际判断。"
            )
        if "药" in msg and ("交互" in msg or "相互" in msg or "审查" in msg):
            return (
                "【药物相互作用审查 - 临床参考】\n"
                "请提供患者当前用药清单（通用名+剂量+频次）。\n"
                "常见老年高风险药物相互作用：\n"
                "- 华法林 + 阿司匹林/NSAIDs → 出血风险增加\n"
                "- ACEI + 螺内酯 → 高钾血症风险\n"
                "- 他汀类 + 贝特类 → 肌病风险\n"
                "- 苯二氮卓类 + 阿片类 → 呼吸抑制\n"
                "建议使用Beers标准和STOPP/START标准进行老年用药审查。\n"
                "【临床参考】具体请查阅药品说明书和最新临床指南。"
            )
        return (
            "【临床辅助助手】\n"
            "我可以协助医生进行：CGA老年综合评估、药物相互作用审查、"
            "检验结果分析、转诊建议生成。\n"
            "请输入患者信息或具体临床问题。\n"
            "【临床参考】所有建议请结合临床判断。"
        )


# ---------------------------------------------------------------------------
# 5. 多租户 Chat Service：统一入口 + 租户路由 + 并发控制
# ---------------------------------------------------------------------------

class MultiTenantChatService:
    """
    多租户聊天服务：
    - 根据 tenant_id 路由到对应租户的 Agent
    - 使用租户级 Semaphore 控制并发
    - 模拟 /api/chat 和 /api/chat/stream 两个端点
    """

    def __init__(self) -> None:
        self.tenant_manager = TenantManager()

    def setup_demo_tenants(self) -> None:
        """注册 GerClaw 三类演示租户。"""
        self.tenant_manager.register_tenant("family", "family:f001")
        self.tenant_manager.register_tenant("family", "family:f002")
        self.tenant_manager.register_tenant("community", "community:c001")
        self.tenant_manager.register_tenant("hospital", "hospital:h001")

    async def chat(self, tenant_id: str, session_id: str, message: str) -> dict[str, Any]:
        """
        非流式聊天接口（模拟 POST /api/chat）。
        返回完整回复 + 元信息。
        """
        config = self.tenant_manager.get_tenant(tenant_id)
        sem = self.tenant_manager.get_semaphore(tenant_id)

        async with sem:  # 租户级并发控制
            agent = await self.tenant_manager.get_or_create_agent(tenant_id, session_id)
            reply = await agent.reply(message, session_id)

        return {
            "tenant_id": tenant_id,
            "tenant_type": config.tenant_type,
            "session_id": session_id,
            "reply": reply,
            "model": config.model_name,
            "kb_accessible": config.knowledge_base,
        }

    async def chat_stream(self, tenant_id: str, session_id: str, message: str):
        """
        流式聊天接口（模拟 GET /api/chat/stream SSE）。
        逐字 yield 文本块。
        """
        config = self.tenant_manager.get_tenant(tenant_id)
        sem = self.tenant_manager.get_semaphore(tenant_id)

        async with sem:
            agent = await self.tenant_manager.get_or_create_agent(tenant_id, session_id)
            async for char in agent.reply_stream(message, session_id):
                yield char


# ---------------------------------------------------------------------------
# 6. 演示：模拟多租户请求
# ---------------------------------------------------------------------------

async def demo_multi_tenant() -> None:
    """演示三类租户的隔离效果和并发控制。"""
    service = MultiTenantChatService()
    service.setup_demo_tenants()

    print("=" * 60)
    print("GerClaw 多租户医疗 AgentService 演示")
    print("=" * 60)

    # 展示已注册租户
    print("\n[已注册租户]")
    for t in service.tenant_manager.list_tenants():
        print(f"  - {t.tenant_id}  type={t.tenant_type}  "
              f"max_concurrency={t.max_concurrent_sessions}  "
              f"model={t.model_name}  kb={t.knowledge_base}")

    # ---- 场景 1：家庭用户问血压问题 ----
    print("\n" + "-" * 60)
    print("[场景1] 家庭租户 family:f001 — 老人问血压")
    print("-" * 60)
    result = await service.chat(
        tenant_id="family:f001",
        session_id=f"sess_{uuid4().hex[:8]}",
        message="我量血压150/95，头有点晕，怎么办？",
    )
    print(f"[租户类型] {result['tenant_type']}")
    print(f"[使用模型] {result['model']}")
    print(f"[可访问KB] {result['kb_accessible']}")
    print(f"[回复]\n{result['reply']}")

    # ---- 场景 2：社区医生做慢病随访 ----
    print("\n" + "-" * 60)
    print("[场景2] 社区租户 community:c001 — 社区医生做慢病随访")
    print("-" * 60)
    result = await service.chat(
        tenant_id="community:c001",
        session_id=f"sess_{uuid4().hex[:8]}",
        message="我需要对张大爷做本季度高血压随访，请给出随访方案",
    )
    print(f"[租户类型] {result['tenant_type']}")
    print(f"[使用模型] {result['model']}")
    print(f"[可访问KB] {result['kb_accessible']}")
    print(f"[回复]\n{result['reply']}")

    # ---- 场景 3：医院医生做 CGA 评估 ----
    print("\n" + "-" * 60)
    print("[场景3] 医院租户 hospital:h001 — 医生请求 CGA 评估")
    print("-" * 60)
    result = await service.chat(
        tenant_id="hospital:h001",
        session_id=f"sess_{uuid4().hex[:8]}",
        message="对一位82岁女性患者进行CGA综合评估，需要覆盖哪些维度？",
    )
    print(f"[租户类型] {result['tenant_type']}")
    print(f"[使用模型] {result['model']}")
    print(f"[可访问KB] {result['kb_accessible']}")
    print(f"[回复]\n{result['reply']}")

    # ---- 场景 4：租户隔离验证 — 医院问漏服药物 vs 家庭问漏服 ----
    print("\n" + "-" * 60)
    print("[场景4] 租户隔离验证 — 同一问题在不同租户下的差异化回答")
    print("-" * 60)
    for tid in ["family:f001", "hospital:h001"]:
        result = await service.chat(
            tenant_id=tid,
            session_id=f"sess_{uuid4().hex[:8]}",
            message="老人忘记吃药怎么办？",
        )
        print(f"\n  >>> {tid} ({result['tenant_type']}):")
        # 只打印前两行作为对比
        first_lines = "\n".join(result["reply"].split("\n")[:3])
        print(f"  {first_lines}")

    # ---- 场景 5：SSE 流式输出演示（家庭租户） ----
    print("\n" + "-" * 60)
    print("[场景5] SSE 流式输出演示 — family:f002 询问用药")
    print("-" * 60)
    session_id = f"sess_{uuid4().hex[:8]}"
    print(f"[session_id] {session_id}")
    print("[SSE 流]", end="", flush=True)
    collected = ""
    async for ch in service.chat_stream(
        tenant_id="family:f002",
        session_id=session_id,
        message="忘记吃降压药了怎么办？",
    ):
        print(ch, end="", flush=True)
        collected += ch
    print("\n[流结束]")

    # ---- 场景 6：并发会话限制演示 ----
    print("\n" + "-" * 60)
    print("[场景6] 租户并发控制 — 模拟多个并发会话")
    print("-" * 60)

    async def one_session(idx: int):
        return await service.chat(
            tenant_id="family:f001",  # max_concurrent_sessions=10
            session_id=f"sess_concurrent_{idx}",
            message=f"第{idx}个并发会话测试",
        )

    # 家庭租户 max_concurrent_sessions=10，我们发 12 个并发任务
    tasks = [one_session(i) for i in range(12)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if not isinstance(r, Exception))
    print(f"  发起12个并发请求，成功完成: {success}，异常: {12 - success}")
    print("  （家庭租户并发限制=10，超出部分会排队等待，不会被拒绝）")

    print("\n" + "=" * 60)
    print("多租户演示完成。核心要点：")
    print("  1. tenant_id 决定 Agent 配置（system_prompt/KB/工具/模型）")
    print("  2. 每个租户独立 Semaphore 控制并发")
    print("  3. Agent 实例按 tenant_id:session_id 缓存，会话间隔离")
    print("  4. 生产环境通过 extra_agent_middlewares 工厂实现相同模式")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 7. 入口
# ---------------------------------------------------------------------------

async def main() -> None:
    """主入口：运行多租户演示。"""
    await demo_multi_tenant()


if __name__ == "__main__":
    asyncio.run(main())
