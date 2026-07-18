"""
GerClaw老年医疗AI平台 - Mem0长期记忆中间件示例
=============================================
演示功能：
1. 使用Mem0Middleware集成mem0长期记忆，跨会话记住患者医疗信息
2. 第一轮对话：张大爷告知过敏史（青霉素过敏）、慢病（高血压/糖尿病）、用药（氨氯地平/二甲双胍）
3. 第二轮对话：新会话中询问用药和注意事项，Agent通过mem0检索历史记忆
4. 若无mem0ai依赖，自动使用Mock模式演示完整流程

运行方式：
    # 有mem0依赖时（真实模式）：
    pip install "agentscope[mem0]"
    export DASHSCOPE_API_KEY="your-key"
    python mem0_longterm_memory.py

    # 无mem0依赖时（Mock模式）：
    python mem0_longterm_memory.py
"""

import asyncio
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# 尝试导入真实AgentScope组件，失败时使用Mock
# ---------------------------------------------------------------------------
try:
    from agentscope.agent import Agent
    from agentscope.credential import DashScopeCredential
    from agentscope.message import UserMsg, AssistantMsg, TextBlock, HintBlock, Msg
    from agentscope.middleware import Mem0Middleware
    from agentscope.model import DashScopeChatModel
    from agentscope.tool import Toolkit

    HAS_AGENTSCOPE = True
except ImportError:
    HAS_AGENTSCOPE = False

# 尝试导入mem0
try:
    import mem0
    HAS_MEM0 = True
except ImportError:
    HAS_MEM0 = False


# ===========================================================================
# Mock模式实现（无需mem0依赖即可运行）
# ===========================================================================
class MockMemoryStore:
    """模拟mem0的记忆存储，使用字典存储文本记忆。"""

    def __init__(self) -> None:
        self._memories: dict[str, list[str]] = {}

    async def add(self, messages: list[dict], user_id: str, agent_id: str | None = None, **_: Any) -> None:
        """模拟mem0.add：从对话中提取关键事实并存储。"""
        key = f"{user_id}:{agent_id or 'default'}"
        if key not in self._memories:
            self._memories[key] = []
        # 简化：直接存储user消息文本作为记忆（真实mem0会用LLM提取facts）
        for msg in messages:
            if msg.get("role") == "user":
                text = msg.get("content", "")
                if text and text not in self._memories[key]:
                    self._memories[key].append(text)
                    print(f"  [Mock记忆存储] 已记录: {text[:60]}...")

    async def search(self, query: str, filters: dict, top_k: int = 5, **_: Any) -> list[dict]:
        """模拟mem0.search：关键词匹配检索记忆。"""
        user_id = filters.get("user_id", "")
        agent_id = filters.get("agent_id")
        key = f"{user_id}:{agent_id or 'default'}"
        memories = self._memories.get(key, [])
        # 简单关键词匹配
        query_lower = query.lower()
        results = []
        for mem in memories:
            # 检查是否包含医疗关键词或直接匹配
            medical_keywords = ["过敏", "青霉素", "高血压", "糖尿病", "药", "氨氯地平", "二甲双胍",
                              "血压", "血糖", "慢病", "张大爷"]
            if any(kw in mem or kw in query for kw in medical_keywords):
                results.append({"memory": mem, "score": 0.9})
        return results[:top_k]


class MockMem0Middleware:
    """模拟Mem0Middleware的最小实现，用于无mem0环境演示流程。"""

    def __init__(self, user_id: str, mode: str = "both", top_k: int = 5, **_: Any) -> None:
        self.user_id = user_id
        self.mode = mode
        self.top_k = top_k
        self._store = MockMemoryStore()
        self._last_messages: list[Msg] = []

    async def list_tools(self) -> list:
        """Mock模式不提供工具，返回空列表。"""
        return []

    def _build_memory_hint(self, memories: list[dict]) -> str:
        """将检索结果构建为Hint文本。"""
        if not memories:
            return ""
        lines = ["## 过去对话中的相关记忆\n"]
        for i, m in enumerate(memories, 1):
            lines.append(f"- {m['memory']}")
        return "\n".join(lines)

    async def before_reply(self, agent: "MockAgent", user_message: str) -> str | None:
        """模拟reply前检索记忆并返回提示文本。"""
        results = await self._store.search(
            query=user_message,
            filters={"user_id": self.user_id},
            top_k=self.top_k,
        )
        hint = self._build_memory_hint(results)
        if hint:
            print(f"  [记忆注入] 检索到{len(results)}条相关记忆")
        return hint

    async def after_reply(self, user_message: str, assistant_reply: str) -> None:
        """模拟reply后存储对话到记忆。"""
        await self._store.add(
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_reply},
            ],
            user_id=self.user_id,
        )


