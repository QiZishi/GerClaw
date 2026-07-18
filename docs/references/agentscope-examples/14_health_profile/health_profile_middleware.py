"""
GerClaw老年医疗AI平台 - 健康画像自定义Middleware示例
===============================================
演示功能：
1. 继承MiddlewareBase实现自定义HealthProfileMiddleware（参考StateChangeMiddleware风格）
2. 在on_reply洋葱模型钩子中监听Agent状态变更
3. 自动从对话文本中提取/更新健康画像标签：
   - 慢病诊断（高血压/糖尿病/冠心病等，含ICD-10编码）
   - 药物变更（氨氯地平/二甲双胍/阿司匹林等新药或停药）
   - 过敏发现（青霉素/海鲜/磺胺等药物或食物过敏）
4. 健康画像数据结构存放在agent.state.middle_context["health_profile"]中
5. 维护profile_version乐观锁版本号、updated_at时间戳、去重合并逻辑
6. 多轮对话后自动打印健康画像快照，验证自动提取效果

运行方式：
    export DASHSCOPE_API_KEY="your-key"
    python health_profile_middleware.py

依赖：
    pip install agentscope
    （无额外依赖，Middleware规则提取使用关键词匹配，无需LLM抽取即可运行）
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Any, AsyncGenerator

# ---------------------------------------------------------------------------
# 尝试导入AgentScope，失败时降级到Mock模式
# ---------------------------------------------------------------------------
try:
    from agentscope.agent import Agent
    from agentscope.credential import DashScopeCredential
    from agentscope.message import UserMsg, Msg, TextBlock
    from agentscope.middleware import MiddlewareBase
    from agentscope.model import DashScopeChatModel
    from agentscope.tool import Toolkit

    HAS_AGENTSCOPE = True
except ImportError:
    HAS_AGENTSCOPE = False


# ===========================================================================
# 健康画像数据结构与提取规则
# ===========================================================================

# ICD-10编码映射表（慢病关键词 → ICD-10编码+中文名称）
CONDITION_RULES: dict[str, tuple[str, str]] = {
    "高血压": ("I10", "原发性高血压"),
    "糖尿病": ("E11", "2型糖尿病"),
    "冠心病": ("I25.1", "冠状动脉粥样硬化性心脏病"),
    "高血脂": ("E78.5", "高脂血症"),
    "慢阻肺": ("J44", "慢性阻塞性肺疾病"),
    "骨质疏松": ("M81", "骨质疏松症"),
    "关节炎": ("M13.9", "关节炎"),
    "脑卒中": ("I64", "脑卒中"),
    "房颤": ("I48", "心房颤动"),
}

# 药物关键词映射（通用名/商品名 → 通用名+默认剂量）
MEDICATION_RULES: dict[str, dict[str, str]] = {
    "氨氯地平": {"name": "苯磺酸氨氯地平片", "default_dose": "5mg", "route": "oral",
                 "for_condition": "I10"},
    "络活喜": {"name": "苯磺酸氨氯地平片", "default_dose": "5mg", "route": "oral",
               "for_condition": "I10"},
    "二甲双胍": {"name": "盐酸二甲双胍片", "default_dose": "0.5g", "route": "oral",
                 "for_condition": "E11"},
    "格华止": {"name": "盐酸二甲双胍片", "default_dose": "0.5g", "route": "oral",
               "for_condition": "E11"},
    "阿司匹林": {"name": "阿司匹林肠溶片", "default_dose": "100mg", "route": "oral",
                 "for_condition": "I25.1"},
    "他汀": {"name": "阿托伐他汀钙片", "default_dose": "20mg", "route": "oral",
             "for_condition": "E78.5"},
    "阿托伐他汀": {"name": "阿托伐他汀钙片", "default_dose": "20mg", "route": "oral",
                   "for_condition": "E78.5"},
    "胰岛素": {"name": "胰岛素注射液", "default_dose": "遵医嘱", "route": "subcutaneous",
               "for_condition": "E11"},
    "硝酸甘油": {"name": "硝酸甘油片", "default_dose": "0.5mg", "route": "sublingual",
                 "for_condition": "I25.1"},
}

# 过敏关键词映射
ALLERGY_RULES: dict[str, tuple[str, str, str]] = {
    "青霉素": ("青霉素", "drug", "severe"),
    "头孢": ("头孢类抗生素", "drug", "severe"),
    "磺胺": ("磺胺类药物", "drug", "severe"),
    "阿司匹林过敏": ("阿司匹林", "drug", "moderate"),
    "海鲜": ("海鲜", "food", "moderate"),
    "花生": ("花生", "food", "severe"),
    "牛奶": ("牛奶", "food", "mild"),
    "花粉": ("花粉", "environmental", "mild"),
}


def empty_health_profile() -> dict[str, Any]:
    """创建空的健康画像结构（GerClaw六大数据类精简版）。"""
    return {
        "basic_info": {
            "name": None, "age": None, "gender": None,
        },
        "conditions": [],       # [{code, display, onset_date, severity, status}]
        "allergies": [],        # [{substance, type, severity, reaction, discovered_at}]
        "medications": [],      # [{name, dose, frequency, route, start_date, for_condition}]
        "assessments": {},      # CGA评估 {adl, mmse, fall_risk, ...}
        "conversation_summary": {
            "key_facts": [],
            "active_priorities": [],
            "recent_alerts": [],
        },
        "schema_version": 1,
        "profile_version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# 健康画像Middleware（参考StateChangeMiddleware的on_reply钩子模式）
# ===========================================================================
if HAS_AGENTSCOPE:
    class HealthProfileMiddleware(MiddlewareBase):
        """监听Agent对话、自动提取并维护健康画像的自定义Middleware。

        参考 agentscope.app.middleware.StateChangeMiddleware 的设计思路：
        - 在on_reply开始时初始化middle_context中的健康画像
        - 透传所有事件（不阻塞流式输出）
        - 在on_reply结束后扫描最新对话，提取健康标签
        - 检测到变更时更新profile_version和updated_at
        """

        def __init__(self, user_id: str | None = None) -> None:
            super().__init__()
            self.user_id = user_id or "anonymous"
            self._change_log: list[str] = []  # 本次reply的变更记录

        async def get_middleware_key(self) -> str:
            """Middleware命名空间键，用于在middle_context中隔离状态。"""
            return "health_profile"

        async def on_reply(
            self,
            agent: "Agent",
            input_kwargs: dict,
            next_handler,
        ) -> AsyncGenerator:
            """洋葱模型核心钩子：reply前初始化，reply后提取画像。"""
            # ---- before ----
            key = await self.get_middleware_key()
            profile = agent.state.middle_context.get(key)
            if profile is None:
                profile = empty_health_profile()
                agent.state.middle_context[key] = profile
                self._log_change("初始化健康画像")

            self._change_log.clear()

            # 从input中提取用户消息（首轮提取，避免只依赖context）
            inputs = input_kwargs.get("inputs")
            if inputs is not None:
                user_text = self._extract_text(inputs)
                if user_text:
                    self._extract_from_text(user_text, profile)

            # ---- 透传reply事件流 ----
            async for event in next_handler(input_kwargs):
                yield event

            # ---- after：reply完成后，扫描最新对话做补充提取 ----
            self._scan_recent_context(agent.state.context, profile)

            # 更新元数据
            if self._change_log:
                profile["profile_version"] += 1
                profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
                self._log_change(f"画像版本升级到 v{profile['profile_version']}")

        # ------------------------------------------------------------------
        # 文本提取工具方法
        # ------------------------------------------------------------------
        def _extract_text(self, inputs: Any) -> str:
            """从Msg或list[Msg]中提取纯文本。"""
            if isinstance(inputs, list):
                return "\n".join(self._extract_text(m) for m in inputs)
            if hasattr(inputs, "get_text_content"):
                return inputs.get_text_content() or ""
            if isinstance(inputs, str):
                return inputs
            return ""

        def _scan_recent_context(self, context: list[Msg], profile: dict) -> None:
            """扫描最近几条消息（避免重复全量扫描），提取健康信息。"""
            # 只扫描最近4条消息（2轮对话）
            for msg in context[-4:]:
                if msg.role == "user":
                    text = msg.get_text_content() if hasattr(msg, "get_text_content") else ""
                    if text:
                        self._extract_from_text(text, profile)

        def _extract_from_text(self, text: str, profile: dict) -> None:
            """从一段文本中基于规则提取健康信息。"""
            self._extract_basic_info(text, profile)
            self._extract_conditions(text, profile)
            self._extract_medications(text, profile)
            self._extract_allergies(text, profile)
            self._extract_alerts(text, profile)

        def _extract_basic_info(self, text: str, profile: dict) -> None:
            """提取基础信息（姓名、年龄、性别）。"""
            # 姓名：XX大爷/XX奶奶/我叫XX
            name_match = re.search(r"(?:我叫|我是)([\u4e00-\u9fa5]{2,4})", text)
            if name_match:
                name = name_match.group(1)
                if not any(suffix in name for suffix in ["大爷", "奶奶", "医生", "阿姨"]):
                    if profile["basic_info"]["name"] != name:
                        profile["basic_info"]["name"] = name
                        self._log_change(f"记录姓名: {name}")
            for title in ["大爷", "奶奶"]:
                m = re.search(rf"([\u4e00-\u9fa5]){title}", text)
                if m:
                    full = m.group(1) + title
                    if profile["basic_info"]["name"] != full:
                        profile["basic_info"]["name"] = full
                        self._log_change(f"记录姓名: {full}")
                    break

            # 年龄
            age_match = re.search(r"(\d{2})\s*岁", text)
            if age_match:
                age = int(age_match.group(1))
                if 50 <= age <= 120 and profile["basic_info"]["age"] != age:
                    profile["basic_info"]["age"] = age
                    self._log_change(f"记录年龄: {age}岁")

            # 性别
            if re.search(r"(爷爷|大爷|老先生)", text):
                if profile["basic_info"]["gender"] != "male":
                    profile["basic_info"]["gender"] = "male"
            elif re.search(r"(奶奶|老太太|阿姨)", text):
                if profile["basic_info"]["gender"] != "female":
                    profile["basic_info"]["gender"] = "female"

        def _extract_conditions(self, text: str, profile: dict) -> None:
            """提取慢病诊断。"""
            existing_codes = {c["code"] for c in profile["conditions"]}
            for kw, (code, display) in CONDITION_RULES.items():
                if kw in text and code not in existing_codes:
                    # 排除否定句："没有高血压"/"不是糖尿病"
                    neg_pattern = rf"(没有|无|不是|并未|未曾).{{0,4}}{kw}"
                    if re.search(neg_pattern, text):
                        continue
                    entry = {
                        "code": code,
                        "display": display,
                        "onset_date": datetime.now().strftime("%Y-%m-%d"),
                        "severity": "moderate",
                        "status": "active",
                        "source": "conversation",
                    }
                    profile["conditions"].append(entry)
                    existing_codes.add(code)
                    self._log_change(f"新发现慢病: {display} ({code})")
                    # 同步到对话摘要
                    fact = f"诊断{display}"
                    if fact not in profile["conversation_summary"]["key_facts"]:
                        profile["conversation_summary"]["key_facts"].append(fact)

        def _extract_medications(self, text: str, profile: dict) -> None:
            """提取用药信息。"""
            existing_names = {m["name"] for m in profile.get("medications", [])}
            # 检测停药
            stop_patterns = [
                r"(?:停|不再吃|不吃了|停了|停用)([\u4e00-\u9fa5]{2,6})",
                r"把([\u4e00-\u9fa5]{2,6})(?:停|停了|停掉)",
            ]
            for pat in stop_patterns:
                for m in re.finditer(pat, text):
                    drug_kw = m.group(1)
                    for kw, info in MEDICATION_RULES.items():
                        if kw in drug_kw:
                            for med in profile.get("medications", []):
                                if med["name"] == info["name"] and med.get("status") != "stopped":
                                    med["status"] = "stopped"
                                    med["stop_date"] = datetime.now().strftime("%Y-%m-%d")
                                    self._log_change(f"停药: {info['name']}")
                            break

            # 检测新药（正在吃/开始吃/服用/加了XX药）
            start_patterns = [
                r"(?:在吃|正在吃|开始吃|服用|吃着|加了|新开了|医生开了)([\u4e00-\u9fa5]{2,8})",
                r"吃([\u4e00-\u9fa5]{2,6})(?:降压|降糖|药|片)",
            ]
            for pat in start_patterns:
                for m in re.finditer(pat, text):
                    drug_kw = m.group(1)
                    for kw, info in MEDICATION_RULES.items():
                        if kw in drug_kw and info["name"] not in existing_names:
                            entry = {
                                "name": info["name"],
                                "dose": info["default_dose"],
                                "frequency": "遵医嘱",
                                "route": info["route"],
                                "start_date": datetime.now().strftime("%Y-%m-%d"),
                                "for_condition": info.get("for_condition"),
                                "status": "active",
                                "source": "conversation",
                            }
                            profile["medications"].append(entry)
                            existing_names.add(info["name"])
                            self._log_change(f"新发现用药: {info['name']}")
                            break

        def _extract_allergies(self, text: str, profile: dict) -> None:
            """提取过敏信息。"""
            if "过敏" not in text:
                return
            existing_substances = {a["substance"] for a in profile["allergies"]}
            for kw, (substance, atype, severity) in ALLERGY_RULES.items():
                if kw in text and substance not in existing_substances:
                    # 排除否定句
                    if re.search(rf"(不对|不过敏|没有).{{0,4}}{kw}", text):
                        continue
                    entry = {
                        "substance": substance,
                        "type": atype,
                        "severity": severity,
                        "reaction": "未知（需进一步确认）",
                        "discovered_at": datetime.now().strftime("%Y-%m-%d"),
                        "source": "conversation",
                    }
                    profile["allergies"].append(entry)
                    existing_substances.add(substance)
                    self._log_change(f"新发现过敏: {substance} ({atype}, {severity})")

        def _extract_alerts(self, text: str, profile: dict) -> None:
            """提取告警事件（如血压值异常、不良反应等）。"""
            # 血压异常（简单正则匹配）
            bp_match = re.search(r"血压(\d{2,3})/?(\d{2,3})?", text)
            if bp_match:
                systolic = int(bp_match.group(1))
                if systolic >= 160:
                    alert = {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "type": "amber",
                        "trigger": f"收缩压{systolic}mmHg",
                        "action": "提醒服药+建议就医",
                    }
                    profile["conversation_summary"]["recent_alerts"].append(alert)
                    self._log_change(f"告警: 收缩压{systolic}mmHg")

            # 副作用关键词
            side_effect_kws = ["水肿", "头晕", "心慌", "皮疹", "呼吸困难", "胃肠不适"]
            for kw in side_effect_kws:
                if kw in text:
                    alert = {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "type": "info",
                        "trigger": f"患者反馈{kw}",
                        "action": "记录并关注",
                    }
                    profile["conversation_summary"]["recent_alerts"].append(alert)
                    self._log_change(f"记录症状: {kw}")
                    break

        def _log_change(self, message: str) -> None:
            """记录本次reply中的画像变更。"""
            ts = datetime.now().strftime("%H:%M:%S")
            self._change_log.append(f"[{ts}] {message}")

        def get_change_log(self) -> list[str]:
            """获取最近一次reply的变更日志（调试/展示用）。"""
            return list(self._change_log)

else:
    # Mock模式下的Middleware基类桩
    class HealthProfileMiddleware:  # type: ignore
        """Mock版健康画像Middleware（无agentscope依赖）。"""

        def __init__(self, user_id: str | None = None) -> None:
            self.user_id = user_id or "anonymous"
            self._change_log: list[str] = []

        async def get_middleware_key(self) -> str:
            return "health_profile"

        def get_change_log(self) -> list[str]:
            return list(self._change_log)

        def _log_change(self, message: str) -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            self._change_log.append(f"[{ts}] {message}")

        def before_reply(self, state: dict, user_text: str) -> None:
            """Mock：reply前初始化画像。"""
            key = "health_profile"
            if key not in state.get("middle_context", {}):
                state.setdefault("middle_context", {})[key] = empty_health_profile()
                self._log_change("初始化健康画像")
            self._change_log.clear()
            self._extract_from_text(user_text, state["middle_context"][key])

        def after_reply(self, state: dict) -> None:
            """Mock：reply后更新版本号。"""
            profile = state["middle_context"]["health_profile"]
            if self._change_log:
                profile["profile_version"] += 1
                profile["updated_at"] = datetime.now().isoformat(timespec="seconds")

        # 复用与真实模式相同的提取逻辑（简化：复制方法）
        def _extract_from_text(self, text: str, profile: dict) -> None:
            self._extract_basic_info(text, profile)
            self._extract_conditions(text, profile)
            self._extract_medications(text, profile)
            self._extract_allergies(text, profile)
            self._extract_alerts(text, profile)

        def _extract_basic_info(self, text: str, profile: dict) -> None:
            name_match = re.search(r"(?:我叫|我是)([\u4e00-\u9fa5]{2,4})", text)
            if name_match:
                name = name_match.group(1)
                if not any(s in name for s in ["大爷", "奶奶", "医生", "阿姨"]):
                    if profile["basic_info"]["name"] != name:
                        profile["basic_info"]["name"] = name
                        self._log_change(f"记录姓名: {name}")
            for title in ["大爷", "奶奶"]:
                m = re.search(rf"([\u4e00-\u9fa5]){title}", text)
                if m:
                    full = m.group(1) + title
                    if profile["basic_info"]["name"] != full:
                        profile["basic_info"]["name"] = full
                        self._log_change(f"记录姓名: {full}")
                    break
            age_match = re.search(r"(\d{2})\s*岁", text)
            if age_match:
                age = int(age_match.group(1))
                if 50 <= age <= 120 and profile["basic_info"]["age"] != age:
                    profile["basic_info"]["age"] = age
                    self._log_change(f"记录年龄: {age}岁")
            if re.search(r"(爷爷|大爷|老先生)", text):
                profile["basic_info"]["gender"] = "male"
            elif re.search(r"(奶奶|老太太|阿姨)", text):
                profile["basic_info"]["gender"] = "female"

        def _extract_conditions(self, text: str, profile: dict) -> None:
            existing_codes = {c["code"] for c in profile["conditions"]}
            for kw, (code, display) in CONDITION_RULES.items():
                if kw in text and code not in existing_codes:
                    if re.search(rf"(没有|无|不是|并未).{{0,4}}{kw}", text):
                        continue
                    profile["conditions"].append({
                        "code": code, "display": display,
                        "onset_date": datetime.now().strftime("%Y-%m-%d"),
                        "severity": "moderate", "status": "active",
                        "source": "conversation",
                    })
                    existing_codes.add(code)
                    self._log_change(f"新发现慢病: {display} ({code})")
                    fact = f"诊断{display}"
                    if fact not in profile["conversation_summary"]["key_facts"]:
                        profile["conversation_summary"]["key_facts"].append(fact)

        def _extract_medications(self, text: str, profile: dict) -> None:
            existing_names = {m["name"] for m in profile.get("medications", [])}
            for pat in [r"(?:停|不再吃|不吃了|停了|停用)([\u4e00-\u9fa5]{2,6})",
                        r"把([\u4e00-\u9fa5]{2,6})(?:停|停了|停掉)"]:
                for m in re.finditer(pat, text):
                    drug_kw = m.group(1)
                    for kw, info in MEDICATION_RULES.items():
                        if kw in drug_kw:
                            for med in profile.get("medications", []):
                                if med["name"] == info["name"] and med.get("status") != "stopped":
                                    med["status"] = "stopped"
                                    med["stop_date"] = datetime.now().strftime("%Y-%m-%d")
                                    self._log_change(f"停药: {info['name']}")
                            break
            for pat in [r"(?:在吃|正在吃|开始吃|服用|吃着|加了|新开了|医生开了)([\u4e00-\u9fa5]{2,8})",
                        r"吃([\u4e00-\u9fa5]{2,6})(?:降压|降糖|药|片)"]:
                for m in re.finditer(pat, text):
                    drug_kw = m.group(1)
                    for kw, info in MEDICATION_RULES.items():
                        if kw in drug_kw and info["name"] not in existing_names:
                            profile["medications"].append({
                                "name": info["name"], "dose": info["default_dose"],
                                "frequency": "遵医嘱", "route": info["route"],
                                "start_date": datetime.now().strftime("%Y-%m-%d"),
                                "for_condition": info.get("for_condition"),
                                "status": "active", "source": "conversation",
                            })
                            existing_names.add(info["name"])
                            self._log_change(f"新发现用药: {info['name']}")
                            break

        def _extract_allergies(self, text: str, profile: dict) -> None:
            if "过敏" not in text:
                return
            existing_substances = {a["substance"] for a in profile["allergies"]}
            for kw, (substance, atype, severity) in ALLERGY_RULES.items():
                if kw in text and substance not in existing_substances:
                    if re.search(rf"(不对|不过敏|没有).{{0,4}}{kw}", text):
                        continue
                    profile["allergies"].append({
                        "substance": substance, "type": atype,
                        "severity": severity, "reaction": "未知（需进一步确认）",
                        "discovered_at": datetime.now().strftime("%Y-%m-%d"),
                        "source": "conversation",
                    })
                    existing_substances.add(substance)
                    self._log_change(f"新发现过敏: {substance} ({atype}, {severity})")

        def _extract_alerts(self, text: str, profile: dict) -> None:
            bp_match = re.search(r"血压(\d{2,3})/?(\d{2,3})?", text)
            if bp_match:
                systolic = int(bp_match.group(1))
                if systolic >= 160:
                    profile["conversation_summary"]["recent_alerts"].append({
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "type": "amber", "trigger": f"收缩压{systolic}mmHg",
                        "action": "提醒服药+建议就医",
                    })
                    self._log_change(f"告警: 收缩压{systolic}mmHg")
            for kw in ["水肿", "头晕", "心慌", "皮疹", "呼吸困难", "胃肠不适"]:
                if kw in text:
                    profile["conversation_summary"]["recent_alerts"].append({
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "type": "info", "trigger": f"患者反馈{kw}",
                        "action": "记录并关注",
                    })
                    self._log_change(f"记录症状: {kw}")
                    break


# ===========================================================================
# 健康画像打印工具
# ===========================================================================
def print_profile_snapshot(profile: dict, change_log: list[str] | None = None) -> None:
    """打印健康画像快照（调试/展示用）。"""
    print("  ┌─ 健康画像快照 " + "─" * 40)
    bi = profile["basic_info"]
    print(f"  │ 基本信息: 姓名={bi.get('name') or '未记录'}  "
          f"年龄={bi.get('age') or '?'}岁  性别={bi.get('gender') or '?'}")
    conds = profile.get("conditions", [])
    if conds:
        cond_str = ", ".join(f"{c['display']}({c['code']})" for c in conds)
        print(f"  │ 慢病({len(conds)}): {cond_str}")
    else:
        print(f"  │ 慢病: 无记录")
    meds = [m for m in profile.get("medications", []) if m.get("status") != "stopped"]
    stopped = [m for m in profile.get("medications", []) if m.get("status") == "stopped"]
    if meds:
        med_str = ", ".join(f"{m['name']} {m.get('dose','')}" for m in meds)
        print(f"  │ 用药({len(meds)}): {med_str}")
    else:
        print(f"  │ 用药: 无记录")
    if stopped:
        print(f"  │ 已停药: {', '.join(m['name'] for m in stopped)}")
    allergs = profile.get("allergies", [])
    if allergs:
        alg_str = ", ".join(f"{a['substance']}[{a['severity']}]" for a in allergs)
        print(f"  │ 过敏({len(allergs)}): {alg_str}")
    else:
        print(f"  │ 过敏: 无记录")
    alerts = profile["conversation_summary"].get("recent_alerts", [])
    if alerts:
        print(f"  │ 近期告警({len(alerts)}): {alerts[-1]['trigger']}")
    facts = profile["conversation_summary"].get("key_facts", [])
    if facts:
        print(f"  │ 关键事实: {'; '.join(facts[-5:])}")
    print(f"  │ 画像版本: v{profile.get('profile_version', 1)}  "
          f"更新时间: {profile.get('updated_at', '?')}")
    if change_log:
        print(f"  │ 本次变更:")
        for log in change_log:
            print(f"  │   {log}")
    print("  └" + "─" * 54)


# ===========================================================================
# 真实AgentScope运行模式
# ===========================================================================
async def run_real_mode() -> None:
    """使用真实AgentScope运行健康画像Middleware示例。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("未设置DASHSCOPE_API_KEY，切换到Mock模式")
        await run_mock_mode()
        return

    print("=" * 60)
    print("GerClaw健康画像Middleware示例 - 真实模式（AgentScope）")
    print("=" * 60)

    credential = DashScopeCredential(api_key=api_key)
    chat_model = DashScopeChatModel(
        credential=credential, model="qwen-plus", stream=False,
    )

    # 创建自定义健康画像Middleware
    profile_mw = HealthProfileMiddleware(user_id="elder_zhang_001")

    agent = Agent(
        name="gerclaw_health_assistant",
        system_prompt=(
            "你是GerClaw老年医疗AI助手张医生。请用温和、耐心、通俗易懂的语气"
            "与老年患者交流。在对话中注意收集患者的慢病、用药、过敏信息，"
            "发现异常指标时给出安全提醒。每次回复简洁不超过100字。"
        ),
        model=chat_model,
        toolkit=Toolkit(),
        middlewares=[profile_mw],
    )

    # 模拟多轮对话
    dialogues = [
        "医生你好，我是张大爷，今年72岁了。",
        "我有高血压，一直在吃氨氯地平控制。",
        "哦对了，我对青霉素过敏，上次打针差点出事。",
        "医生我最近血压165/95，脚踝还有点肿，这是怎么回事？",
    ]

    for i, text in enumerate(dialogues, 1):
        print(f"\n--- 第{i}轮对话 ---")
        print(f"  [张大爷] {text}")
        reply = await agent.reply(UserMsg("张大爷", text))
        reply_text = reply.get_text_content()
        print(f"  [张医生] {reply_text[:200]}{'...' if len(reply_text) > 200 else ''}")
        # 打印Middleware提取的健康画像
        profile = agent.state.middle_context.get("health_profile", {})
        print_profile_snapshot(profile, profile_mw.get_change_log())

    print("\n" + "=" * 60)
    print("示例运行完成！HealthProfileMiddleware自动维护了健康画像。")
    print("=" * 60)


