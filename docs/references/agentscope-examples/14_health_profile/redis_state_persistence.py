"""
GerClaw老年医疗AI平台 - 基于Redis的Agent会话持久化示例
====================================================
演示功能：
1. 使用Python dict模拟Redis接口（无redis-py/fakeredis依赖也可运行）
2. 第一轮对话：张大爷告知高血压病史和氨氯地平用药，AgentState序列化保存到"Redis"
3. 模拟进程重启/新实例：创建全新Agent实例，从"Redis"反序列化恢复AgentState
4. 第二轮对话：张大爷反馈脚踝水肿（氨氯地平常见副作用），新Agent能引用历史对话
5. 验证对话历史跨实例恢复，健康信息不丢失

运行方式：
    export DASHSCOPE_API_KEY="your-key"
    python redis_state_persistence.py

依赖：
    pip install agentscope
    （无需redis服务，内部使用dict模拟Redis set/get接口）
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# 尝试导入AgentScope，失败时降级到Mock模式
# ---------------------------------------------------------------------------
try:
    from agentscope.agent import Agent
    from agentscope.credential import DashScopeCredential
    from agentscope.message import UserMsg, AssistantMsg, TextBlock, Msg
    from agentscope.model import DashScopeChatModel
    from agentscope.state import AgentState
    from agentscope.tool import Toolkit

    HAS_AGENTSCOPE = True
except ImportError:
    HAS_AGENTSCOPE = False


# ===========================================================================
# Dict模拟Redis（实现set/get/delete基本KV接口，模拟RedisStorage行为）
# ===========================================================================
class DictRedis:
    """使用Python dict模拟Redis异步KV接口。

    生产环境应使用 agentscope.app.storage.RedisStorage 或 fakeredis，
    本类仅用于演示AgentState序列化/反序列化流程。
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str) -> None:
        """模拟Redis SET命令，存储JSON字符串。"""
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        """模拟Redis GET命令，返回JSON字符串或None。"""
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        """模拟Redis DELETE命令，返回删除数量。"""
        if key in self._store:
            del self._store[key]
            return 1
        return 0

    def key_count(self) -> int:
        """返回当前key数量（调试用）。"""
        return len(self._store)


def make_redis_key(user_id: str, session_id: str) -> str:
    """生成AgentState在Redis中的key（参考RedisStorage.KeyConfig命名）。"""
    return f"gerclaw:user:{user_id}:session:{session_id}:state"