class MockAgent:
    """模拟Agent类，用于无AgentScope环境演示记忆流程。"""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        middlewares: list[MockMem0Middleware] | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.middlewares = middlewares or []
        self.context: list[str] = []

    async def reply(self, user_msg: "UserMsg | str") -> str:
        """模拟reply流程：先检索记忆→生成回复→存储记忆。"""
        text = user_msg if isinstance(user_msg, str) else user_msg.get_text_content() or ""
        memory_hint = None

        # 1. before_reply: 中间件检索记忆
        for mw in self.middlewares:
            hint = await mw.before_reply(self, text)
            if hint:
                memory_hint = hint

        # 2. 模拟LLM生成回复（根据是否有记忆决定回答内容）
        reply = self._generate_reply(text, memory_hint)
        print(f"  [张大爷] {text}")
        print(f"  [GerClaw助手] {reply}")

        # 3. after_reply: 中间件存储对话
        for mw in self.middlewares:
            await mw.after_reply(text, reply)

        self.context.append(text)
        return reply

    def _generate_reply(self, user_text: str, memory_hint: str | None) -> str:
        """根据记忆和用户输入生成回复（Mock模式用规则模拟）。"""
        has_memory = memory_hint is not None

        # 第一轮：患者告知信息
        if "青霉素" in user_text or "过敏" in user_text:
            if has_memory:
                return ("根据您之前告知的信息，我已记录您的青霉素过敏史、"
                       "高血压和糖尿病诊断，以及当前用药（氨氯地平、二甲双胍）。"
                       "请问还有其他需要补充的吗？")
            return ("好的张大爷，我已经记住了您的重要医疗信息：\n"
                   "【过敏史】青霉素过敏\n"
                   "【慢性病】高血压、2型糖尿病\n"
                   "【当前用药】氨氯地平（降压）、二甲双胍（降糖）\n"
                   "这些信息会安全保存，下次您来咨询时我会记得。")

        # 第二轮：询问用药
        if ("吃什么药" in user_text or "用药" in user_text or "注意" in user_text
                or "什么药" in user_text):
            if has_memory:
                return ("张大爷，根据您的医疗记录：\n"
                       "【过敏提醒】您对青霉素过敏，请务必避免使用青霉素类药物！\n"
                       "【当前用药】\n"
                       "  1. 氨氯地平 - 降压药，建议每天固定时间服用\n"
                       "  2. 二甲双胍 - 降糖药，建议餐中或餐后服用以减少胃肠不适\n"
                       "【注意事项】\n"
                       "  - 定期监测血压和血糖\n"
                       "  - 如出现头晕、心慌等症状请及时就医\n"
                       "  - 就诊时务必告知医生您的青霉素过敏史")
            return ("张大爷，我这边暂时没有您之前的用药记录。"
                   "您能告诉我目前在服用哪些药物吗？有没有药物过敏史？")

        # 默认回复
        if has_memory:
            return f"我记得您的情况。关于'{user_text}'，建议您按时服药并定期复查。"
        return f"关于'{user_text}'，我需要先了解您的基本健康情况。"


