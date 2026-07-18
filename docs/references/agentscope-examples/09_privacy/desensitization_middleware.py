# -*- coding: utf-8 -*-
"""GerClaw PHI 数据脱敏中间件示例。

演示自定义 AgentScope Middleware（继承 MiddlewareBase），实现 on_reply hook
对 Agent 输出中的医疗 PHI（个人健康信息）进行实时脱敏：
- 身份证号（18位）→ *****************
- 手机号（11位）→ 1**********
- 患者姓名（上下文模式识别）→ [患者]
- 邮箱 → ***@***

运行前提：pip install agentscope && export DASHSCOPE_API_KEY=sk-xxx
"""
import asyncio
import os
import re
from typing import Any, AsyncGenerator, Callable

from agentscope.agent import Agent
from agentscope.credential import DashScopeCredential
from agentscope.event import TextBlockDeltaEvent
from agentscope.message import TextBlock, UserMsg
from agentscope.middleware import MiddlewareBase
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit


# ========== PHI 脱敏正则 ==========
ID_CARD_RE = re.compile(
    r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"
)
PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
NAME_RE = re.compile(r"(患者|病人|姓名|名[字为])([：:]\s*)([\u4e00-\u9fa5]{2,4})")
MRN_RE = re.compile(r"((?:住院号|病历号|门诊号|病案号|MRN)([：:]\s*))([A-Za-z0-9\-]{4,20})")


def desensitize_phi(text: str) -> str:
    """对文本中的 PHI 进行正则脱敏替换。"""
    if not text:
        return text
    text = ID_CARD_RE.sub("*****************", text)
    text = PHONE_RE.sub("1**********", text)
    text = EMAIL_RE.sub("***@***", text)
    text = NAME_RE.sub(r"\1\2[患者]", text)
    text = MRN_RE.sub(r"\1[病历号]", text)
    return text


class PHIDesensitizationMiddleware(MiddlewareBase):
    """PHI 脱敏中间件：拦截 on_reply 输出流，对 TextBlockDelta 做实时脱敏。"""

    def __init__(self, desensitize_input: bool = False) -> None:
        self._desensitize_input = desensitize_input
        self._hit_count = 0

    async def on_reply(
        self,
        agent: Agent,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """洋葱模型 Hook：在输出事件流中对增量文本做脱敏。"""
        # 可选：对输入也脱敏（模型看不到原始 PHI）
        if self._desensitize_input:
            inputs = input_kwargs.get("inputs")
            if inputs is not None:
                input_kwargs["inputs"] = self._desensitize_inputs(inputs)

        async for event in next_handler(**input_kwargs):
            # 对流式增量文本做脱敏
            if isinstance(event, TextBlockDeltaEvent):
                original = event.delta
                event.delta = desensitize_phi(event.delta)
                if event.delta != original:
                    self._hit_count += 1
            yield event

    def _desensitize_inputs(self, inputs):
        """对输入 Msg 的 TextBlock 做脱敏。"""
        if hasattr(inputs, "content"):
            return self._desensitize_msg(inputs)
        if isinstance(inputs, list):
            return [self._desensitize_msg(m) for m in inputs]
        return inputs

    def _desensitize_msg(self, msg):
        """对单条 Msg 的文本内容脱敏。"""
        try:
            content = msg.content
            if isinstance(content, str):
                msg.content = desensitize_phi(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, TextBlock) and b.text:
                        b.text = desensitize_phi(b.text)
        except Exception:
            pass
        return msg

    @property
    def hit_count(self) -> int:
        """脱敏命中次数，用于审计。"""
        return self._hit_count


def _check_no_phi(text: str, label: str) -> bool:
    """检查文本中是否有 PHI 残留。"""
    phi_items = [
        ("身份证", "110101199003078888"),
        ("手机号", "13800138888"),
        ("邮箱", "zhangwei@example.com"),
        ("姓名", "张伟"),
    ]
    ok = True
    for name, val in phi_items:
        if val in text:
            print(f"  [FAIL] {label} 中发现未脱敏{name}")
            ok = False
    return ok


async def main() -> None:
    """主入口：验证脱敏中间件效果。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("[错误] 请先设置 DASHSCOPE_API_KEY 环境变量")
        return

    print("=" * 60)
    print("GerClaw PHI 数据脱敏中间件演示")
    print("=" * 60)

    # ---- 1. 脱敏函数单元测试 ----
    print("\n[1] 脱敏函数单元测试")
    raw = (
        "患者张伟，身份证110101199003078888，手机13800138888，"
        "邮箱zhangwei@example.com，病历号MRN-2026-001。"
    )
    masked = desensitize_phi(raw)
    print(f"  原始: {raw}")
    print(f"  脱敏: {masked}")
    _check_no_phi(masked, "脱敏结果")

    # ---- 2. 创建 Agent ----
    print("\n[2] 创建 Agent（注册 PHIDesensitizationMiddleware）")
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-plus",
    )
    phi_mw = PHIDesensitizationMiddleware()
    agent = Agent(
        name="medical_assistant",
        system_prompt=(
            "你是 GerClaw 医疗助手。回复时请原样引用用户提供的"
            "姓名、身份证号、手机号、邮箱等信息以便核对。"
        ),
        model=model,
        toolkit=Toolkit(),
        middlewares=[phi_mw],
    )

    # ---- 3. 发送含 PHI 的咨询 ----
    print("\n[3] 发送含模拟 PHI 的咨询消息...")
    user_msg = UserMsg(
        name="patient_family",
        content=[TextBlock(
            text=(
                "你好，患者张伟，身份证号110101199003078888，"
                "手机号13800138888，邮箱zhangwei@example.com，"
                "72岁，高血压，服药氨氯地平，血压仍高需要调药吗？"
            ),
        )],
    )
    reply = await agent.reply(user_msg)

    # ---- 4. 验证输出脱敏 ----
    print("\n[4] 验证 Agent 输出脱敏效果")
    reply_text = "".join(
        b.text for b in reply.content if hasattr(b, "text") and b.text
    )
    print(f"  Agent 回复:\n  {reply_text[:500]}")
    print()
    safe = _check_no_phi(reply_text, "Agent输出")
    print(f"  脱敏命中次数: {phi_mw.hit_count}")
    print(f"  输出安全: {'是' if safe else '否（存在PHI残留）'}")

    print("\n" + "=" * 60)
    print("提示：生产环境建议集成 Microsoft Presidio + PaddleNLP NER")
    print("      脱敏中间件注册顺序应在 TracingMiddleware 之前")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