# ===========================================================================
# 健康画像数据结构（存放在middle_context中，随AgentState一起序列化）
# ===========================================================================
def empty_health_profile(name: str = "") -> dict[str, Any]:
    """创建空的健康画像结构（对应调研文档§1.2.2的JSONB字段精简版）。"""
    return {
        "basic_info": {"name": name, "age": None, "gender": None},
        "conditions": [],      # 慢病列表 [{code, display, onset_date, severity, status}]
        "allergies": [],       # 过敏列表 [{substance, type, severity, reaction}]
        "medications": [],     # 用药列表 [{name, dose, frequency, start_date, route}]
        "assessments": {},     # CGA评估
        "conversation_summary": {"key_facts": [], "active_priorities": []},
        "profile_version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# Mock模式实现（无AgentScope时演示持久化流程）
# ===========================================================================
class MockAgentState:
    """模拟AgentState：简化版状态容器，支持JSON序列化。"""

    def __init__(self) -> None:
        self.context: list[dict[str, str]] = []
        self.middle_context: dict[str, Any] = {}
        self.session_id: str = f"session-{datetime.now().strftime('%H%M%S')}"

    def model_dump_json(self) -> str:
        """序列化到JSON字符串。"""
        return json.dumps(
            {
                "context": self.context,
                "middle_context": self.middle_context,
                "session_id": self.session_id,
            },
            ensure_ascii=False,
        )

    @classmethod
    def model_validate_json(cls, raw: str) -> "MockAgentState":
        """从JSON字符串反序列化。"""
        data = json.loads(raw)
        state = cls()
        state.context = data.get("context", [])
        state.middle_context = data.get("middle_context", {})
        state.session_id = data.get("session_id", state.session_id)
        return state


class MockAgent:
    """模拟Agent类，演示state持久化/恢复流程。"""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        state: MockAgentState | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.state = state or MockAgentState()
        # 初始化健康画像（如果恢复的state中没有）
        if "health_profile" not in self.state.middle_context:
            self.state.middle_context["health_profile"] = empty_health_profile()

    async def reply(self, user_name: str, user_text: str) -> str:
        """模拟一轮对话回复。"""
        profile = self.state.middle_context["health_profile"]
        # 记录对话到context
        self.state.context.append({"role": "user", "name": user_name, "content": user_text})

        # 简单规则提取健康信息（演示用，真实场景用LLM或自定义Middleware）
        self._extract_health_info(user_text, profile)

        # 根据历史信息生成回复
        reply = self._generate_reply(user_text, profile)

        self.state.context.append({"role": "assistant", "name": self.name, "content": reply})
        profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
        profile["profile_version"] += 1

        print(f"  [{user_name}] {user_text}")
        print(f"  [GerClaw助手] {reply}")
        return reply

    def _extract_health_info(self, text: str, profile: dict) -> None:
        """从用户消息中提取健康信息（简化规则匹配）。"""
        # 基础信息
        if "我叫" in text or "我是" in text:
            for nm in ["张大爷", "李奶奶", "王大爷"]:
                if nm in text:
                    profile["basic_info"]["name"] = nm
                    break

        # 慢病
        if "高血压" in text and not any(c["display"] == "原发性高血压" for c in profile["conditions"]):
            profile["conditions"].append({
                "code": "I10", "display": "原发性高血压",
                "onset_date": "未知", "severity": "moderate", "status": "active",
            })
            profile["conversation_summary"]["key_facts"].append("有高血压病史")
        if "糖尿病" in text and not any(c["display"] == "2型糖尿病" for c in profile["conditions"]):
            profile["conditions"].append({
                "code": "E11", "display": "2型糖尿病",
                "onset_date": "未知", "severity": "moderate", "status": "active",
            })

        # 用药
        if "氨氯地平" in text and not any(m["name"].startswith("氨氯地平") for m in profile["medications"]):
            profile["medications"].append({
                "name": "苯磺酸氨氯地平片", "dose": "5mg",
                "frequency": "每日1次", "start_date": "未知", "route": "oral",
            })
            profile["conversation_summary"]["active_priorities"].append("血压控制")
        if "二甲双胍" in text and not any(m["name"].startswith("二甲双胍") for m in profile["medications"]):
            profile["medications"].append({
                "name": "盐酸二甲双胍片", "dose": "0.5g",
                "frequency": "每日2次", "start_date": "未知", "route": "oral",
            })

        # 过敏
        if "青霉素" in text and "过敏" in text:
            if not any(a["substance"] == "青霉素" for a in profile["allergies"]):
                profile["allergies"].append({
                    "substance": "青霉素", "type": "drug",
                    "severity": "severe", "reaction": "皮疹/呼吸困难",
                })

    def _generate_reply(self, user_text: str, profile: dict) -> str:
        """根据当前健康画像生成回复（规则模拟）。"""
        meds = [m["name"] for m in profile["medications"]]
        conds = [c["display"] for c in profile["conditions"]]
        allergs = [a["substance"] for a in profile["allergies"]]

        # 第一轮：初次就诊
        if "高血压" in user_text and "氨氯地平" in user_text:
            return (
                f"好的，我已记录您的信息：\n"
                f"  【慢病】{', '.join(conds) if conds else '无'}\n"
                f"  【用药】{', '.join(meds) if meds else '无'}\n"
                f"  【过敏】{', '.join(allergs) if allergs else '未记录'}\n"
                f"建议您每天固定时间服药，定期监测血压。"
            )

        # 第二轮：提及副作用（脚踝水肿是氨氯地平常见副作用）
        if "脚踝" in user_text or "水肿" in user_text or "肿" in user_text:
            amlo = any("氨氯地平" in m for m in meds)
            if amlo:
                return (
                    f"张大爷，脚踝水肿是氨氯地平（您正在服用的降压药）的常见不良反应之一。\n"
                    f"根据您的健康档案：\n"
                    f"  - 诊断：{', '.join(conds)}\n"
                    f"  - 用药：{', '.join(meds)}\n"
                    f"  - 过敏：{', '.join(allergs) if allergs else '无'}\n"
                    f"建议：1) 不要自行停药；2) 就诊时告知医生此症状，考虑调整剂量或更换药物；"
                    f"3) 避免长时间站立，适当抬高下肢。"
                )
            return "脚踝水肿可能与多种因素有关，建议您到医院做进一步检查。"

        # 默认
        if conds or meds:
            return f"张大爷，我已了解您的健康情况。{'、'.join(conds) if conds else ''}需要定期监测，请按时服药。"
        return "张大爷您好，我是GerClaw健康助手，请告诉我您的健康情况。"


async def save_state_to_redis(
    redis: DictRedis, user_id: str, session_id: str, state: Any,
) -> None:
    """将AgentState序列化并保存到Redis（模拟RedisStorage.update_session_state）。"""
    key = make_redis_key(user_id, session_id)
    # 真实AgentScope中state已经是AgentState(BaseModel)，调用model_dump_json()
    if hasattr(state, "model_dump_json"):
        raw = state.model_dump_json()
    else:
        raw = state.model_dump_json()  # MockAgentState
    await redis.set(key, raw)
    print(f"  [Redis] 已保存state到 {key}  ({len(raw)} bytes)")


async def load_state_from_redis(
    redis: DictRedis, user_id: str, session_id: str,
) -> Any:
    """从Redis读取并反序列化AgentState。"""
    key = make_redis_key(user_id, session_id)
    raw = await redis.get(key)
    if raw is None:
        return None
    print(f"  [Redis] 从 {key} 恢复state  ({len(raw)} bytes)")
    if HAS_AGENTSCOPE:
        return AgentState.model_validate_json(raw)
    return MockAgentState.model_validate_json(raw)


# ===========================================================================
# 真实AgentScope模式
# ===========================================================================
async def run_real_mode() -> None:
    """使用真实AgentScope运行持久化示例。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("未设置DASHSCOPE_API_KEY，切换到Mock模式")
        await run_mock_mode()
        return

    print("=" * 60)
    print("GerClaw健康画像持久化示例 - 真实模式（AgentScope + dict模拟Redis）")
    print("=" * 60)

    credential = DashScopeCredential(api_key=api_key)
    chat_model = DashScopeChatModel(
        credential=credential, model="qwen-plus", stream=False,
    )
    redis = DictRedis()
    user_id = "elder_zhang_001"
    session_id = "session-demo-001"

    # ---- 第一轮对话：初次就诊 ----
    print("\n" + "=" * 50)
    print("【第一轮对话】张大爷初次就诊（新会话、空state）")
    print("=" * 50)

    system_prompt = (
        "你是GerClaw老年医疗AI助手。请用温和、耐心、通俗易懂的语气和老年患者交流。"
        "每次回复简洁，重点突出安全提醒。"
    )
    agent1 = Agent(
        name="gerclaw_health_assistant",
        system_prompt=system_prompt,
        model=chat_model,
        toolkit=Toolkit(),
        middlewares=[],
    )
    # 手动初始化健康画像到middle_context（演示用；生产中由Middleware自动初始化）
    agent1.state.middle_context["health_profile"] = empty_health_profile("张大爷")

    reply1 = await agent1.reply(UserMsg(
        "张大爷",
        "医生你好，我叫张大爷，今年72岁。我有高血压好几年了，一直在吃氨氯地平。",
    ))
    print(f"[助手] {reply1.get_text_content()}")

    # 简单提取健康信息到profile（演示手动维护，实际由Middleware自动完成）
    profile = agent1.state.middle_context["health_profile"]
    profile["basic_info"]["age"] = 72
    profile["basic_info"]["name"] = "张大爷"
    if not any(c["code"] == "I10" for c in profile["conditions"]):
        profile["conditions"].append({
            "code": "I10", "display": "原发性高血压",
            "onset_date": "约5年前", "severity": "moderate", "status": "active",
        })
    if not any("氨氯地平" in m["name"] for m in profile["medications"]):
        profile["medications"].append({
            "name": "苯磺酸氨氯地平片", "dose": "5mg",
            "frequency": "每日1次", "start_date": "约5年前", "route": "oral",
        })
    profile["profile_version"] += 1
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")

    # 序列化保存到Redis（模拟进程退出前持久化）
    await save_state_to_redis(redis, user_id, session_id, agent1.state)
    print(f"  [进程] Agent实例1即将销毁，对话历史共{len(agent1.state.context)}条消息\n")

    # ---- 模拟进程重启 / 新实例启动 ----
    print("=" * 50)
    print("【模拟进程重启】创建全新Agent实例，从Redis恢复state")
    print("=" * 50)

    recovered_state = await load_state_from_redis(redis, user_id, session_id)
    print(f"  恢复的对话历史条数：{len(recovered_state.context)}")
    print(f"  恢复的健康画像慢病数：{len(recovered_state.middle_context['health_profile']['conditions'])}")
    print(f"  恢复的健康画像用药数：{len(recovered_state.middle_context['health_profile']['medications'])}")

    # 创建新Agent实例，传入恢复的state
    agent2 = Agent(
        name="gerclaw_health_assistant",
        system_prompt=system_prompt + " 回答前请先参考对话历史中患者已告知的信息。",
        model=chat_model,
        toolkit=Toolkit(),
        middlewares=[],
    )
    agent2.load_state(recovered_state)  # 关键：加载恢复的state

    # ---- 第二轮对话：反馈副作用 ----
    print("\n" + "=" * 50)
    print("【第二轮对话】新Agent实例，张大爷反馈脚踝水肿")
    print("=" * 50)

    reply2 = await agent2.reply(UserMsg(
        "张大爷",
        "医生，我最近脚踝有点肿，是怎么回事？跟我吃的降压药有关系吗？",
    ))
    print(f"[助手] {reply2.get_text_content()}")

    # 第二轮结束后再次保存
    await save_state_to_redis(redis, user_id, session_id, agent2.state)

    print("\n" + "=" * 50)
    print("持久化验证完成！")
    print(f"  Redis中存储的key数量：{redis.key_count()}")
    print(f"  最终对话历史条数：{len(agent2.state.context)}")
    print(f"  健康画像版本号：{agent2.state.middle_context['health_profile']['profile_version']}")
    print("=" * 50)


# ===========================================================================
# Mock模式
# ===========================================================================
async def run_mock_mode() -> None:
    """使用Mock组件演示持久化流程（无需AgentScope/API Key）。"""
    print("=" * 60)
    print("GerClaw健康画像持久化示例 - Mock模式（dict模拟Redis）")
    print("=" * 60)
    print("说明：本模式演示AgentState序列化→Redis→反序列化恢复的完整流程。")
    print("      安装agentscope并设置DASHSCOPE_API_KEY可运行真实LLM模式。\n")

    redis = DictRedis()
    user_id = "elder_zhang_001"
    session_id = "session-demo-001"
    system_prompt = "GerClaw老年医疗AI助手"

    # ---- 第一轮对话 ----
    print("=" * 50)
    print("【第一轮对话】张大爷初次就诊（Agent实例1）")
    print("=" * 50)

    agent1 = MockAgent(name="gerclaw_assistant", system_prompt=system_prompt)
    await agent1.reply(
        "张大爷",
        "医生你好，我叫张大爷，今年72岁。我有高血压好几年了，一直在吃氨氯地平。",
    )

    # 保存state到Redis（模拟进程结束前持久化）
    await save_state_to_redis(redis, user_id, session_id, agent1.state)
    print(f"  [进程] Agent实例1销毁，释放内存。对话历史{len(agent1.state.context)}条已持久化。\n")

    # ---- 模拟进程重启 ----
    print("=" * 50)
    print("【模拟进程重启】新进程启动，从Redis恢复会话")
    print("=" * 50)

    recovered = await load_state_from_redis(redis, user_id, session_id)
    print(f"  恢复检查：")
    print(f"    - session_id: {recovered.session_id}")
    print(f"    - 对话历史条数: {len(recovered.context)}")
    hp = recovered.middle_context.get("health_profile", {})
    print(f"    - 慢病记录: {[c['display'] for c in hp.get('conditions', [])]}")
    print(f"    - 用药记录: {[m['name'] for m in hp.get('medications', [])]}")
    print(f"    - 画像版本: {hp.get('profile_version')}")

    # 创建新Agent实例，传入恢复的state
    agent2 = MockAgent(
        name="gerclaw_assistant",
        system_prompt=system_prompt,
        state=recovered,
    )
    print(f"  [进程] 新Agent实例创建完成，state已加载。\n")

    # ---- 第二轮对话 ----
    print("=" * 50)
    print("【第二轮对话】新Agent实例，张大爷反馈脚踝水肿")
    print("=" * 50)

    await agent2.reply(
        "张大爷",
        "医生，我最近脚踝有点肿，是怎么回事？跟我吃的降压药有关系吗？",
    )

    # 第二轮后再次保存（state已更新）
    await save_state_to_redis(redis, user_id, session_id, agent2.state)

    # ---- 验证持久化结果 ----
    print("\n" + "=" * 50)
    print("【持久化结果验证】")
    print("=" * 50)
    final_raw = await redis.get(make_redis_key(user_id, session_id))
    final_state = MockAgentState.model_validate_json(final_raw)
    final_hp = final_state.middle_context["health_profile"]

    print(f"  Redis key总数：{redis.key_count()}")
    print(f"  最终对话历史：{len(final_state.context)}条消息")
    print(f"  最终健康画像：")
    print(f"    - 姓名：{final_hp['basic_info'].get('name')}")
    print(f"    - 慢病：{[c['display'] for c in final_hp['conditions']]}")
    print(f"    - 用药：{[m['name'] for m in final_hp['medications']]}")
    print(f"    - 画像版本：v{final_hp['profile_version']}")
    print(f"    - 最后更新：{final_hp['updated_at']}")

    # 跨实例验证关键断言
    assert len(final_state.context) == 4, "对话历史应该包含2轮共4条消息"
    assert any("氨氯地平" in m["name"] for m in final_hp["medications"]), "氨氯地平应在用药列表中"
    assert any(c["code"] == "I10" for c in final_hp["conditions"]), "高血压应在慢病列表中"
    print("\n  [验证通过] 对话历史和健康画像成功跨实例恢复！")
    print("=" * 50)


# ===========================================================================
# 入口
# ===========================================================================
async def main() -> None:
    """主函数：根据环境选择真实模式或Mock模式。"""
    if HAS_AGENTSCOPE and os.environ.get("DASHSCOPE_API_KEY"):
        await run_real_mode()
    else:
        missing = []
        if not HAS_AGENTSCOPE:
            missing.append("agentscope")
        if not os.environ.get("DASHSCOPE_API_KEY"):
            missing.append("DASHSCOPE_API_KEY")
        if missing:
            print(f"[提示] 缺少 {', '.join(missing)}，自动切换到Mock模式\n")
        await run_mock_mode()


if __name__ == "__main__":
    asyncio.run(main())