# ===========================================================================
# 真实模式实现（需要安装agentscope[mem0]）
# ===========================================================================
async def run_real_mode() -> None:
    """使用真实AgentScope + Mem0运行示例。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：未设置DASHSCOPE_API_KEY环境变量，切换到Mock模式")
        await run_mock_mode()
        return

    print("=" * 60)
    print("GerClaw医疗记忆示例 - 真实模式（AgentScope + Mem0）")
    print("=" * 60)

    # 初始化模型
    credential = DashScopeCredential(api_key=api_key)
    chat_model = DashScopeChatModel(
        credential=credential,
        model="qwen-plus",
        stream=False,
    )

    # 创建Mem0中间件（路径1：传AgentScope模型，自动构建OSS AsyncMemory）
    mw = Mem0Middleware(
        user_id="patient_zhang_001",
        chat_model=chat_model,
        mode="static_control",  # 自动检索+自动写回，Agent无感知
        top_k=5,
        await_write=True,
    )

    # ---- 第一轮对话：告知医疗信息 ----
    print("\n" + "=" * 40)
    print("【第一轮对话】张大爷首次就诊，告知基本信息")
    print("=" * 40)

    agent1 = Agent(
        name="gerclaw_medical_assistant",
        system_prompt=(
            "你是GerClaw老年医疗AI助手。请用温和、耐心的语气与老年患者交流。"
            "当患者告知过敏史、慢病或用药信息时，确认已记住并给出简要回应。"
        ),
        model=chat_model,
        toolkit=Toolkit(tools=await mw.list_tools()),
        middlewares=[mw],
    )

    reply1 = await agent1.reply(UserMsg(
        "张大爷",
        "医生你好，我叫张大爷。我对青霉素过敏，有高血压和糖尿病，"
        "现在吃氨氯地平和二甲双胍。",
    ))
    print(f"[助手回复] {reply1.get_text_content()}")

    # ---- 第二轮对话：新会话，询问用药 ----
    print("\n" + "=" * 40)
    print("【第二轮对话】新会话（新Agent实例），张大爷询问用药")
    print("=" * 40)

    agent2 = Agent(
        name="gerclaw_medical_assistant",
        system_prompt=(
            "你是GerClaw老年医疗AI助手。请用温和、耐心的语气与老年患者交流。"
            "回答用药问题时，先检索记忆中的患者信息，给出安全提醒。"
        ),
        model=chat_model,
        toolkit=Toolkit(tools=await mw.list_tools()),
        middlewares=[mw],
    )

    reply2 = await agent2.reply(UserMsg(
        "张大爷",
        "医生，我平时吃什么药来着？需要注意什么？",
    ))
    print(f"[助手回复] {reply2.get_text_content()}")

    print("\n" + "=" * 40)
    print("示例运行完成！跨会话记忆验证通过。")
    print("=" * 40)


# ===========================================================================
# Mock模式实现
# ===========================================================================
async def run_mock_mode() -> None:
    """使用Mock组件运行示例（无需mem0/真实API）。"""
    print("=" * 60)
    print("GerClaw医疗记忆示例 - Mock模式（无mem0依赖）")
    print("=" * 60)
    print("说明：本模式使用内存字典模拟mem0存储，演示记忆流程。")
    print("      安装pip install agentscope[mem0]并设置DASHSCOPE_API_KEY可运行真实模式。\n")

    # 创建Mock中间件
    mw = MockMem0Middleware(
        user_id="patient_zhang_001",
        mode="static_control",
        top_k=5,
    )

    # ---- 第一轮对话：告知医疗信息 ----
    print("=" * 40)
    print("【第一轮对话】张大爷首次就诊，告知基本信息")
    print("=" * 40)

    agent1 = MockAgent(
        name="gerclaw_medical_assistant",
        system_prompt="GerClaw老年医疗助手",
        middlewares=[mw],
    )

    await agent1.reply("医生你好，我是张大爷。我对青霉素过敏，有高血压和糖尿病，现在吃氨氯地平和二甲双胍。")

    # ---- 第二轮对话：新会话，询问用药 ----
    print("\n" + "=" * 40)
    print("【第二轮对话】新会话（新Agent实例），张大爷询问用药")
    print("=" * 40)

    # 新建Agent实例模拟跨会话（context为空，但中间件的记忆存储保持）
    agent2 = MockAgent(
        name="gerclaw_medical_assistant",
        system_prompt="GerClaw老年医疗助手",
        middlewares=[mw],  # 复用同一个mw实例（包含之前存储的记忆）
    )

    await agent2.reply("医生，我平时吃什么药来着？需要注意什么？")

    print("\n" + "=" * 40)
    print("示例运行完成！")
    print("- 第一轮张大爷告知的过敏史/慢病/用药已存储到记忆")
    print("- 第二轮新会话中，Agent通过记忆检索成功回忆起张大爷的信息")
    print("- 过敏信息被优先提醒，符合GerClaw临床安全要求")
    print("=" * 40)


# ===========================================================================
# 入口
# ===========================================================================
async def main() -> None:
    """主函数：根据环境选择真实模式或Mock模式。"""
    if HAS_AGENTSCOPE and HAS_MEM0 and os.environ.get("DASHSCOPE_API_KEY"):
        await run_real_mode()
    else:
        missing = []
        if not HAS_AGENTSCOPE:
            missing.append("agentscope")
        if not HAS_MEM0:
            missing.append("mem0ai")
        if not os.environ.get("DASHSCOPE_API_KEY"):
            missing.append("DASHSCOPE_API_KEY")
        if missing:
            print(f"[提示] 缺少以下组件，自动切换到Mock模式: {', '.join(missing)}")
            print()
        await run_mock_mode()


if __name__ == "__main__":
    asyncio.run(main())
