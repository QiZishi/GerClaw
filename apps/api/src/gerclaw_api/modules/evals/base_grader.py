"""Multi-grader evaluation framework for GerClaw medical AI system."""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field


class GraderType(str, Enum):
    """评分器类型"""
    RULE = "rule"  # 规则评分器
    EVIDENCE = "evidence"  # 证据评分器
    MEDICAL = "medical"  # 医学评分器
    PERFORMANCE = "performance"  # 性能评分器
    DIALOGUE = "dialogue"  # 对话评分器


class GraderStatus(str, Enum):
    """评分器状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class EvalCaseStatus(str, Enum):
    """评测用例状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class ReportFormat(str, Enum):
    """报告格式"""
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    CSV = "csv"


@dataclass
class GraderConfig:
    """评分器配置"""
    grader_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    grader_type: GraderType = GraderType.RULE
    version: str = "1.0.0"
    enabled: bool = True
    
    # 评分权重
    weight: float = 1.0
    
    # 超时设置
    timeout_seconds: int = 30
    
    # 重试次数
    max_retries: int = 3
    
    # 配置参数
    config_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraderResult:
    """评分器结果"""
    grader_id: str = ""
    grader_name: str = ""
    grader_type: GraderType = GraderType.RULE
    
    # 评分结果
    passed: bool = False
    score: float = 0.0
    max_score: float = 1.0
    
    # 详细信息
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # 时间信息
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalCaseInput:
    """评测用例输入"""
    case_id: str = ""
    query: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    expected_output: Optional[Dict[str, Any]] = None
    
    # 多轮对话支持
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalCaseOutput:
    """评测用例输出"""
    case_id: str = ""
    response: str = ""
    structured_output: Optional[Dict[str, Any]] = None
    
    # 性能指标
    latency_ms: float = 0.0
    token_count: int = 0
    token_cost: float = 0.0
    
    # SSE信息
    sse_heartbeat_count: int = 0
    sse_timeout_count: int = 0
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalCaseResult:
    """评测用例结果"""
    case_id: str = ""
    case_name: str = ""
    status: EvalCaseStatus = EvalCaseStatus.PENDING
    
    # 输入输出
    input_data: EvalCaseInput = field(default_factory=EvalCaseInput)
    output_data: EvalCaseOutput = field(default_factory=EvalCaseOutput)
    
    # 评分结果
    grader_results: List[GraderResult] = field(default_factory=list)
    
    # 综合评分
    total_score: float = 0.0
    passed: bool = False
    
    # 时间信息
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    
    # 错误信息
    error_message: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    """评测报告"""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    # 评测配置
    eval_name: str = ""
    eval_description: str = ""
    eval_version: str = "1.0.0"
    
    # 评测结果
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    skipped_cases: int = 0
    
    # 通过率
    pass_rate: float = 0.0
    
    # 各评分器结果
    grader_summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # 详细结果
    case_results: List[EvalCaseResult] = field(default_factory=list)
    
    # 失败清单
    failure_list: List[Dict[str, Any]] = field(default_factory=list)
    
    # 趋势数据
    trend_data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseGrader(ABC):
    """评分器基类"""
    
    def __init__(self, config: GraderConfig):
        self.config = config
        self.status = GraderStatus.ACTIVE
    
    @abstractmethod
    async def grade(self, input_data: EvalCaseInput, output_data: EvalCaseOutput) -> GraderResult:
        """评分"""
        pass
    
    def _create_result(self, passed: bool, score: float, details: Dict[str, Any] = None) -> GraderResult:
        """创建评分结果"""
        return GraderResult(
            grader_id=self.config.grader_id,
            grader_name=self.config.name,
            grader_type=self.config.grader_type,
            passed=passed,
            score=score,
            max_score=self.config.weight,
            details=details or {},
            end_time=datetime.now(UTC),
            duration_ms=0.0,  # 实际计算中会更新
        )
