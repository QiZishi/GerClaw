"""Deterministic Quick, Standard, Deep, and Emergency routing."""

from __future__ import annotations

import re

from gerclaw_api.modules.agent_harness.routing.contracts import (
    RouteDecision,
    RouteKind,
    RoutingInput,
    RoutingPolicy,
)

_DEEP_REQUEST = re.compile(
    r"(?:生成|形成|撰写|整理).{0,12}(?:报告|文档)|"
    r"鉴别诊断|综合评估|五大处方|用药审查|"
    r"(?:比较|综合|交叉分析).{0,20}(?:资料|文件|检查|方案)"
)
_STANDARD_OPERATION = re.compile(
    r"\b(?:web_search|search_knowledge|search_memory)\b|"
    r"(?:调用|使用).{0,12}(?:搜索|检索|Skill|能力)|"
    r"(?:联网|在线).{0,8}(?:搜索|检索|查找)"
)
_SIMPLE_CALCULATION = re.compile(r"^[\d\s+\-*/().=?]+$")


class DeterministicRouter:
    """Route from validated request shape without model or external calls."""

    def __init__(self, policy: RoutingPolicy) -> None:
        self._policy = policy

    def decide(self, routing_input: RoutingInput) -> RouteDecision:
        if routing_input.high_risk_detected:
            return RouteDecision(
                route=RouteKind.EMERGENCY,
                reason_code="red_flag_short_circuit",
                model_allowed=False,
            )

        attachment_count = max(
            routing_input.image_count + routing_input.document_count,
            int(routing_input.has_images) + int(routing_input.has_documents),
        )
        capability_count = len(routing_input.selected_capabilities)
        required_capabilities = routing_input.selected_capabilities

        if capability_count >= self._policy.deep_capability_count:
            return RouteDecision(
                route=RouteKind.DEEP,
                reason_code="multiple_capabilities",
                required_capabilities=required_capabilities,
            )
        if attachment_count >= self._policy.deep_attachment_count:
            return RouteDecision(
                route=RouteKind.DEEP,
                reason_code="multiple_attachments",
                required_capabilities=required_capabilities,
            )
        if _DEEP_REQUEST.search(routing_input.message):
            return RouteDecision(
                route=RouteKind.DEEP,
                reason_code="complex_deliverable",
                required_capabilities=required_capabilities,
            )
        if len(routing_input.message) >= self._policy.deep_min_characters:
            return RouteDecision(
                route=RouteKind.DEEP,
                reason_code="large_request",
                required_capabilities=required_capabilities,
            )
        if _STANDARD_OPERATION.search(routing_input.message):
            return RouteDecision(
                route=RouteKind.STANDARD,
                reason_code="explicit_operation",
                required_capabilities=required_capabilities,
            )

        if (
            not routing_input.medical_content
            and attachment_count == 0
            and capability_count == 0
            and len(routing_input.message) <= self._policy.quick_max_characters
        ):
            reason_code = (
                "simple_calculation"
                if _SIMPLE_CALCULATION.fullmatch(routing_input.message)
                else "short_non_medical"
            )
            return RouteDecision(route=RouteKind.QUICK, reason_code=reason_code)

        return RouteDecision(
            route=RouteKind.STANDARD,
            reason_code=(
                "medical_request"
                if routing_input.medical_content
                else "bounded_general_request"
            ),
            required_capabilities=required_capabilities,
        )