# ===========================================================================
# Mock模式（无AgentScope依赖也可验证Middleware规则提取逻辑）
# ===========================================================================
async def run_mock_mode() -> None:
    """使用Mock组件演示Middleware画像提取流程。"""
    print("=" * 60)
    print("GerClaw健康画像Middleware示例 - Mock模式")
    print("=" * 60)
    print("说明：本模式使用规则匹配演示健康画像Middleware的自动提取能力。")
    print("      安装agentscope并设置DASHSCOPE_API_KEY可运行真实LLM模式。\n")

    # 初始化Middleware和状态（模拟Agent.state）
    mw = HealthProfileMiddleware(user_id="elder_zhang_001")
    state: dict[str, Any] = {"middle_context": {}}

    # 模拟多轮对话，每轮调用before_reply→（模拟LLM回复）→after_reply
    dialogues = [
        # 第1轮：初诊，告知姓名年龄
        ("张大爷", "医生你好，我是张大爷，今年72岁了。"),
        # 第2轮：告知高血压+氨氯地平
        ("张大爷", "我有高血压好几年了，一直在吃氨氯地平，每天一次。"),
        # 第3轮：告知青霉素过敏+新增糖尿病+二甲双胍
        ("张大爷", "哦对了，我对青霉素过敏，上次皮试红肿。最近查出来糖尿病，医生开了二甲双胍。"),
        # 第4轮：血压异常+副作用反馈
        ("张大爷", "医生我今天量血压165/95，而且脚踝有点水肿，是不是药的问题？"),
        # 第5轮：加药（他汀）
        ("张大爷", "医生说我血脂也高，让我加了他汀类药物。"),
    ]

    for i, (user_name, text) in enumerate(dialogues, 1):
        print(f"\n--- 第{i}轮对话 ---")
        print(f"  [{user_name}] {text}")

        # 1. before_reply（Middleware提取画像）
        mw.before_reply(state, text)

        # 2. 模拟LLM生成简单回复
        reply = _mock_llm_reply(text, state["middle_context"]["health_profile"])
        print(f"  [张医生] {reply}")

        # 3. after_reply（Middleware更新版本号）
        mw.after_reply(state)

        # 4. 打印画像快照
        profile = state["middle_context"]["health_profile"]
        print_profile_snapshot(profile, mw.get_change_log())

    # 最终验证
    print("\n" + "=" * 60)
    print("【最终健康画像验证】")
    print("=" * 60)
    hp = state["middle_context"]["health_profile"]
    assert hp["basic_info"]["name"] == "张大爷", "姓名应被记录"
    assert hp["basic_info"]["age"] == 72, "年龄应被记录"
    assert any(c["code"] == "I10" for c in hp["conditions"]), "高血压应被记录"
    assert any(c["code"] == "E11" for c in hp["conditions"]), "糖尿病应被记录"
    assert any("氨氯地平" in m["name"] for m in hp["medications"]), "氨氯地平应被记录"
    assert any("二甲双胍" in m["name"] for m in hp["medications"]), "二甲双胍应被记录"
    assert any(a["substance"] == "青霉素" for a in hp["allergies"]), "青霉素过敏应被记录"
    assert hp["conversation_summary"]["recent_alerts"], "血压告警应被记录"
    assert hp["profile_version"] >= 5, f"版本号应>=5（当前v{hp['profile_version']}）"
    print("  [验证通过] HealthProfileMiddleware成功从5轮对话中提取了：")
    active_meds = [m for m in hp["medications"] if m.get("status") != "stopped"]
    print(f"    - {len(hp['conditions'])}项慢病诊断")
    print(f"    - {len(active_meds)}项在用药物")
    print(f"    - {len(hp['allergies'])}项过敏记录")
    print(f"    - {len(hp['conversation_summary']['recent_alerts'])}条健康告警")
    print(f"    - 画像版本v{hp['profile_version']}")
    print("=" * 60)


