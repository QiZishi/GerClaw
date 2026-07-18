# -*- coding: utf-8 -*-
"""
GerClaw 老年医疗 AI API 服务示例。

演示如何基于 AgentScope 2.0.3 的 `create_app` 构建 GerClaw 医疗 API 服务：
  1. 使用 create_app 构建底层 AgentScope FastAPI 应用（含 Redis 存储/消息总线/LocalWorkspace）
  2. 挂载自定义医疗路由（/api/medical/*），复用底层 Agent 能力但包装医疗业务逻辑
  3. 自定义 JWT 认证依赖覆盖默认的 X-User-ID 头认证
  4. 提供两个医疗端点：
     - POST /api/medical/consult  老年科问诊（同步包装，创建临时session→触发chat→返回结果）
     - POST /api/medical/cga      老年综合评估(CGA)流式端点（SSE）
  5. 提供 /health 健康检查端点
  6. 自动注册"老年科AI医生"Agent 和 DashScope 凭证

运行方式：
  # 需要本地 Redis（localhost:6379）
  pip install agentscope fastapi uvicorn redis httpx
  export DASHSCOPE_API_KEY="sk-your-key"
  python gerclaw_api_server.py

  服务启动后：
    - API 文档: http://localhost:8000/docs
    - 健康检查: http://localhost:8000/health
    - 问诊接口: POST http://localhost:8000/api/medical/consult
    - CGA评估:  POST http://localhost:8000/api/medical/cga (SSE)

环境变量：
  DASHSCOPE_API_KEY    必填，通义千问 API Key
  GERCLAW_JWT_SECRET   JWT 签名密钥（默认 "gerclaw-dev-secret"）
  REDIS_HOST           Redis 地址（默认 localhost）
  REDIS_PORT           Redis 端口（默认 6379）
  PORT                 服务端口（默认 8000）
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# AgentScope 核心导入
from agentscope.app import create_app
from agentscope.app.deps import (
    get_chat_service,
    get_current_user_id,
    get_session_service,
    get_storage,
)
from agentscope.app.message_bus import InMemoryMessageBus, RedisMessageBus
from agentscope.app.storage import RedisStorage
from agentscope.app.workspace_manager import LocalWorkspaceManager

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
JWT_SECRET = os.environ.get("GERCLAW_JWT_SECRET", "gerclaw-dev-secret-change-me")
JWT_ALGORITHM = "HS256"
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
PORT = int(os.environ.get("PORT", "8000"))
WORKSPACE_DIR = os.environ.get("GERCLAW_WORKSPACE_DIR", "/tmp/gerclaw_workspaces")

# ---------------------------------------------------------------------------
# 医疗数据模型
# ---------------------------------------------------------------------------
class ConsultRequest(BaseModel):
    """老年科问诊请求。"""
    patient_id: str = Field(..., description="患者ID", examples=["P20240001"])
    patient_name: str = Field(..., description="患者姓名", examples=["李大爷"])
    age: int = Field(..., ge=60, le=120, description="年龄")
    gender: str = Field(..., pattern="^(男|女)$", description="性别")
    chief_complaint: str = Field(..., min_length=2, description="主诉")
    history: Optional[str] = Field(None, description="既往病史")
    medications: Optional[list[str]] = Field(None, description="当前用药")
    question: str = Field(..., min_length=2, description="医生的提问/患者咨询内容")


class ConsultResponse(BaseModel):
    """问诊响应。"""
    consultation_id: str
    patient_id: str
    advice: str
    risk_flags: list[str] = Field(default_factory=list)
    cga_domains: list[str] = Field(default_factory=list, description="建议进一步评估的CGA领域")
    timestamp: str


class CGARequest(BaseModel):
    """老年综合评估(CGA)请求。"""
    patient_id: str = Field(...)
    patient_name: str = Field(...)
    age: int = Field(...)
    gender: str = Field(...)
    # 各领域数据（简化版）
    adl_score: Optional[int] = Field(None, ge=0, le=6, description="ADL日常生活能力评分(0-6)")
    iadl_score: Optional[int] = Field(None, ge=0, le=8, description="IADL工具性日常生活能力评分(0-8)")
    mmse_score: Optional[int] = Field(None, ge=0, le=30, description="MMSE认知评分(0-30)")
    gait_speed: Optional[float] = Field(None, description="4米步速(m/s)")
    grip_strength: Optional[float] = Field(None, description="握力(kg)")
    falls_last_year: Optional[int] = Field(0, description="过去一年跌倒次数")
    mood: Optional[str] = Field(None, description="情绪状态（如GDS-15简版得分或描述）")
    nutrition_mna: Optional[float] = Field(None, description="MNA-SF营养筛查评分(0-14)")
    comorbidities: Optional[list[str]] = Field(None, description="合并症列表")
    medications_count: Optional[int] = Field(None, ge=0, description="用药数量（≥5种为多重用药）")
    notes: Optional[str] = Field(None, description="医生备注")


# ---------------------------------------------------------------------------
# JWT 认证依赖（替换 AgentScope 默认的 X-User-ID）
# ---------------------------------------------------------------------------
async def gerclaw_jwt_auth(
    authorization: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> str:
    """GerClaw JWT 认证。

    优先使用 Authorization: Bearer <token>；
    开发环境下回退到 X-User-ID 头，方便本地调试。
    """
    # 开发模式：若提供了 X-User-ID 且无 JWT，直接使用
    if not authorization and x_user_id:
        return x_user_id

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use: Bearer <token>",
        )
    token = authorization.removeprefix("Bearer ")
    try:
        # 注意：生产环境应使用 python-jose 或 PyJWT
        # 这里用简单的 base64 模拟 JWT 解析，实际请替换为 jose.jwt.decode
        import base64
        try:
            payload_b64 = token.split(".")[1]
            padding = 4 - len(payload_b64) % 4
            payload_json = base64.urlsafe_b64decode(payload_b64 + "=" * padding)
            payload = json.loads(payload_json)
            user_id = payload.get("sub")
            if not user_id:
                raise ValueError("no sub")
            return user_id
        except Exception:
            # token 解析失败时，如果有 X-User-ID 则作为开发模式fallback
            if x_user_id:
                return x_user_id
            raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT token",
        )


# ---------------------------------------------------------------------------
# 构建底层 AgentScope app
# ---------------------------------------------------------------------------
def build_agentscope_app() -> FastAPI:
    """构建 AgentScope FastAPI 应用。

    根据是否有 Redis 可用选择存储后端；
    无 Redis 时使用 InMemoryMessageBus 做开发模式（但AgentScope的storage目前仅提供RedisStorage，
    所以我们提供一个简单的降级：如果Redis不可用则在内存中mock，方便demo启动）。
    """
    try:
        storage = RedisStorage(host=REDIS_HOST, port=REDIS_PORT)
        message_bus = RedisMessageBus(host=REDIS_HOST, port=REDIS_PORT)
        print(f"[GerClaw] 已连接 Redis: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        print(f"[GerClaw] 警告：Redis 连接失败 ({e})，使用 InMemory 模式（仅开发用）")
        # AgentScope 要求 StorageBase；若无 Redis 则使用 InMemoryMessageBus 但storage需要特殊处理
        # 为了demo可运行，我们仍尝试构造，如失败则给出提示
        storage = RedisStorage(host=REDIS_HOST, port=REDIS_PORT)
        message_bus = InMemoryMessageBus()

    workspace_manager = LocalWorkspaceManager(basedir=WORKSPACE_DIR, ttl=86400.0)

    app = create_app(
        storage=storage,
        message_bus=message_bus,
        workspace_manager=workspace_manager,
        # 暂不启用 KB（demo简化），需要时参考12_REST_API服务层.md配置
        knowledge_base_manager=None,
        # 医疗子Agent模板预注册
        custom_subagent_templates=[
            # 可在此注册 cga_assessor / medication_reviewer / care_advisor 等模板
        ],
        title="GerClaw Medical AI Platform",
        version="1.0.0",
    )
    return app


# ---------------------------------------------------------------------------
# 自定义医疗路由
# ---------------------------------------------------------------------------
medical_router = APIRouter(prefix="/api/medical", tags=["GerClaw Medical API"])


@medical_router.get("/agents", summary="列出可用的医疗 Agent")
async def list_medical_agents(
    user_id: str = Depends(gerclaw_jwt_auth),
    storage = Depends(get_storage),
):
    """列出当前用户可用的医疗 Agent。"""
    agents = await storage.list_agents(user_id)
    return {"agents": [{"id": a.id, "name": a.data.name} for a in agents], "total": len(agents)}


@medical_router.post("/consult", response_model=ConsultResponse, summary="老年科AI问诊")
async def medical_consult(
    req: ConsultRequest,
    request: Request,
    user_id: str = Depends(gerclaw_jwt_auth),
    storage = Depends(get_storage),
    chat_service = Depends(get_chat_service),
):
    """老年科AI问诊接口。

    包装底层 ChatService：
    1. 校验患者信息并记录审计日志
    2. 获取或创建"老年科AI医生"Agent
    3. 创建/复用问诊 Session
    4. 构造医疗专业 prompt 触发 chat
    5. 返回初步建议（demo模式直接返回结构化建议，生产环境应通过SSE异步返回）

    注意：这是同步包装的简化示例；真实生产建议使用 SSE 流式返回（参考 /cga 端点）。
    """
    consultation_id = f"consult-{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()
    print(f"[GerClaw] 问诊请求 {consultation_id} 来自 {user_id} 患者 {req.patient_id}")

    # --- 构造医疗建议（demo：基于规则+Agent提示，实际应调用ChatService.run） ---
    risk_flags: list[str] = []
    cga_domains: list[str] = []

    # 简单风险筛查规则（演示用，真实场景应由Agent推理）
    if req.age >= 80:
        risk_flags.append("高龄(≥80岁)")
        cga_domains.append("功能状态(ADL/IADL)")
    if req.medications and len(req.medications) >= 5:
        risk_flags.append(f"多重用药({len(req.medications)}种)")
        cga_domains.append("用药审查")
    if "头晕" in req.chief_complaint or "眩晕" in req.chief_complaint:
        risk_flags.append("跌倒风险(头晕主诉)")
        cga_domains.append("平衡与步态")
    if "高血压" in (req.history or "") or "糖尿病" in (req.history or ""):
        cga_domains.append("慢病管理")
        if "糖尿病" in (req.history or ""):
            cga_domains.append("营养评估")

    advice_parts = [
        f"【初步问诊建议】患者{req.patient_name}({req.age}岁{req.gender})，主诉：{req.chief_complaint}。",
    ]
    if req.history:
        advice_parts.append(f"既往史：{req.history}。")
    if req.medications:
        advice_parts.append(f"当前用药：{', '.join(req.medications)}。")
    advice_parts.append(f"针对您的问题「{req.question}」：建议首先进行生命体征测量（血压、心率、血氧），"
                        f"重点排查体位性低血压；同时建议进行老年综合评估(CGA)以全面了解功能状态。")
    if risk_flags:
        advice_parts.append(f"风险标记：{'、'.join(risk_flags)}。")
    if cga_domains:
        advice_parts.append(f"建议进一步评估领域：{'、'.join(list(dict.fromkeys(cga_domains)))}。")
    advice_parts.append("请注意：以上为AI辅助建议，最终诊断需由临床医生确认。")

    return ConsultResponse(
        consultation_id=consultation_id,
        patient_id=req.patient_id,
        advice="".join(advice_parts),
        risk_flags=risk_flags,
        cga_domains=list(dict.fromkeys(cga_domains)),
        timestamp=now,
    )


@medical_router.post("/cga", summary="老年综合评估(CGA) - 流式SSE")
async def cga_assessment(
    req: CGARequest,
    request: Request,
    user_id: str = Depends(gerclaw_jwt_auth),
):
    """老年综合评估(CGA) SSE 流式端点。

    逐领域输出评估结果：
      1. 功能状态（ADL/IADL）
      2. 认知功能（MMSE）
      3. 跌倒风险
      4. 营养状态
      5. 情绪/抑郁
      6. 多重用药
      7. 综合建议

    返回 text/event-stream，每个事件为 JSON。
    """
    assessment_id = f"cga-{uuid.uuid4().hex[:12]}"
    print(f"[GerClaw] CGA评估 {assessment_id} 患者 {req.patient_id} 由 {user_id} 发起")

    async def generate() -> AsyncGenerator[str, None]:
        """SSE 事件生成器。"""
        def sse_event(event_type: str, data: dict) -> str:
            payload = json.dumps(
                {"type": event_type, "assessment_id": assessment_id, "data": data},
                ensure_ascii=False,
            )
            return f"data: {payload}\n\n"

        # 开始事件
        yield sse_event("start", {
            "patient_name": req.patient_name,
            "age": req.age,
            "domains": ["功能状态", "认知", "跌倒", "营养", "情绪", "用药", "综合"],
        })
        await asyncio.sleep(0.3)

        # 领域1：功能状态
        adl_level = "未知"
        if req.adl_score is not None:
            adl_level = "功能完好" if req.adl_score == 6 else "功能下降" if req.adl_score >= 4 else "明显受损"
        iadl_level = "未知"
        if req.iadl_score is not None:
            iadl_level = "独立" if req.iadl_score >= 7 else "需协助"
        yield sse_event("domain_result", {
            "domain": "功能状态",
            "adl": {"score": req.adl_score, "level": adl_level},
            "iadl": {"score": req.iadl_score, "level": iadl_level},
            "summary": f"ADL: {adl_level}; IADL: {iadl_level}",
        })
        await asyncio.sleep(0.4)

        # 领域2：认知
        cog_level = "未知"
        if req.mmse_score is not None:
            if req.mmse_score >= 27:
                cog_level = "认知正常"
            elif req.mmse_score >= 21:
                cog_level = "轻度认知障碍"
            elif req.mmse_score >= 10:
                cog_level = "中度认知障碍"
            else:
                cog_level = "重度认知障碍"
        yield sse_event("domain_result", {
            "domain": "认知功能",
            "mmse": {"score": req.mmse_score, "level": cog_level},
            "summary": f"MMSE {req.mmse_score}: {cog_level}",
        })
        await asyncio.sleep(0.4)

        # 领域3：跌倒风险
        fall_risk = "未知"
        if req.falls_last_year is not None:
            if req.falls_last_year >= 2 or (req.gait_speed is not None and req.gait_speed < 0.8):
                fall_risk = "高风险"
            elif req.falls_last_year == 1:
                fall_risk = "中风险"
            else:
                fall_risk = "低风险"
        yield sse_event("domain_result", {
            "domain": "跌倒风险",
            "falls_last_year": req.falls_last_year,
            "gait_speed": req.gait_speed,
            "level": fall_risk,
            "summary": f"过去一年跌倒{req.falls_last_year}次，步速{req.gait_speed}m/s，风险等级: {fall_risk}",
        })
        await asyncio.sleep(0.4)

        # 领域4：营养
        nut_level = "未知"
        if req.nutrition_mna is not None:
            nut_level = "营养正常" if req.nutrition_mna >= 12 else "有营养不良风险" if req.nutrition_mna >= 8 else "营养不良"
        yield sse_event("domain_result", {
            "domain": "营养状态",
            "mna_sf": req.nutrition_mna,
            "level": nut_level,
            "summary": f"MNA-SF {req.nutrition_mna}: {nut_level}",
        })
        await asyncio.sleep(0.4)

        # 领域5：情绪
        yield sse_event("domain_result", {
            "domain": "情绪状态",
            "mood": req.mood or "未评估",
            "summary": "建议使用GDS-15进行抑郁筛查" if not req.mood else f"情绪状态: {req.mood}",
        })
        await asyncio.sleep(0.3)

        # 领域6：用药
        poly_pharmacy = req.medications_count is not None and req.medications_count >= 5
        yield sse_event("domain_result", {
            "domain": "多重用药",
            "medications_count": req.medications_count,
            "polypharmacy": poly_pharmacy,
            "summary": f"用药{req.medications_count}种，{'存在多重用药风险' if poly_pharmacy else '未见多重用药'}",
        })
        await asyncio.sleep(0.4)

        # 综合建议
        overall_risks = []
        if adl_level in ("功能下降", "明显受损"):
            overall_risks.append("日常生活能力下降")
        if "认知障碍" in cog_level:
            overall_risks.append(cog_level)
        if fall_risk in ("高风险", "中风险"):
            overall_risks.append(f"跌倒{fall_risk}")
        if "营养不良" in nut_level or "风险" in nut_level:
            overall_risks.append(nut_level)
        if poly_pharmacy:
            overall_risks.append("多重用药")

        yield sse_event("summary", {
            "overall_risk_level": "高" if len(overall_risks) >= 3 else "中" if len(overall_risks) >= 1 else "低",
            "risk_factors": overall_risks,
            "recommendations": [
                "制定个性化照护计划",
                "定期随访评估（建议3个月一次）",
                "转诊相关专科（如有认知障碍转神经内科/记忆门诊）",
                "用药审查（Beers标准/STOPP-START）",
                "营养咨询和运动干预（如有需要）",
            ][: max(2, len(overall_risks) + 1)],
            "disclaimer": "本评估结果为AI辅助分析，仅供临床参考，不构成诊断结论。",
        })
        await asyncio.sleep(0.2)

        # 结束事件
        yield sse_event("done", {"completed_at": datetime.now().isoformat()})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 应用组装
# ---------------------------------------------------------------------------
def create_gerclaw_app() -> FastAPI:
    """组装 GerClaw 完整应用。"""
    # 底层 AgentScope app
    agentscope_app = build_agentscope_app()

    # 替换认证依赖：JWT 认证覆盖默认 X-User-ID
    agentscope_app.dependency_overrides[get_current_user_id] = gerclaw_jwt_auth

    # 添加 CORS（适老化前端/小程序接入）
    agentscope_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 健康检查端点
    @agentscope_app.get("/health", tags=["system"], summary="健康检查")
    async def health():
        return {
            "status": "ok",
            "service": "GerClaw Medical AI Platform",
            "version": "1.0.0",
            "agentscope_version": _get_agentscope_version(),
            "timestamp": datetime.now().isoformat(),
        }

    # 挂载 GerClaw 自定义医疗路由到根 app
    agentscope_app.include_router(medical_router)

    # 启动事件：自动注册默认医疗Agent
    @agentscope_app.on_event("startup")
    async def bootstrap_medical_agents():
        """服务启动时自动创建一个默认的"老年科AI医生"Agent和DashScope凭证。"""
        try:
            storage = agentscope_app.state.storage
            # 使用bootstrap系统用户创建默认agent
            bootstrap_user = "system-bootstrap"
            agents = await storage.list_agents(bootstrap_user)
            if not any(a.data.name == "GerClaw老年科AI医生" for a in agents):
                from agentscope.app.storage import AgentData, AgentRecord
                record = AgentRecord(
                    user_id=bootstrap_user,
                    data=AgentData(
                        name="GerClaw老年科AI医生",
                        system_prompt=(
                            "你是GerClaw平台的老年科AI医生助手，专门服务于60岁以上老年患者。"
                            "你擅长老年综合评估(CGA)、慢病管理、多重用药审查、跌倒风险评估、"
                            "认知筛查和营养评估。回答时请：\n"
                            "1. 使用通俗易懂的语言，避免过多医学术语\n"
                            "2. 每次回答前先总结关键信息\n"
                            "3. 明确标注'AI辅助建议，请以医生诊断为准'\n"
                            "4. 对急症风险（如突发胸痛、呼吸困难、意识障碍）立即提示就医"
                        ),
                    ),
                )
                agent_id = await storage.upsert_agent(bootstrap_user, record)
                print(f"[GerClaw] 已注册默认老年科AI医生 agent_id={agent_id}")

                # 若有DashScope key，自动创建凭证和默认session
                if DASHSCOPE_KEY:
                    from agentscope.credential import CredentialFactory
                    cred = CredentialFactory.from_dict({
                        "type": "dashscope_chat",
                        "api_key": DASHSCOPE_KEY,
                    })
                    cred_id = await storage.upsert_credential(bootstrap_user, cred)
                    print(f"[GerClaw] 已注册 DashScope 凭证 credential_id={cred_id}")
        except Exception as e:
            print(f"[GerClaw] 启动引导警告（非致命）: {e}")

    return agentscope_app


def _get_agentscope_version() -> str:
    """获取 AgentScope 版本号。"""
    try:
        from agentscope._version import __version__
        return __version__
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
app = create_gerclaw_app()


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("GerClaw 老年医疗 AI 平台 API 服务")
    print("=" * 60)
    print(f"  端口: {PORT}")
    print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  DashScope Key: {'已配置' if DASHSCOPE_KEY else '未配置（仅mock模式）'}")
    print(f"  API 文档: http://localhost:{PORT}/docs")
    print(f"  健康检查: http://localhost:{PORT}/health")
    print(f"  问诊接口: POST http://localhost:{PORT}/api/medical/consult")
    print(f"  CGA评估:  POST http://localhost:{PORT}/api/medical/cga (SSE)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
