"""End-to-end error handling chain for memory module."""

from __future__ import annotations

import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


from gerclaw_api.modules.memory.models import (
    ExtractedMemoryFact,
    MemoryUpdateResult,
    ProvenanceRecord,
)


class ErrorSeverity(str, Enum):
    """错误严重程度"""
    LOW = "low"  # 低严重度，可降级处理
    MEDIUM = "medium"  # 中等严重度，需要记录
    HIGH = "high"  # 高严重度，需要告警
    CRITICAL = "critical"  # 严重错误，需要立即处理


class ErrorCategory(str, Enum):
    """错误类别"""
    EXTRACTION = "extraction"  # 提取错误
    COMPRESSION = "compression"  # 压缩错误
    RETRIEVAL = "retrieval"  # 检索错误
    STORAGE = "storage"  # 存储错误
    CONFIGURATION = "configuration"  # 配置错误
    VALIDATION = "validation"  # 验证错误
    NETWORK = "network"  # 网络错误
    TIMEOUT = "timeout"  # 超时错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class ErrorContext:
    """错误上下文"""
    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # 错误信息
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    error_type: str = ""
    error_message: str = ""
    traceback: Optional[str] = None

    # 上下文信息
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    operation: Optional[str] = None

    # 相关数据
    input_data: Optional[Dict[str, Any]] = None
    config_snapshot: Optional[Dict[str, Any]] = None

    # 降级信息
    fallback_used: bool = False
    fallback_strategy: Optional[str] = None
    fallback_result: Optional[Any] = None

    # 影响评估
    affected_fields: List[str] = field(default_factory=list)
    data_loss_risk: bool = False


@dataclass
class ErrorHandlingResult:
    """错误处理结果"""
    success: bool = True
    error_context: Optional[ErrorContext] = None
    fallback_result: Optional[Any] = None
    recovery_action: Optional[str] = None
    user_message: Optional[str] = None