def _mock_llm_reply(text: str, profile: dict) -> str:
    """Mock LLM回复（基于规则的简单回应，用于演示）。"""
    conds = [c["display"] for c in profile.get("conditions", [])]
    meds = [m["name"] for m in profile.get("medications", []) if m.get("status") != "stopped"]
    allergs = [a["substance"] for a in profile.get("allergies", [])]

    if "过敏" in text and "青霉素" in text:
        return "好的张大爷，我已经记录您的青霉素过敏史，这非常重要！以后就诊时务必告知医生。"
    if "高血压" in text or "氨氯地平" in text:
        return "好的，您有高血压并在服用氨氯地平。请每天固定时间服药，定期监测血压。"
    if "糖尿病" in text or "二甲双胍" in text:
        return "了解，二甲双胍建议餐中或餐后服用，可以减少胃肠不适。请注意控制饮食和监测血糖。"
    if "水肿" in text or "165" in text:
        return ("张大爷，您的血压165/95偏高，脚踝水肿可能是氨氯地平的副作用。"
                "建议您：1) 不要自行停药；2) 尽快来医院复诊，考虑调整用药方案；"
                "3) 注意低盐饮食，适当抬高下肢。")
    if "他汀" in text or "血脂" in text:
        return "好的，他汀类药物建议晚上睡前服用。用药期间请注意有无肌肉酸痛等不适，定期复查肝功能和血脂。"
    if "72岁" in text or "我是张大爷" in text:
        return f"张大爷您好，我是您的GerClaw健康助手张医生。请问您有什么健康问题需要咨询？"
    if conds or meds:
        return f"好的张大爷，我已记录您的情况。有任何不适随时告诉我。"
    return "张大爷您好，请告诉我您的健康情况。"


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
