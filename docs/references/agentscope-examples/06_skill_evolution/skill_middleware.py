# -*- coding: utf-8 -*-
"""
GerClaw 老年医疗AI平台 — Skill使用审计中间件示例

本示例演示如何通过自定义Middleware实现Skill使用的三大治理能力：
  1. 使用计数统计：记录每个工具/Skill被调用的次数、成功/失败次数
  2. 审计日志：记录每次调用的时间、操作者、工具名、参数摘要、执行结果
  3. 使用频率限制：对高频调用进行限流，防止滥用或异常调用

AgentScope提供两层中间件机制：
  - ToolMiddlewareBase（工具级）：附加到单个工具，洋葱模型包装工具执行
  - MiddlewareBase（Agent级）：附加到Agent，拦截reply/reasoning/acting/model_call等阶段

本示例使用 ToolMiddlewareBase 实现工具级中间件（更轻量、自包含），
配合上一示例的"老年跌倒风险评估"Skill，演示完整的审计流程。

运行方式：
    python skill_middleware.py
"""
import asyncio
import json
import os
import tempfile
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Callable

from pydantic import Field

from agentscope.skill import LocalSkillLoader
from agentscope.state import AgentState
from agentscope.tool import (
    FunctionTool, ParamsBase, ToolChunk, ToolMiddlewareBase, Toolkit, ToolResponse,
)


# ============================================================
# 1. 使用计数中间件：统计工具调用次数
# ============================================================