class MemoryErrorHandler:
    """内存错误处理器"""

    def __init__(self, log_errors: bool = True):
        self._log_errors = log_errors
        self._error_history: List[ErrorContext] = []
        self._error_handlers: Dict[ErrorCategory, Callable] = {
            ErrorCategory.EXTRACTION: self._handle_extraction_error,
            ErrorCategory.COMPRESSION: self._handle_compression_error,
            ErrorCategory.RETRIEVAL: self._handle_retrieval_error,
            ErrorCategory.STORAGE: self._handle_storage_error,
            ErrorCategory.CONFIGURATION: self._handle_configuration_error,
            ErrorCategory.VALIDATION: self._handle_validation_error,
            ErrorCategory.NETWORK: self._handle_network_error,
            ErrorCategory.TIMEOUT: self._handle_timeout_error,
            ErrorCategory.UNKNOWN: self._handle_unknown_error,
        }

    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> ErrorHandlingResult:
        """处理错误"""
        # 创建错误上下文
        error_context = self._create_error_context(error, context)

        # 记录错误
        if self._log_errors:
            self._error_history.append(error_context)

        # 调用相应的错误处理器
        handler = self._error_handlers.get(error_context.category, self._handle_unknown_error)
        result = handler(error, error_context)

        return result

    def _create_error_context(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> ErrorContext:
        """创建错误上下文"""
        error_context = ErrorContext(
            error_type=type(error).__name__,
            error_message=str(error)[:500],
            traceback=traceback.format_exc(),
        )

        # 从上下文提取信息
        if context:
            error_context.user_id = context.get("user_id")
            error_context.session_id = context.get("session_id")
            error_context.operation = context.get("operation")
            error_context.input_data = context.get("input_data")
            error_context.config_snapshot = context.get("config_snapshot")

        # 根据错误类型确定类别和严重程度
        if isinstance(error, (ValueError, TypeError)):
            error_context.category = ErrorCategory.VALIDATION
            error_context.severity = ErrorSeverity.LOW
        elif isinstance(error, (ConnectionError, TimeoutError)):
            error_context.category = ErrorCategory.NETWORK
            error_context.severity = ErrorSeverity.MEDIUM
        elif isinstance(error, TimeoutError):
            error_context.category = ErrorCategory.TIMEOUT
            error_context.severity = ErrorSeverity.MEDIUM
        elif "extract" in str(error).lower():
            error_context.category = ErrorCategory.EXTRACTION
            error_context.severity = ErrorSeverity.MEDIUM
        elif "compress" in str(error).lower():
            error_context.category = ErrorCategory.COMPRESSION
            error_context.severity = ErrorSeverity.MEDIUM
        elif "retriev" in str(error).lower():
            error_context.category = ErrorCategory.RETRIEVAL
            error_context.severity = ErrorSeverity.MEDIUM
        elif "stor" in str(error).lower():
            error_context.category = ErrorCategory.STORAGE
            error_context.severity = ErrorSeverity.HIGH
        elif "config" in str(error).lower():
            error_context.category = ErrorCategory.CONFIGURATION
            error_context.severity = ErrorSeverity.HIGH
        else:
            error_context.category = ErrorCategory.UNKNOWN
            error_context.severity = ErrorSeverity.MEDIUM

        return error_context

    def _handle_extraction_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理提取错误"""
        context.fallback_used = True
        context.fallback_strategy = "deterministic_fallback"

        # 创建降级结果
        fallback_fact = ExtractedMemoryFact(
            category="basic_info",
            memory_type="stable",
            entity="用户输入",
            statement="用户输入了健康相关信息（提取失败）",
            evidence_span=str(context.input_data)[:50] if context.input_data else "",
            action="upsert",
            confidence=0.1,
            provenance=ProvenanceRecord(
                source_type="user_report",
                extraction_method="rule_based",
                confidence_score=0.1,
                verification_status="unverified",
                notes=f"提取失败降级：{context.error_message}",
            ),
            fallback_reason=f"提取失败：{context.error_message}",
        )

        return ErrorHandlingResult(
            success=True,
            error_context=context,
            fallback_result=[(fallback_fact, "pending")],
            recovery_action="使用确定性fallback",
            user_message="健康信息提取遇到问题，已记录待确认",
        )

    def _handle_compression_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理压缩错误"""
        context.fallback_used = True
        context.fallback_strategy = "deterministic_compression"

        return ErrorHandlingResult(
            success=True,
            error_context=context,
            fallback_result=None,  # 由调用者处理
            recovery_action="使用确定性压缩fallback",
            user_message="上下文压缩遇到问题，已使用安全降级策略",
        )

    def _handle_retrieval_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理检索错误"""
        context.fallback_used = True
        context.fallback_strategy = "rule_based_fallback"

        return ErrorHandlingResult(
            success=True,
            error_context=context,
            fallback_result=[],  # 空结果
            recovery_action="使用规则检索fallback",
            user_message="记忆检索遇到问题，已使用备用检索策略",
        )

    def _handle_storage_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理存储错误"""
        context.severity = ErrorSeverity.HIGH
        context.data_loss_risk = True

        return ErrorHandlingResult(
            success=False,
            error_context=context,
            fallback_result=None,
            recovery_action="需要人工干预",
            user_message="数据存储遇到问题，请稍后重试",
        )

    def _handle_configuration_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理配置错误"""
        context.severity = ErrorSeverity.HIGH

        return ErrorHandlingResult(
            success=False,
            error_context=context,
            fallback_result=None,
            recovery_action="使用默认配置",
            user_message="系统配置遇到问题，已使用默认设置",
        )

    def _handle_validation_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理验证错误"""
        context.severity = ErrorSeverity.LOW

        return ErrorHandlingResult(
            success=True,
            error_context=context,
            fallback_result=None,
            recovery_action="跳过无效数据",
            user_message="数据格式验证失败，已跳过",
        )

    def _handle_network_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理网络错误"""
        context.severity = ErrorSeverity.MEDIUM

        return ErrorHandlingResult(
            success=False,
            error_context=context,
            fallback_result=None,
            recovery_action="重试或使用本地缓存",
            user_message="网络连接遇到问题，请检查网络后重试",
        )

    def _handle_timeout_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理超时错误"""
        context.severity = ErrorSeverity.MEDIUM

        return ErrorHandlingResult(
            success=False,
            error_context=context,
            fallback_result=None,
            recovery_action="增加超时时间或使用异步处理",
            user_message="处理超时，请稍后重试",
        )

    def _handle_unknown_error(self, error: Exception, context: ErrorContext) -> ErrorHandlingResult:
        """处理未知错误"""
        context.severity = ErrorSeverity.MEDIUM

        return ErrorHandlingResult(
            success=False,
            error_context=context,
            fallback_result=None,
            recovery_action="记录日志并通知管理员",
            user_message="遇到未知错误，请联系技术支持",
        )

    def get_error_history(self, limit: int = 100) -> List[ErrorContext]:
        """获取错误历史"""
        return self._error_history[-limit:]

    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计"""
        if not self._error_history:
            return {}

        stats = {
            "total_errors": len(self._error_history),
            "by_category": {},
            "by_severity": {},
            "fallback_usage": 0,
        }

        for error in self._error_history:
            # 按类别统计
            category = error.category.value
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

            # 按严重程度统计
            severity = error.severity.value
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1

            # 降级使用统计
            if error.fallback_used:
                stats["fallback_usage"] += 1

        return stats

    def clear_error_history(self):
        """清除错误历史"""
        self._error_history.clear()


def safe_memory_operation(
    operation_name: str,
    operation_func: Callable,
    error_handler: MemoryErrorHandler,
    *args,
    **kwargs
) -> Tuple[Any, Optional[ErrorContext]]:
    """安全执行内存操作，统一处理错误"""
    try:
        result = operation_func(*args, **kwargs)
        return result, None
    except Exception as error:
        context = {
            "operation": operation_name,
            "input_data": {"args": str(args)[:200], "kwargs": str(kwargs)[:200]},
        }
        handling_result = error_handler.handle_error(error, context)

        if handling_result.success and handling_result.fallback_result is not None:
            return handling_result.fallback_result, handling_result.error_context
        else:
            raise error


def update_result_with_error(
    result: MemoryUpdateResult,
    error_context: Optional[ErrorContext]
) -> MemoryUpdateResult:
    """将错误信息更新到MemoryUpdateResult中"""
    if error_context is None:
        return result

    # 更新fallback相关信息
    result.fallback_used = error_context.fallback_used
    result.fallback_strategy = error_context.fallback_strategy
    result.fallback_reason = error_context.error_message

    return result
