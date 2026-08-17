"""Dynamic configuration for memory compression and retrieval parameters."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional



class ExperimentStatus(str, Enum):
    """A/B实验状态"""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CompressionStrategy(str, Enum):
    """压缩策略类型"""
    MEDICAL_WEIGHTED = "medical_weighted"  # 基于医学权重的压缩
    TIME_DECAY = "time_decay"  # 基于时间衰减的压缩
    HYBRID = "hybrid"  # 混合策略


class RetrievalStrategy(str, Enum):
    """检索策略类型"""
    VECTOR_SEARCH = "vector_search"  # 向量检索
    RULE_BASED = "rule_based"  # 基于规则的检索
    HYBRID = "hybrid"  # 混合检索


@dataclass
class MedicalFieldWeight:
    """医学字段权重配置"""
    field_name: str
    weight: float
    description: str
    is_critical: bool = False  # 是否为关键字段（必须保留）


@dataclass
class CompressionConfig:
    """压缩配置"""
    # 基础参数
    max_tokens: int = 4000
    trigger_ratio: float = 0.85
    reserve_ratio: float = 0.2

    # 医学字段权重
    medical_field_weights: Dict[str, MedicalFieldWeight] = field(default_factory=dict)

    # 压缩策略
    strategy: CompressionStrategy = CompressionStrategy.MEDICAL_WEIGHTED

    # 时间衰减参数
    time_decay_factor: float = 0.95
    time_decay_days: int = 30

    # 保留阈值
    min_retention_score: float = 0.3

    # 关键字段保留阈值
    critical_field_retention: float = 0.9


@dataclass
class RetrievalConfig:
    """检索配置"""
    # 基础参数
    top_k: int = 10
    similarity_threshold: float = 0.7

    # 时间衰减
    time_decay_factor: float = 0.95
    time_decay_days: int = 30

    # 降级策略
    fallback_strategy: str = "hybrid"

    # 检索策略
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID

    # 规则检索参数
    rule_based_weight: float = 0.5
    vector_search_weight: float = 0.5


@dataclass
class ABExperimentConfig:
    """A/B实验配置"""
    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    status: ExperimentStatus = ExperimentStatus.DRAFT

    # 实验组配置
    control_group: Dict[str, Any] = field(default_factory=dict)
    treatment_group: Dict[str, Any] = field(default_factory=dict)

    # 流量分配
    traffic_split: float = 0.5  # 50% 对照组，50% 实验组

    # 实验时间
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # 评估指标
    metrics: List[str] = field(default_factory=lambda: [
        "compression_ratio",
        "medical_info_retention",
        "retrieval_accuracy",
        "user_satisfaction",
    ])

    # 样本量
    min_sample_size: int = 100
    current_sample_size: int = 0


@dataclass
class CompressionFeedback:
    """压缩反馈数据"""
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # 压缩参数
    compression_config: CompressionConfig = field(default_factory=CompressionConfig)

    # 压缩结果
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 0.0

    # 医学信息保留情况
    medical_fields_retained: List[str] = field(default_factory=list)
    medical_fields_lost: List[str] = field(default_factory=list)
    medical_info_retention_score: float = 0.0

    # 用户反馈
    user_feedback: Optional[str] = None
    user_satisfaction_score: Optional[float] = None

    # 实验组信息
    experiment_id: Optional[str] = None
    group: Optional[str] = None  # "control" or "treatment"


@dataclass
class RetrievalFeedback:
    """检索反馈数据"""
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # 检索参数
    retrieval_config: RetrievalConfig = field(default_factory=RetrievalConfig)

    # 检索结果
    query: str = ""
    results_count: int = 0
    relevant_results_count: int = 0
    retrieval_accuracy: float = 0.0

    # 降级情况
    fallback_used: bool = False
    fallback_strategy: Optional[str] = None

    # 用户反馈
    user_feedback: Optional[str] = None
    user_satisfaction_score: Optional[float] = None

    # 实验组信息
    experiment_id: Optional[str] = None
    group: Optional[str] = None


class MemoryConfigManager:
    """内存配置管理器"""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path
        self._compression_config = CompressionConfig()
        self._retrieval_config = RetrievalConfig()
        self._experiments: Dict[str, ABExperimentConfig] = {}
        self._compression_feedbacks: List[CompressionFeedback] = []
        self._retrieval_feedbacks: List[RetrievalFeedback] = []

        # 初始化默认医学字段权重
        self._init_default_medical_weights()

    def _init_default_medical_weights(self):
        """初始化默认医学字段权重"""
        default_weights = {
            "allergy": MedicalFieldWeight("allergy", 10.0, "过敏史", True),
            "medication": MedicalFieldWeight("medication", 9.0, "药物信息", True),
            "vital_sign": MedicalFieldWeight("vital_sign", 8.0, "生命体征", True),
            "red_flag": MedicalFieldWeight("red_flag", 10.0, "红旗事件", True),
            "diagnosis": MedicalFieldWeight("diagnosis", 7.0, "诊断信息", False),
            "procedure": MedicalFieldWeight("procedure", 6.0, "手术/操作", False),
            "hospitalization": MedicalFieldWeight("hospitalization", 6.0, "住院信息", False),
            "chronic_disease": MedicalFieldWeight("chronic_disease", 5.0, "慢性病", False),
            "symptom": MedicalFieldWeight("symptom", 4.0, "症状", False),
            "test_result": MedicalFieldWeight("test_result", 5.0, "检查结果", False),
            "lab_result": MedicalFieldWeight("lab_result", 5.0, "化验结果", False),
            "lifestyle": MedicalFieldWeight("lifestyle", 3.0, "生活方式", False),
            "preference": MedicalFieldWeight("preference", 2.0, "偏好", False),
            "general_chat": MedicalFieldWeight("general_chat", 1.0, "一般聊天", False),
        }
        self._compression_config.medical_field_weights = default_weights

    def get_compression_config(self) -> CompressionConfig:
        """获取压缩配置"""
        return self._compression_config

    def get_retrieval_config(self) -> RetrievalConfig:
        """获取检索配置"""
        return self._retrieval_config

    def update_compression_config(self, **kwargs):
        """更新压缩配置"""
        for key, value in kwargs.items():
            if hasattr(self._compression_config, key):
                setattr(self._compression_config, key, value)

    def update_retrieval_config(self, **kwargs):
        """更新检索配置"""
        for key, value in kwargs.items():
            if hasattr(self._retrieval_config, key):
                setattr(self._retrieval_config, key, value)

    def update_medical_field_weight(self, field_name: str, weight: float, is_critical: bool = False):
        """更新医学字段权重"""
        if field_name in self._compression_config.medical_field_weights:
            self._compression_config.medical_field_weights[field_name].weight = weight
            self._compression_config.medical_field_weights[field_name].is_critical = is_critical

    def create_experiment(self, name: str, description: str,
                         control_config: Dict[str, Any],
                         treatment_config: Dict[str, Any],
                         traffic_split: float = 0.5) -> ABExperimentConfig:
        """创建A/B实验"""
        experiment = ABExperimentConfig(
            name=name,
            description=description,
            control_group=control_config,
            treatment_group=treatment_config,
            traffic_split=traffic_split,
            start_time=datetime.now(UTC),
        )
        self._experiments[experiment.experiment_id] = experiment
        return experiment

    def get_experiment_config(self, experiment_id: str, user_id: str) -> Dict[str, Any]:
        """根据用户ID获取实验配置"""
        if experiment_id not in self._experiments:
            return {}

        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            return experiment.control_group

        # 基于用户ID的哈希决定分组
        user_hash = hash(user_id) % 100
        if user_hash < experiment.traffic_split * 100:
            return experiment.treatment_group
        else:
            return experiment.control_group

    def record_compression_feedback(self, feedback: CompressionFeedback):
        """记录压缩反馈"""
        self._compression_feedbacks.append(feedback)

        # 如果有实验，更新实验统计
        if feedback.experiment_id and feedback.experiment_id in self._experiments:
            experiment = self._experiments[feedback.experiment_id]
            experiment.current_sample_size += 1

    def record_retrieval_feedback(self, feedback: RetrievalFeedback):
        """记录检索反馈"""
        self._retrieval_feedbacks.append(feedback)

        if feedback.experiment_id and feedback.experiment_id in self._experiments:
            experiment = self._experiments[feedback.experiment_id]
            experiment.current_sample_size += 1

    def get_experiment_metrics(self, experiment_id: str) -> Dict[str, Any]:
        """获取实验指标"""
        if experiment_id not in self._experiments:
            return {}

        experiment = self._experiments[experiment_id]

        # 收集对照组和实验组的反馈
        control_feedbacks = [
            f for f in self._compression_feedbacks
            if f.experiment_id == experiment_id and f.group == "control"
        ]
        treatment_feedbacks = [
            f for f in self._compression_feedbacks
            if f.experiment_id == experiment_id and f.group == "treatment"
        ]

        # 计算指标
        metrics = {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "status": experiment.status.value,
            "sample_size": experiment.current_sample_size,
            "control_group": {
                "sample_size": len(control_feedbacks),
                "avg_compression_ratio": self._avg_compression_ratio(control_feedbacks),
                "avg_medical_retention": self._avg_medical_retention(control_feedbacks),
                "avg_user_satisfaction": self._avg_user_satisfaction(control_feedbacks),
            },
            "treatment_group": {
                "sample_size": len(treatment_feedbacks),
                "avg_compression_ratio": self._avg_compression_ratio(treatment_feedbacks),
                "avg_medical_retention": self._avg_medical_retention(treatment_feedbacks),
                "avg_user_satisfaction": self._avg_user_satisfaction(treatment_feedbacks),
            },
        }

        return metrics

    def _avg_compression_ratio(self, feedbacks: List[CompressionFeedback]) -> float:
        """计算平均压缩率"""
        if not feedbacks:
            return 0.0
        ratios = [f.compression_ratio for f in feedbacks if f.compression_ratio > 0]
        return sum(ratios) / len(ratios) if ratios else 0.0

    def _avg_medical_retention(self, feedbacks: List[CompressionFeedback]) -> float:
        """计算平均医学信息保留率"""
        if not feedbacks:
            return 0.0
        scores = [f.medical_info_retention_score for f in feedbacks if f.medical_info_retention_score > 0]
        return sum(scores) / len(scores) if scores else 0.0

    def _avg_user_satisfaction(self, feedbacks: List[CompressionFeedback]) -> float:
        """计算平均用户满意度"""
        if not feedbacks:
            return 0.0
        scores = [f.user_satisfaction_score for f in feedbacks if f.user_satisfaction_score is not None]
        return sum(scores) / len(scores) if scores else 0.0

    def save_config(self, path: Optional[Path] = None):
        """保存配置到文件"""
        save_path = path or self._config_path
        if not save_path:
            return

        config_data = {
            "compression": {
                "max_tokens": self._compression_config.max_tokens,
                "trigger_ratio": self._compression_config.trigger_ratio,
                "reserve_ratio": self._compression_config.reserve_ratio,
                "strategy": self._compression_config.strategy.value,
                "time_decay_factor": self._compression_config.time_decay_factor,
                "time_decay_days": self._compression_config.time_decay_days,
                "min_retention_score": self._compression_config.min_retention_score,
                "critical_field_retention": self._compression_config.critical_field_retention,
                "medical_field_weights": {
                    name: {
                        "weight": fw.weight,
                        "description": fw.description,
                        "is_critical": fw.is_critical,
                    }
                    for name, fw in self._compression_config.medical_field_weights.items()
                },
            },
            "retrieval": {
                "top_k": self._retrieval_config.top_k,
                "similarity_threshold": self._retrieval_config.similarity_threshold,
                "time_decay_factor": self._retrieval_config.time_decay_factor,
                "time_decay_days": self._retrieval_config.time_decay_days,
                "fallback_strategy": self._retrieval_config.fallback_strategy,
                "strategy": self._retrieval_config.strategy.value,
                "rule_based_weight": self._retrieval_config.rule_based_weight,
                "vector_search_weight": self._retrieval_config.vector_search_weight,
            },
            "experiments": {
                exp_id: {
                    "name": exp.name,
                    "description": exp.description,
                    "status": exp.status.value,
                    "traffic_split": exp.traffic_split,
                    "current_sample_size": exp.current_sample_size,
                }
                for exp_id, exp in self._experiments.items()
            },
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

    def load_config(self, path: Optional[Path] = None):
        """从文件加载配置"""
        load_path = path or self._config_path
        if not load_path or not load_path.exists():
            return

        with open(load_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 更新压缩配置
        if "compression" in config_data:
            comp = config_data["compression"]
            self._compression_config.max_tokens = comp.get("max_tokens", 4000)
            self._compression_config.trigger_ratio = comp.get("trigger_ratio", 0.85)
            self._compression_config.reserve_ratio = comp.get("reserve_ratio", 0.2)
            self._compression_config.strategy = CompressionStrategy(comp.get("strategy", "medical_weighted"))
            self._compression_config.time_decay_factor = comp.get("time_decay_factor", 0.95)
            self._compression_config.time_decay_days = comp.get("time_decay_days", 30)
            self._compression_config.min_retention_score = comp.get("min_retention_score", 0.3)
            self._compression_config.critical_field_retention = comp.get("critical_field_retention", 0.9)

            # 更新医学字段权重
            if "medical_field_weights" in comp:
                for name, fw_data in comp["medical_field_weights"].items():
                    if name in self._compression_config.medical_field_weights:
                        self._compression_config.medical_field_weights[name].weight = fw_data.get("weight", 1.0)
                        self._compression_config.medical_field_weights[name].is_critical = fw_data.get("is_critical", False)

        # 更新检索配置
        if "retrieval" in config_data:
            ret = config_data["retrieval"]
            self._retrieval_config.top_k = ret.get("top_k", 10)
            self._retrieval_config.similarity_threshold = ret.get("similarity_threshold", 0.7)
            self._retrieval_config.time_decay_factor = ret.get("time_decay_factor", 0.95)
            self._retrieval_config.time_decay_days = ret.get("time_decay_days", 30)
            self._retrieval_config.fallback_strategy = ret.get("fallback_strategy", "hybrid")
            self._retrieval_config.strategy = RetrievalStrategy(ret.get("strategy", "hybrid"))
            self._retrieval_config.rule_based_weight = ret.get("rule_based_weight", 0.5)
            self._retrieval_config.vector_search_weight = ret.get("vector_search_weight", 0.5)