class SkillUsageCountMiddleware(ToolMiddlewareBase):
    """Skill使用计数中间件。

    记录每个工具的：总调用次数、成功次数、失败次数、最后调用时间。
    可用于生成Skill使用报表、发现高频/低频Skill、检测异常模式。
    """

    def __init__(self) -> None:
        # 使用字典存储计数：{工具名: {total, success, error, last_called}}
        self.stats: dict[str, dict[str, Any]] = {}

    async def on_tool_call(
        self,
        tool: Any,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """拦截工具调用，在执行前后更新计数。"""
        tool_name = tool.name

        # 前置：初始化计数
        if tool_name not in self.stats:
            self.stats[tool_name] = {
                "total": 0, "success": 0, "error": 0,
                "last_called": None, "last_duration_ms": 0,
            }
        self.stats[tool_name]["total"] += 1
        start_time = time.monotonic()

        error_occurred = False
        try:
            # 执行工具
            async for chunk in next_handler(**input_kwargs):
                # 检测chunk中的错误状态
                if hasattr(chunk, "state") and chunk.state == "error":
                    error_occurred = True
                yield chunk
        except Exception:
            error_occurred = True
            raise
        finally:
            # 后置：更新统计
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            if error_occurred:
                self.stats[tool_name]["error"] += 1
            else:
                self.stats[tool_name]["success"] += 1
            self.stats[tool_name]["last_called"] = datetime.now().isoformat()
            self.stats[tool_name]["last_duration_ms"] = elapsed_ms

    def get_report(self) -> str:
        """生成格式化的使用统计报告。"""
        if not self.stats:
            return "暂无工具调用记录。"

        lines = ["=== Skill/工具使用统计报告 ==="]
        lines.append(f"{'工具名':<30} {'总调用':>6} {'成功':>6} {'失败':>6} {'平均耗时':>8} {'最后调用'}")
        lines.append("-" * 90)
        for name, s in sorted(self.stats.items()):
            total = s["total"]
            avg = s["last_duration_ms"] if total == 1 else s.get("last_duration_ms", 0)
            lines.append(
                f"{name:<30} {total:>6} {s['success']:>6} {s['error']:>6} "
                f"{avg:>6}ms {s['last_called'] or 'N/A':>20}"
            )
        return "\n".join(lines)


# ============================================================
# 2. 审计日志中间件：记录每次调用的详细信息
# ============================================================

class SkillAuditLogMiddleware(ToolMiddlewareBase):
    """Skill审计日志中间件。

    记录每次工具/Skill调用的完整审计信息：
    - 时间戳、工具名、调用参数（可配置脱敏）
    - 执行状态（成功/失败）、耗时
    - 结果摘要（截取前N个字符）

    审计日志符合GerClaw医疗场景要求：L2/L3级Skill调用需保留审计链≥10年。
    """

    def __init__(
        self,
        log_file: str | None = None,
        max_result_chars: int = 200,
        sensitive_params: set[str] | None = None,
    ) -> None:
        """初始化审计中间件。

        Args:
            log_file: 日志文件路径（None则仅内存存储）
            max_result_chars: 结果最大记录字符数
            sensitive_params: 需要脱敏的参数名集合（如patient_id）
        """
        self.log_file = log_file
        self.max_result_chars = max_result_chars
        self.sensitive_params = sensitive_params or {"patient_id", "id_card", "phone"}
        self.records: list[dict[str, Any]] = []

    def _sanitize_params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """对敏感参数进行脱敏处理。"""
        sanitized = {}
        for k, v in kwargs.items():
            if k in self.sensitive_params and isinstance(v, str) and len(v) > 4:
                sanitized[k] = v[:2] + "****" + v[-2:]
            else:
                sanitized[k] = v
        return sanitized

    def _write_log(self, record: dict[str, Any]) -> None:
        """写入日志到文件。"""
        self.records.append(record)
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def on_tool_call(
        self,
        tool: Any,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """拦截工具调用，记录审计日志。"""
        call_id = f"audit_{int(time.time()*1000)}_{id(tool) % 10000}"
        start_time = time.monotonic()
        timestamp = datetime.now().isoformat()

        # 前置：记录调用开始
        sanitized_params = self._sanitize_params(input_kwargs)
        record = {
            "call_id": call_id,
            "timestamp": timestamp,
            "tool_name": tool.name,
            "params_summary": {
                k: str(v)[:50] for k, v in sanitized_params.items()
            },
            "status": "started",
            "duration_ms": 0,
            "result_summary": "",
        }

        result_chunks: list[str] = []
        error_occurred = False

        try:
            async for chunk in next_handler(**input_kwargs):
                # 收集结果文本
                if hasattr(chunk, "content"):
                    for block in chunk.content:
                        if hasattr(block, "text"):
                            result_chunks.append(block.text)
                if hasattr(chunk, "state") and chunk.state == "error":
                    error_occurred = True
                yield chunk
        except Exception as e:
            error_occurred = True
            record["error_message"] = str(e)
            raise
        finally:
            # 后置：记录调用结束
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            full_result = "".join(result_chunks)
            record["status"] = "error" if error_occurred else "success"
            record["duration_ms"] = elapsed_ms
            record["result_summary"] = full_result[: self.max_result_chars]
            self._write_log(record)

    def print_recent(self, n: int = 5) -> None:
        """打印最近N条审计记录。"""
        print(f"\n=== 最近 {min(n, len(self.records))} 条审计日志 ===")
        for rec in self.records[-n:]:
            status_tag = "✓" if rec["status"] == "success" else "✗"
            print(
                f"  [{rec['timestamp']}] {status_tag} {rec['tool_name']} "
                f"({rec['duration_ms']}ms) params={list(rec['params_summary'].keys())}"
            )


# ============================================================
# 3. 频率限制中间件：防止滥用
# ============================================================

class SkillRateLimitMiddleware(ToolMiddlewareBase):
    """Skill使用频率限制中间件。

    实现滑动窗口限流：在指定时间窗口内，每个工具最多调用max_calls次。
    超过限制时返回错误提示，不执行实际工具调用。

    适用于：
    - 防止高风险Skill被频繁调用（如处方审核、影像识别）
    - 控制成本（限制昂贵API的调用频率）
    - 检测异常调用模式（如批量爬虫式调用）
    """

    def __init__(
        self,
        max_calls: int = 10,
        window_seconds: float = 60.0,
        blocked_tools: set[str] | None = None,
    ) -> None:
        """初始化限流中间件。

        Args:
            max_calls: 时间窗口内最大调用次数
            window_seconds: 时间窗口大小（秒）
            blocked_tools: 需要特殊限流的工具集合（None则对所有工具生效）
        """
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.blocked_tools = blocked_tools
        # 调用历史：{工具名: [timestamp1, timestamp2, ...]}
        self.call_history: dict[str, list[float]] = {}

    def _is_rate_limited(self, tool_name: str) -> tuple[bool, int, float]:
        """检查是否触发限流。

        Returns:
            (是否限流, 当前窗口调用次数, 距窗口重置剩余秒数)
        """
        now = time.monotonic()
        history = self.call_history.get(tool_name, [])

        # 清理过期记录
        window_start = now - self.window_seconds
        history = [t for t in history if t > window_start]
        self.call_history[tool_name] = history

        current_count = len(history)
        if current_count >= self.max_calls:
            oldest = min(history) if history else now
            wait_seconds = self.window_seconds - (now - oldest)
            return True, current_count, max(0, wait_seconds)
        return False, current_count, 0

    async def on_tool_call(
        self,
        tool: Any,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        """拦截工具调用，检查频率限制。"""
        tool_name = tool.name

        # 如果指定了blocked_tools，仅对这些工具限流
        if self.blocked_tools is not None and tool_name not in self.blocked_tools:
            async for chunk in next_handler(**input_kwargs):
                yield chunk
            return

        # 检查限流
        limited, count, wait = self._is_rate_limited(tool_name)
        if limited:
            error_msg = (
                f"RateLimitExceeded: 工具 '{tool_name}' 在{self.window_seconds}秒内"
                f"已调用{count}次（上限{self.max_calls}次），"
                f"请等待{wait:.1f}秒后重试。"
            )
            print(f"  [限流] {error_msg}")
            yield ToolChunk(
                content=[{"type": "text", "text": error_msg}],
                state="error",
                is_last=True,
            )
            return

        # 记录本次调用时间
        self.call_history.setdefault(tool_name, []).append(time.monotonic())

        # 正常执行
        async for chunk in next_handler(**input_kwargs):
            yield chunk


# ============================================================
# 辅助：创建跌倒风险评估Skill目录（同custom_medical_skill.py）
# ============================================================

FALL_RISK_SKILL_MD = """---
name: fall-risk-assessment
description: Use when assessing fall risk for elderly patients aged 60+. Triggers on admission screening, mobility complaints, history of falls, or post-fall evaluation.
display_name: 老年跌倒风险评估
version: "1.0.0"
medical:
  risk_level: "medium"
  requires_approval: false
---

# 老年跌倒风险评估（Morse跌倒量表）

## When to Use
- 60岁以上老年患者入院/入住养老院时
- 有跌倒史或步态不稳主诉

## Core Protocol
1. 确认患者年龄≥60岁
2. 使用 fall_risk_calculator 评估6个维度
3. 根据MFS评分分级：0-24低风险，25-50中风险，≥51高风险
4. 给出对应干预措施
"""


def create_temp_skill_dir() -> tuple[str, str]:
    """创建临时Skill目录。返回(temp_dir, skill_dir)。"""
    temp_dir = tempfile.mkdtemp(prefix="gerclaw_middleware_")
    skill_dir = os.path.join(temp_dir, "fall-risk-assessment")
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(FALL_RISK_SKILL_MD)
    return temp_dir, skill_dir


# ============================================================
# 跌倒风险评估工具函数
# ============================================================

async def calculate_fall_risk(
    age: int,
    fall_history: bool = False,
    secondary_diagnosis: bool = False,
    ambulatory_aid: str = "none",
    iv_present: bool = False,
    gait: str = "normal",
    mental_status_impaired: bool = False,
) -> str:
    """计算Morse跌倒量表评分（简化版，用于中间件演示）。

    Args:
        age: 患者年龄（≥60）
        fall_history: 过去3个月是否有跌倒史
        secondary_diagnosis: 是否有多诊断
        ambulatory_aid: 行走辅助方式
        iv_present: 是否有静脉输液
        gait: 步态状况
        mental_status_impaired: 精神状态是否受损
    """
    score = 0
    if fall_history:
        score += 25
    if secondary_diagnosis:
        score += 15
    if ambulatory_aid == "crutches":
        score += 15
    elif ambulatory_aid == "furniture":
        score += 30
    if iv_present:
        score += 20
    if gait == "weak":
        score += 10
    elif gait == "impaired":
        score += 20
    if mental_status_impaired:
        score += 15

    if score <= 24:
        level = "低风险"
    elif score <= 50:
        level = "中风险"
    else:
        level = "高风险"

    return f"MFS评分{score}分，{level}。（AI辅助评估，须医护复核）"


# ============================================================
# 主演示流程
# ============================================================

async def demo_middleware_setup() -> tuple[Toolkit, SkillUsageCountMiddleware, SkillAuditLogMiddleware, SkillRateLimitMiddleware, str]:
    """演示：创建中间件实例，注册到工具，构建Toolkit。"""
    print("=" * 60)
    print("步骤1：创建并配置三层中间件")
    print("=" * 60)

    # 创建三个中间件实例
    count_mw = SkillUsageCountMiddleware()
    audit_mw = SkillAuditLogMiddleware(max_result_chars=150)
    rate_limit_mw = SkillRateLimitMiddleware(
        max_calls=3,              # 每60秒最多3次（演示用，实际可设更高）
        window_seconds=60.0,
        blocked_tools={"fall_risk_calculator"},  # 仅对评估工具限流
    )

    print("  ✓ SkillUsageCountMiddleware（计数统计）已创建")
    print("  ✓ SkillAuditLogMiddleware（审计日志）已创建")
    print("  ✓ SkillRateLimitMiddleware（频率限制：3次/60秒）已创建")

    # 将中间件附加到工具（洋葱模型：先注册的在外层）
    calc_tool = FunctionTool(
        func=calculate_fall_risk,
        name="fall_risk_calculator",
        is_read_only=True,
        is_concurrency_safe=True,
        middlewares=[count_mw, audit_mw, rate_limit_mw],
    )
    print("\n  中间件已附加到 fall_risk_calculator 工具")
    print("  洋葱顺序：计数 → 审计 → 限流 → 实际工具执行")

    # 创建Skill和Toolkit
    temp_dir, _ = create_temp_skill_dir()
    loader = LocalSkillLoader(directory=temp_dir, scan_subdir=True)

    toolkit = Toolkit(
        tools=[calc_tool],
        skills_or_loaders=[loader],
    )

    schemas = await toolkit.get_tool_schemas()
    print(f"\n  Toolkit已就绪，共 {len(schemas)} 个工具")
    for s in schemas:
        print(f"    - {s['function']['name']}")

    return toolkit, count_mw, audit_mw, rate_limit_mw, temp_dir


async def demo_normal_calls(
    toolkit: Toolkit,
    count_mw: SkillUsageCountMiddleware,
    audit_mw: SkillAuditLogMiddleware,
) -> None:
    """演示：正常调用3次，观察计数和审计记录。"""
    print("\n" + "=" * 60)
    print("步骤2：正常调用3次跌倒风险评估")
    print("=" * 60)

    state = AgentState()
    test_cases = [
        {"age": 72, "fall_history": False, "secondary_diagnosis": False,
         "gait": "normal", "_desc": "72岁健康老人"},
        {"age": 78, "fall_history": True, "secondary_diagnosis": True,
         "ambulatory_aid": "crutches", "gait": "weak", "_desc": "78岁有跌倒史"},
        {"age": 85, "fall_history": True, "secondary_diagnosis": True,
         "ambulatory_aid": "furniture", "gait": "impaired",
         "mental_status_impaired": True, "_desc": "85岁高风险患者"},
    ]

    for i, case in enumerate(test_cases, 1):
        desc = case.pop("_desc")
        print(f"\n  --- 第{i}次调用：{desc} ---")
        tool_call = type("TC", (), {})()  # 简单构造
        tc_call = __import__("agentscope.message", fromlist=["ToolCallBlock"]).ToolCallBlock(
            id=f"call_{i}",
            name="fall_risk_calculator",
            input=json.dumps(case),
        )
        async for result in toolkit.call_tool(tc_call, state):
            if hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        print(f"  结果: {block.text}")

    # 输出统计报告
    print("\n" + count_mw.get_report())
    audit_mw.print_recent(n=3)


async def demo_rate_limit(
    toolkit: Toolkit,
    rate_limit_mw: SkillRateLimitMiddleware,
) -> None:
    """演示：触发频率限制。"""
    print("\n" + "=" * 60)
    print("步骤3：触发频率限制（第4次调用应被拒绝）")
    print("=" * 60)

    state = AgentState()
    tc_call = __import__("agentscope.message", fromlist=["ToolCallBlock"]).ToolCallBlock(
        id="call_4",
        name="fall_risk_calculator",
        input=json.dumps({"age": 65, "fall_history": False}),
    )

    print("  尝试第4次调用（上限3次/60秒）...")
    async for result in toolkit.call_tool(tc_call, state):
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    print(f"  返回: {block.text}")

    # 查看限流状态
    limited, count, wait = rate_limit_mw._is_rate_limited("fall_risk_calculator")
    print(f"\n  限流状态: 已触发={limited}, 当前窗口调用={count}次")


async def demo_skill_viewer_audit(
    toolkit: Toolkit,
    audit_mw: SkillAuditLogMiddleware,
    count_mw: SkillUsageCountMiddleware,
) -> None:
    """演示：Skill查看器的调用也会被审计（因为它也是Toolkit中的工具）。"""
    print("\n" + "=" * 60)
    print("步骤4：调用Skill查看器（同样被审计）")
    print("=" * 60)

    state = AgentState()
    tc_call = __import__("agentscope.message", fromlist=["ToolCallBlock"]).ToolCallBlock(
        id="view_skill",
        name="Skill",
        input=json.dumps({"skill": "fall-risk-assessment"}),
    )

    print("  调用 Skill 工具查看 fall-risk-assessment ...")
    async for result in toolkit.call_tool(tc_call, state):
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    print(f"  返回内容（前120字符）: {block.text[:120]}...")

    # 最终统计
    print("\n" + "=" * 60)
    print("最终统计与审计报告")
    print("=" * 60)
    print(count_mw.get_report())
    audit_mw.print_recent(n=10)


async def main() -> None:
    """主入口。"""
    print("GerClaw 老年医疗AI平台 — Skill使用审计中间件演示")
    print("AgentScope ToolMiddlewareBase 计数/审计/限流示例\n")

    toolkit, count_mw, audit_mw, rate_limit_mw, temp_dir = await demo_middleware_setup()
    await demo_normal_calls(toolkit, count_mw, audit_mw)
    await demo_rate_limit(toolkit, rate_limit_mw)
    await demo_skill_viewer_audit(toolkit, audit_mw, count_mw)

    # 清理临时目录
    import shutil
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("示例运行完成。")
    print("=" * 60)
    print("\n关键要点：")
    print("1. ToolMiddlewareBase 通过洋葱模型包装工具执行，pre/post逻辑清晰")
    print("2. 多个中间件按注册顺序组成洋葱链：先注册→外层，后注册→内层")
    print("3. 审计中间件可对接日志系统/数据库，满足医疗审计≥10年保存要求")
    print("4. 限流中间件可按工具粒度配置，高风险Skill设置更严格的限流策略")
    print("5. Agent级MiddlewareBase（on_acting钩子）可实现跨工具的全局审计，")
    print("   适合统一拦截所有工具调用（参见参考文档第2.6节）")


if __name__ == "__main__":
    asyncio.run(main())
