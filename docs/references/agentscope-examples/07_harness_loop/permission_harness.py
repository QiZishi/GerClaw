# -*- coding: utf-8 -*-
"""
permission_harness.py —— GerClaw老年医疗AI · AgentScope权限引擎演示

对应参考索引: agentscope参考/07_AgentHarness回路.md §7
核心API: PermissionEngine + PermissionRule + PermissionContext + PermissionMode

功能: 演示PermissionEngine权限检查流程（不启动完整Agent，不需要LLM/API Key）。
     定义5个医疗工具（药品查询/开药/体征查询/修改诊断/开具检查），
     通过PermissionRule配置医疗安全策略，模拟不同操作的权限决策结果，
     并演示4种PermissionMode下的行为差异。

运行: python permission_harness.py
"""

import asyncio
from typing import Any

from agentscope.permission import (
    PermissionEngine, PermissionContext, PermissionMode,
    PermissionRule, PermissionBehavior, PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk
from agentscope.message import TextBlock


# ---- 1. 医疗工具定义 ----

class QueryDrugInfo(ToolBase):
    """药品查询 — 低风险只读，check_permissions返回PASSTHROUGH由规则决定。"""
    name = "query_drug_info"
    description = "查询药品说明书（只读）"
    input_schema = {"type": "object", "properties": {"drug_name": {"type": "string"}}, "required": ["drug_name"]}
    is_concurrency_safe = True; is_read_only = True; is_external_tool = False; is_mcp = False
    async def check_permissions(self, tool_input, context):
        return PermissionDecision(behavior=PermissionBehavior.PASSTHROUGH, message="只读查询")
    async def __call__(self, drug_name, **kw):
        return ToolChunk(content=[TextBlock(text=f"[药品信息] {drug_name}")])


class PrescribeDrug(ToolBase):
    """开药 — 高风险；受控药物/老年高剂量返回bypass_immune=True的ASK。"""
    name = "prescribe_drug"
    description = "开立处方（需医生审批）"
    input_schema = {"type": "object", "properties": {
        "drug_name": {"type": "string"}, "dosage": {"type": "string"},
        "patient_age": {"type": "integer"}}, "required": ["drug_name", "dosage", "patient_age"]}
    is_concurrency_safe = False; is_read_only = False; is_external_tool = False; is_mcp = False
    async def check_permissions(self, tool_input, context):
        drug = tool_input.get("drug_name", "")
        age = tool_input.get("patient_age", 0)
        if drug in {"吗啡", "地西泮", "芬太尼"}:
            return PermissionDecision(behavior=PermissionBehavior.ASK,
                message=f"受控药物({drug})需主任审批", decision_reason="controlled_drug", bypass_immune=True)
        if age >= 75:
            return PermissionDecision(behavior=PermissionBehavior.ASK,
                message=f"老年患者({age}岁)处方需确认剂量", decision_reason="elderly_dosage", bypass_immune=True)
        return PermissionDecision(behavior=PermissionBehavior.PASSTHROUGH, message="普通处方")
    async def __call__(self, drug_name, dosage, **kw):
        return ToolChunk(content=[TextBlock(text=f"[处方] {drug_name} {dosage}")])


class CheckVitals(ToolBase):
    """体征查询 — 只读低风险。"""
    name = "check_vital_signs"
    description = "查询患者体征（只读）"
    input_schema = {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"]}
    is_concurrency_safe = True; is_read_only = True; is_external_tool = False; is_mcp = False
    async def check_permissions(self, tool_input, context):
        return PermissionDecision(behavior=PermissionBehavior.PASSTHROUGH, message="体征只读")
    async def __call__(self, patient_id, **kw):
        return ToolChunk(content=[TextBlock(text=f"[体征] {patient_id}: BP 145/90")])


class ModifyDiagnosis(ToolBase):
    """修改诊断 — 高风险；危重诊断bypass_immune ASK。"""
    name = "modify_diagnosis"
    description = "修改诊断结论（需审批）"
    input_schema = {"type": "object", "properties": {
        "patient_id": {"type": "string"}, "new_diagnosis": {"type": "string"}},
        "required": ["patient_id", "new_diagnosis"]}
    is_concurrency_safe = False; is_read_only = False; is_external_tool = False; is_mcp = False
    async def check_permissions(self, tool_input, context):
        diag = tool_input.get("new_diagnosis", "")
        if any(c in diag for c in {"心肌梗死", "脑卒中", "肺栓塞"}):
            return PermissionDecision(behavior=PermissionBehavior.ASK,
                message=f"危重诊断({diag})需主任审批", decision_reason="critical_diag", bypass_immune=True)
        return PermissionDecision(behavior=PermissionBehavior.PASSTHROUGH, message="普通诊断修改")
    async def __call__(self, patient_id, new_diagnosis, **kw):
        return ToolChunk(content=[TextBlock(text=f"[诊断] {patient_id}→{new_diagnosis}")])


class OrderExam(ToolBase):
    """开具检查 — 中风险。"""
    name = "order_exam"
    description = "开具检查项目（需确认）"
    input_schema = {"type": "object", "properties": {
        "exam_name": {"type": "string"}, "patient_id": {"type": "string"}},
        "required": ["exam_name", "patient_id"]}
    is_concurrency_safe = True; is_read_only = False; is_external_tool = False; is_mcp = False
    async def check_permissions(self, tool_input, context):
        return PermissionDecision(behavior=PermissionBehavior.PASSTHROUGH, message="检查开立")
    async def __call__(self, exam_name, patient_id, **kw):
        return ToolChunk(content=[TextBlock(text=f"[检查单] {patient_id}:{exam_name}")])


# ---- 2. 辅助函数 ----

def _sep(t): print(f"\n{'='*62}\n  {t}\n{'='*62}")

def _label(b):
    m = {PermissionBehavior.ALLOW: "\033[92m✓ ALLOW 自动通过\033[0m",
         PermissionBehavior.DENY:  "\033[91m✗ DENY  拒绝执行\033[0m",
         PermissionBehavior.ASK:   "\033[93m? ASK   需医生确认\033[0m",
         PermissionBehavior.PASSTHROUGH: "→ PASSTHROUGH"}
    return m.get(b, str(b))

async def check(engine, tool, inp, scenario=""):
    d = await engine.check_permission(tool, inp)
    bi = " [bypass_immune]" if d.bypass_immune else ""
    print(f"  {scenario:<22s} → {_label(d.behavior)}{bi}")
    print(f"    {d.message}")
    if d.decision_reason: print(f"    原因: {d.decision_reason}")
    return d

def build_ctx(mode=PermissionMode.DEFAULT):
    return PermissionContext(mode=mode,
        allow_rules={
            "query_drug_info": [PermissionRule(tool_name="query_drug_info", rule_content=None,
                behavior=PermissionBehavior.ALLOW, source="medicalPolicy")],
            "check_vital_signs": [PermissionRule(tool_name="check_vital_signs", rule_content=None,
                behavior=PermissionBehavior.ALLOW, source="medicalPolicy")],
        },
        ask_rules={
            "prescribe_drug": [PermissionRule(tool_name="prescribe_drug", rule_content=None,
                behavior=PermissionBehavior.ASK, source="medicalPolicy")],
            "modify_diagnosis": [PermissionRule(tool_name="modify_diagnosis", rule_content=None,
                behavior=PermissionBehavior.ASK, source="medicalPolicy")],
            "order_exam": [PermissionRule(tool_name="order_exam", rule_content=None,
                behavior=PermissionBehavior.ASK, source="medicalPolicy")],
        },
        deny_rules={})


# ---- 3. 主流程 ----

async def main():
    print("\nGerClaw · PermissionEngine 权限引擎演示\n")

    # Part 1: DEFAULT模式基础检查
    _sep("Part 1: DEFAULT模式 — 医疗工具权限检查")
    eng = PermissionEngine(build_ctx(PermissionMode.DEFAULT))
    cases = [
        ("药品查询(氨氯地平)", QueryDrugInfo(), {"drug_name": "氨氯地平"}),
        ("体征查询(P001)",     CheckVitals(),   {"patient_id": "P001"}),
        ("普通开药(72岁)",     PrescribeDrug(), {"drug_name": "氨氯地平", "dosage": "5mg/日", "patient_age": 72}),
        ("老年开药(82岁)",     PrescribeDrug(), {"drug_name": "氨氯地平", "dosage": "10mg/日", "patient_age": 82}),
        ("受控药物(吗啡)",     PrescribeDrug(), {"drug_name": "吗啡", "dosage": "10mg", "patient_age": 78}),
        ("普通诊断修改",       ModifyDiagnosis(), {"patient_id": "P001", "new_diagnosis": "高血压"}),
        ("危重诊断(心梗)",     ModifyDiagnosis(), {"patient_id": "P001", "new_diagnosis": "急性心肌梗死"}),
        ("开具血常规",         OrderExam(), {"exam_name": "血常规", "patient_id": "P001"}),
    ]
    for name, tool, inp in cases:
        await check(eng, tool, inp, name)

    # Part 2: 不同PermissionMode对比
    _sep("Part 2: PermissionMode对比 — 普通处方(二甲双胍,65岁)")
    for mode in [PermissionMode.DEFAULT, PermissionMode.EXPLORE, PermissionMode.BYPASS, PermissionMode.DONT_ASK]:
        eng_m = PermissionEngine(build_ctx(mode))
        print(f"\n  模式: {mode.value}")
        await check(eng_m, PrescribeDrug(), {"drug_name": "二甲双胍", "dosage": "500mg bid", "patient_age": 65})

    # Part 3: bypass_immune安全机制
    _sep("Part 3: bypass_immune — 即使误配allow规则，受控药物仍需审批")
    ctx_s = build_ctx(PermissionMode.DEFAULT)
    eng_s = PermissionEngine(ctx_s)
    eng_s.add_rule(PermissionRule(tool_name="prescribe_drug", rule_content=None,
        behavior=PermissionBehavior.ALLOW, source="bad_config"))
    await check(eng_s, PrescribeDrug(), {"drug_name": "吗啡", "dosage": "10mg", "patient_age": 78}, "受控药物(吗啡)")

    # Part 4: 动态规则（医生批准后自动放行）
    _sep("Part 4: 动态add_rule — 医生批准后同类操作自动放行")
    eng_d = PermissionEngine(build_ctx(PermissionMode.DEFAULT))
    print("  [第1次] 开具血常规（ASK规则命中 → 需确认）")
    d1 = await check(eng_d, OrderExam(), {"exam_name": "血常规", "patient_id": "P001"}, "order_exam 第1次")
    if d1.suggested_rules:
        for sr in d1.suggested_rules:
            eng_d.add_rule(PermissionRule(tool_name=sr.tool_name, rule_content=sr.rule_content,
                behavior=PermissionBehavior.ALLOW, source="doctor_approved"))
            print(f"  [医生批准] 添加规则: {sr.tool_name}→ALLOW")
    print("  [第2次] 再次开具检查（已有ALLOW规则 → 自动通过）")
    await check(eng_d, OrderExam(), {"exam_name": "血常规", "patient_id": "P002"}, "order_exam 第2次")

    _sep("演示结束")
    print("PermissionEngine可独立使用，无需启动LLM，适合网关/前置校验层。\n")


if __name__ == "__main__":
    asyncio.run(main())
