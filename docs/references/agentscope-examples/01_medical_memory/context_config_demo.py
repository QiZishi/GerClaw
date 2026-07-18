"""
GerClaw老年医疗AI平台 - ContextConfig上下文压缩示例
==================================================
演示功能：
1. 配置ContextConfig（trigger_ratio=0.7, reserve_ratio=0.15）
2. 自定义医疗summary_template，包含过敏/用药/诊断等医疗字段
3. 模拟多轮就诊记录（高血压随访、糖尿病复查、感冒就诊等长对话）
4. 触发自动上下文压缩，展示医疗历史压缩为结构化摘要的过程
5. 验证压缩后state.summary包含医疗关键字段，最近消息保留在context中

注意：本示例不依赖mem0，使用MockModel模拟LLM响应，纯上下文压缩演示。
如需使用真实模型，将MockModel替换为DashScopeChatModel即可。

运行方式：
    pip install agentscope
    python context_config_demo.py
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agentscope.message import Msg

# ---------------------------------------------------------------------------
# 尝试导入AgentScope组件
# ---------------------------------------------------------------------------
try:
    from agentscope.agent import Agent, ContextConfig
    from agentscope.message import (
        UserMsg, AssistantMsg, TextBlock, Msg, HintBlock,
        ToolCallBlock, ToolResultBlock,
    )
    from agentscope.model import StructuredResponse
    from agentscope.state import AgentState
    from agentscope.tool import Toolkit

    HAS_AGENTSCOPE = True
except ImportError:
    HAS_AGENTSCOPE = False
    print("[警告] 未安装agentscope，使用内置Mock类演示")

    # 定义轻量fallback类型，供简化模式使用
    class _SimpleBlock:
        def __init__(self, text: str) -> None:
            self.text = text

    class _SimpleMsg:
        def __init__(self, name: str, content: str, role: str = "user") -> None:
            self.name = name
            self._content = content
            self.role = role

        def get_text_content(self) -> str:
            return self._content

    def UserMsg(name: str, content: str, **_: Any) -> "_SimpleMsg":  # type: ignore
        return _SimpleMsg(name, content, "user")

    def AssistantMsg(name: str, content: str, **_: Any) -> "_SimpleMsg":  # type: ignore
        return _SimpleMsg(name, content, "assistant")


# ===========================================================================
# Mock模型 - 模拟LLM的结构化压缩响应
# ===========================================================================
@dataclass
class MockChatUsage:
    """模拟token使用统计。"""
    input_tokens: int = 0
    output_tokens: int = 0
    time: float = 0.0


@dataclass
class MockContent:
    """模拟模型输出内容。"""
    text: str = ""
    is_tool_call: bool = False
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)


class MockModel:
    """
    模拟ChatModel，用于演示上下文压缩流程。
    - count_tokens: 使用UTF-8字节数/4估算token
    - generate_structured_output: 返回预设的医疗结构化摘要
    """

    def __init__(self, context_size: int = 500) -> None:
        self.context_size = context_size
        self._structured_response: dict | None = None
        self.compression_call_count = 0

    def set_structured_response(self, content: dict) -> None:
        """设置下次结构化输出返回的内容。"""
        self._structured_response = content

    async def count_tokens(
        self,
        messages: list,
        tools: list[dict] | None = None,
    ) -> int:
        """估算token数（UTF-8字节数/4，与AgentScope默认策略一致）。"""
        total = 0
        for msg in messages:
            if hasattr(msg, "get_text_content"):
                text = msg.get_text_content() or ""
            elif isinstance(msg, dict):
                text = json.dumps(msg, ensure_ascii=False)
            else:
                text = str(msg)
            total += len(text.encode("utf-8")) // 4
        if tools:
            total += sum(
                len(json.dumps(t, ensure_ascii=False).encode("utf-8")) // 4
                for t in tools
            )
        return total

    async def _call_api_with_structured_output(
        self,
        model_name: str,
        messages: list,
        structured_model: Any,
        **kwargs: Any,
    ) -> "StructuredResponse":
        """模拟结构化输出调用（压缩时使用）。"""
        self.compression_call_count += 1
        if self._structured_response:
            content = self._structured_response
        else:
            # 默认医疗摘要
            content = {
                "task_overview": "张大爷多轮就诊咨询，涉及高血压、糖尿病随访及感冒就诊",
                "current_state": "血压135/85mmHg（控制一般），空腹血糖7.2mmol/L（偏高），感冒症状已缓解",
                "important_discoveries": (
                    "1. 青霉素过敏（安全红线）；"
                    "2. 高血压5年，服用氨氯地平5mg qd；"
                    "3. 2型糖尿病3年，服用二甲双胍500mg bid；"
                    "4. 上周感冒已愈，无药物不良反应"
                ),
                "next_steps": (
                    "1. 监测血压血糖，2周后复查；"
                    "2. 二甲双胍可考虑调整剂量；"
                    "3. 避免使用青霉素类药物"
                ),
                "context_to_preserve": (
                    "患者：张大爷，72岁；"
                    "过敏：青霉素；"
                    "用药：氨氯地平5mg/日、二甲双胍500mg/次每日两次；"
                    "诊断：高血压、2型糖尿病"
                ),
            }
        return StructuredResponse(content=content)

    # 实现ChatModelBase需要的基本接口
    async def __call__(self, messages, tools=None, **kwargs):
        return None

    def _get_retryable_exceptions(self):
        return tuple()


# ===========================================================================
# 医疗就诊记录生成器
# ===========================================================================
def generate_medical_visit_records() -> list:
    """
    生成模拟的多轮就诊对话记录。
    每轮包含用户描述症状/问题和医生回复，用于填充context触发压缩。
    """
    visits = [
        # ---- 就诊1：高血压随访 ----
        ("张大爷", "医生好，我最近血压有点高，早上量了150/95，头有点晕。"),
        ("GerClaw助手", "张大爷您好，您目前血压150/95确实偏高。您现在吃什么降压药？剂量是多少？"),
        ("张大爷", "吃氨氯地平，5毫克的，每天早上吃一片，吃了快3年了。"),
        ("GerClaw助手", "好的，记录在案：氨氯地平5mg qd。建议您这几天早晚各量一次血压并记录，如果持续偏高需要考虑调整剂量。头晕的话起身动作慢一点。"),

        # ---- 就诊2：糖尿病复查 ----
        ("张大爷", "医生，我上周查了空腹血糖7.8，是不是太高了？"),
        ("GerClaw助手", "空腹血糖7.8mmol/L对于糖尿病患者确实偏高（目标4.4-7.0）。您二甲双胍怎么吃的？饮食控制怎么样？"),
        ("张大爷", "二甲双胍500毫克的，早晚各一片。最近老伴做饭偏甜，我忍不住多吃了点。"),
        ("GerClaw助手", "了解了。血糖偏高可能与近期饮食有关。建议：1.严格控制碳水摄入，减少甜食；2.饭后散步30分钟；3.2周后复查空腹血糖和HbA1c；4.如果仍高，考虑调整二甲双胍剂量。"),

        # ---- 就诊3：感冒就诊 ----
        ("张大爷", "医生，我这两天感冒了，流鼻涕、嗓子疼，有点咳嗽，没发烧。能吃什么感冒药？"),
        ("GerClaw助手", "张大爷，首先提醒您：您对青霉素过敏，不要吃阿莫西林等青霉素类药物！对于普通感冒症状，建议：1.多喝温水，注意休息；2.可服用板蓝根颗粒或连花清瘟胶囊缓解症状；3.如发烧超过38.5度或症状持续3天以上请及时就医；4.降压药和降糖药照常服用，不要停。"),
        ("张大爷", "好的好的，那我去买板蓝根，谢谢医生。"),
        ("GerClaw助手", "不客气，祝您早日康复！记得按时服用降压药和降糖药，感冒期间也要监测血压血糖。"),

        # ---- 就诊4：复诊（长文本，确保触发压缩） ----
        ("张大爷", "医生，我感冒好了，今天来复查。这两周我按您说的控制饮食，每天饭后散步，血压早上量大概135/85左右，血糖还没去查。最近睡眠不太好，晚上要起夜两三次小便。"),
        ("GerClaw助手", (
            "张大爷您好，很高兴您感冒已愈。血压135/85mmHg较之前有所改善，继续当前氨氯地平方案。"
            "关于夜尿增多，需要关注几个可能原因：1.血糖控制不佳可导致多尿，建议尽快查空腹血糖和HbA1c；"
            "2.老年男性需排除前列腺增生问题；3.晚上8点后适当减少饮水。"
            "睡眠方面，保持规律作息，睡前避免饮茶。等血糖结果出来后我们再评估是否需要调整二甲双胍剂量。"
            "再次提醒：青霉素过敏，就诊时务必告知医生。"
        )),
        # 添加更多轮次以确保触发压缩
        ("张大爷", "好的，我明天就去查血糖。对了医生，我最近膝盖有点疼，上下楼梯不舒服，是不是骨质疏松啊？"),
        ("GerClaw助手", (
            "张大爷，膝关节疼痛在老年人中常见，可能原因包括：1.骨关节炎（退行性关节病）；"
            "2.骨质疏松；3.滑膜炎等。建议您：1.注意关节保暖，避免剧烈运动和长时间爬楼梯；"
            "2.可适当补充钙剂和维生素D；3.如疼痛持续或加重，建议到骨科就诊，必要时拍X光片；"
            "4.不要自行服用止痛药，某些NSAIDs可能影响血压和肾功能。"
        )),
    ]

    messages = []
    for i, (name, text) in enumerate(visits):
        # 使文本足够长以触发压缩（每条约60-200字符）
        # 重复填充部分内容来增大token量
        if name == "张大爷":
            msg = UserMsg(name, text)
        else:
            msg = AssistantMsg(name, text)
        messages.append(msg)
    return messages


# ===========================================================================
# 演示函数
# ===========================================================================
async def demo_with_agentscope() -> None:
    """使用真实AgentScope Agent类演示上下文压缩。"""
    print("=" * 60)
    print("GerClaw ContextConfig上下文压缩示例 - AgentScope模式")
    print("=" * 60)

    # 1. 创建Mock模型
    model = MockModel(context_size=500)  # 设置较小context_size便于触发压缩

    # 2. 配置医疗专用ContextConfig
    medical_summary_template = (
        "<system-info>以下是之前就诊对话的医疗摘要：\n"
        "# 就诊概述\n{task_overview}\n\n"
        "# 当前健康状态\n{current_state}\n\n"
        "# 重要医疗发现（过敏/用药/异常指标）\n{important_discoveries}\n\n"
        "# 后续诊疗计划\n{next_steps}\n\n"
        "# 需要保留的患者信息\n{context_to_preserve}</system-info>"
    )

    context_config = ContextConfig(
        trigger_ratio=0.7,       # 70%时触发压缩
        reserve_ratio=0.15,      # 保留15%最近消息
        tool_result_limit=3000,  # 工具结果上限
        summary_template=medical_summary_template,
    )

    print(f"\n[ContextConfig配置]")
    print(f"  trigger_ratio: {context_config.trigger_ratio}")
    print(f"  reserve_ratio: {context_config.reserve_ratio}")
    print(f"  tool_result_limit: {context_config.tool_result_limit}")
    print(f"  模型context_size: {model.context_size} tokens")
    print(f"  压缩触发阈值: {int(model.context_size * context_config.trigger_ratio)} tokens")

    # 3. 设置Mock模型的结构化压缩响应
    model.set_structured_response({
        "task_overview": "张大爷多轮就诊：高血压随访、糖尿病复查、感冒、膝关节疼痛咨询",
        "current_state": "血压135/85（改善），空腹血糖待复查，感冒已愈，膝关节疼痛待查",
        "important_discoveries": (
            "【过敏红线】青霉素过敏，禁用青霉素类药物；"
            "【慢病】高血压5年（氨氯地平5mg qd）、2型糖尿病3年（二甲双胍500mg bid）；"
            "【近期问题】血糖偏高（上次7.8）、夜尿增多、膝关节疼痛；"
            "【已解决】感冒已愈"
        ),
        "next_steps": (
            "1. 复查空腹血糖+HbA1c；"
            "2. 血糖结果出来后评估是否调整二甲双胍；"
            "3. 膝关节如持续疼痛建议骨科就诊；"
            "4. 继续监测血压"
        ),
        "context_to_preserve": (
            "患者：张大爷，72岁男性；"
            "过敏史：青霉素（严重）；"
            "诊断：高血压、2型糖尿病；"
            "用药：氨氯地平5mg qd、二甲双胍500mg bid；"
            "禁忌：所有青霉素类药物"
        ),
    })

    # 4. 创建Agent并预填充多轮就诊记录
    medical_system_prompt = (
        "你是GerClaw老年医疗AI助手，服务于老年患者。"
        "请用温和、耐心、简洁的语气交流。"
        "始终注意患者过敏史和用药安全。"
    )
    # system_prompt需要占用一些token来触发压缩
    long_system_prompt = medical_system_prompt + "注意事项：" * 20  # 增加system prompt长度

    visit_messages = generate_medical_visit_records()
    print(f"\n[预填充对话] 共{len(visit_messages)}条消息（{len(visit_messages)//2}轮对话）")

    agent = Agent(
        name="gerclaw_medical_assistant",
        system_prompt=long_system_prompt,
        model=model,
        context_config=context_config,
        state=AgentState(
            session_id="demo_session_001",
            context=visit_messages,
        ),
        toolkit=Toolkit(),
    )

    # 5. 计算当前token数
    current_tokens = await model.count_tokens(
        [SystemMsg_dummy(medical_system_prompt)] + visit_messages, tools=[],
    )
    print(f"[压缩前] context中约{current_tokens} tokens")
    print(f"[压缩前] context消息数: {len(agent.state.context)}")
    print(f"[压缩前] summary: {'(空)' if not agent.state.summary else '已有内容'}")

    # 6. 手动触发压缩
    print("\n--- 触发上下文压缩 ---")
    await agent.compress_context()

    # 7. 查看压缩结果
    print(f"\n[压缩后] summary内容:")
    print("-" * 50)
    print(agent.state.summary)
    print("-" * 50)
    print(f"[压缩后] context消息数: {len(agent.state.context)}")
    print(f"[压缩调用次数] {model.compression_call_count}次")

    # 验证过敏信息保留
    summary_text = agent.state.summary if isinstance(agent.state.summary, str) else str(agent.state.summary)
    if "青霉素" in summary_text:
        print("\n[验证通过] 过敏史（青霉素）已保留在压缩摘要中")
    if "氨氯地平" in summary_text:
        print("[验证通过] 用药信息（氨氯地平）已保留在压缩摘要中")
    if "二甲双胍" in summary_text:
        print("[验证通过] 用药信息（二甲双胍）已保留在压缩摘要中")

    # 8. 展示最近保留的消息
    print(f"\n[保留的最近消息]")
    for msg in agent.state.context:
        text = msg.get_text_content() or ""
        print(f"  [{msg.name}] {text[:80]}{'...' if len(text) > 80 else ''}")


def SystemMsg_dummy(text: str):
    """创建一个简单的类Msg对象用于token计数。"""
    class _Dummy:
        def get_text_content(self):
            return text
    return _Dummy()


async def demo_simplified() -> None:
    """简化模式：不依赖AgentScope，直接演示ContextConfig参数含义和压缩流程概念。"""
    print("=" * 60)
    print("GerClaw ContextConfig上下文压缩示例 - 简化模式")
    print("=" * 60)
    print("说明：本模式演示ContextConfig参数配置和压缩原理，不依赖AgentScope安装。\n")

    # ---- ContextConfig参数演示 ----
    print("【ContextConfig医疗配置参数】")
    print("-" * 50)
    config = {
        "trigger_ratio": 0.7,
        "reserve_ratio": 0.15,
        "tool_result_limit": 3000,
        "compression_prompt": "请将以下医疗对话压缩为结构化摘要...",
        "summary_template": (
            "<system-info>以下是之前就诊对话的医疗摘要：\n"
            "# 就诊概述\n{task_overview}\n"
            "# 当前健康状态\n{current_state}\n"
            "# 重要医疗发现\n{important_discoveries}\n"
            "# 后续诊疗计划\n{next_steps}\n"
            "# 需要保留的患者信息\n{context_to_preserve}</system-info>"
        ),
    }
    for k, v in config.items():
        if k == "summary_template":
            print(f"  {k}: (医疗定制模板，包含5个医疗摘要字段)")
        elif k == "compression_prompt":
            print(f"  {k}: {v[:40]}...")
        else:
            print(f"  {k}: {v}")

    # ---- 压缩流程演示 ----
    context_size = 1000  # 假设模型context window为1000 tokens
    trigger = int(context_size * config["trigger_ratio"])  # 700
    reserve = int(context_size * config["reserve_ratio"])  # 150

    print(f"\n【压缩触发机制】")
    print(f"  模型上下文窗口: {context_size} tokens")
    print(f"  触发阈值(trigger_ratio={config['trigger_ratio']}): {trigger} tokens")
    print(f"  保留空间(reserve_ratio={config['reserve_ratio']}): {reserve} tokens")
    print(f"  压缩安全余量: {context_size - trigger} tokens (给压缩模型留空间)")

    # ---- 模拟就诊记录 ----
    print(f"\n【模拟多轮就诊对话】")
    visits = generate_medical_visit_records()
    total_chars = sum(len((m.get_text_content() or "").encode("utf-8")) for m in visits)
    est_tokens = total_chars // 4
    print(f"  对话轮数: {len(visits)//2}轮")
    print(f"  消息数: {len(visits)}条")
    print(f"  估算token数: ~{est_tokens} tokens")
    print(f"  是否触发压缩: {'是' if est_tokens > trigger else '否（需更多对话）'}")

    # ---- 模拟压缩结果 ----
    print(f"\n【模拟压缩后摘要（医疗结构化）】")
    print("-" * 50)
    summary = (
        "<system-info>以下是之前就诊对话的医疗摘要：\n"
        "# 就诊概述\n"
        "张大爷多轮就诊：高血压随访、糖尿病复查、感冒、膝关节疼痛咨询\n\n"
        "# 当前健康状态\n"
        "血压135/85mmHg（较前改善），空腹血糖待复查，感冒已愈，膝关节疼痛待查\n\n"
        "# 重要医疗发现（过敏/用药/异常指标）\n"
        "【过敏红线】青霉素过敏，禁用青霉素类药物\n"
        "【慢病】高血压5年（氨氯地平5mg qd）、2型糖尿病3年（二甲双胍500mg bid）\n"
        "【近期问题】血糖偏高（上次7.8mmol/L）、夜尿增多、膝关节疼痛\n"
        "【已解决】感冒已愈\n\n"
        "# 后续诊疗计划\n"
        "1. 复查空腹血糖+HbA1c\n"
        "2. 根据血糖结果评估是否调整二甲双胍剂量\n"
        "3. 膝关节持续疼痛建议骨科就诊\n"
        "4. 继续家庭血压监测\n\n"
        "# 需要保留的患者信息\n"
        "患者：张大爷，72岁男性；过敏史：青霉素（严重）；"
        "诊断：高血压、2型糖尿病；"
        "用药：氨氯地平5mg qd、二甲双胍500mg bid；"
        "禁忌：所有青霉素类药物</system-info>"
    )
    print(summary)
    print("-" * 50)
    summary_tokens = len(summary.encode("utf-8")) // 4
    print(f"  摘要token数: ~{summary_tokens} tokens (原始对话~{est_tokens} tokens, 压缩比~{est_tokens/max(summary_tokens,1):.1f}x)")

    # ---- 保留的最近消息 ----
    print(f"\n【压缩后保留的最近消息】（reserve_ratio={config['reserve_ratio']}范围内）")
    for msg in visits[-4:]:
        text = msg.get_text_content() or ""
        role = "张大爷" if msg.name == "张大爷" else "助手"
        print(f"  [{role}] {text[:70]}{'...' if len(text) > 70 else ''}")

    print(f"\n{'='*60}")
    print("示例运行完成！")
    print("核心要点：")
    print("1. trigger_ratio控制何时压缩（0.7=使用70%窗口时触发）")
    print("2. reserve_ratio控制保留多少最近消息（0.15=保留15%窗口）")
    print("3. 自定义summary_template确保医疗关键字段不丢失")
    print("4. 过敏史等安全红线信息必须在摘要中保留")
    print(f"{'='*60}")


# ===========================================================================
# 入口
# ===========================================================================
async def main() -> None:
    """主函数：根据AgentScope是否安装选择模式。"""
    # 优先尝试简化模式（不依赖完整AgentScope安装也能展示概念）
    if HAS_AGENTSCOPE:
        try:
            await demo_with_agentscope()
            return
        except Exception as e:
            print(f"[AgentScope模式失败] {e}")
            print("切换到简化模式...\n")
    await demo_simplified()


if __name__ == "__main__":
    asyncio.run(main())
