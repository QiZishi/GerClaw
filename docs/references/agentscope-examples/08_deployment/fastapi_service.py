"""
GerClaw 老年医疗 AI 平台 — FastAPI AgentService 集成示例

演示内容：
1. 使用 agentscope.app.create_app 构建 FastAPI 应用
2. 创建医疗问答 Agent（健康咨询、用药提醒、就医建议）
3. 注册 /api/chat 非流式端点和 /api/chat/stream SSE 流式端点
4. 通过 CORS 中间件支持 Web/App/小程序多端访问
5. 不依赖真实启动服务器，使用 mock client 演示请求/响应流程

依赖（可选，未安装时使用 mock 模式）：
    pip install fastapi uvicorn httpx agentscope

运行：
    DASHSCOPE_API_KEY=sk-xxx python fastapi_service.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# 1. 模型与凭证初始化：DashScopeChatModel 从环境变量读取 API Key
# ---------------------------------------------------------------------------

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
if not DASHSCOPE_API_KEY:
    print("[WARN] 未设置 DASHSCOPE_API_KEY 环境变量，将以 mock 模式运行示例")


def _build_chat_model():
    """构建 DashScope 聊天模型；若缺少依赖则返回 mock 模型。"""
    if not DASHSCOPE_API_KEY:
        return None
    try:
        from agentscope.credential import DashScopeCredential
        from agentscope.model import DashScopeChatModel

        return DashScopeChatModel(
            credential=DashScopeCredential(api_key=DASHSCOPE_API_KEY),
            model="qwen-plus",
            stream=True,
            temperature=0.5,  # 医疗场景温度偏低，保证回答稳定性
        )
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# 2. FastAPI 应用构造：包装 AgentScope create_app + 自定义端点
# ---------------------------------------------------------------------------

def build_app():
    """
    构建 GerClaw 医疗问答 FastAPI 应用。

    包含两种模式：
    - 完整模式：安装了 fastapi/agentscope 且有 API Key 时，调用 create_app 构造真实服务
    - Mock 模式：缺少依赖时返回一个简化版 FastAPI app（或 mock 对象），保证示例可运行
    """
    try:
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import StreamingResponse
        from fastapi.middleware import Middleware
    except ImportError:
        print("[INFO] fastapi 未安装，使用 mock app 演示构造逻辑")
        return _build_mock_app()

    # ---- 2.1 尝试构建 AgentScope 原生服务 ----
    agentscope_app = None
    try:
        from agentscope.app import create_app
        from agentscope.app.message_bus import InMemoryMessageBus
        from agentscope.app.workspace_manager import LocalWorkspaceManager
        import tempfile

        # 内存模式（原型/演示）；生产替换为 RedisStorage + RedisMessageBus
        # storage = RedisStorage(host="localhost", port=6379)
        # message_bus = RedisMessageBus(host="localhost", port=6379)
        message_bus = InMemoryMessageBus()
        workspace_manager = LocalWorkspaceManager(
            basedir=tempfile.mkdtemp(prefix="gerclaw_ws_"),
        )

        # RedisStorage 需要本地 Redis，demo 环境可能没有，用 try 包裹
        try:
            from agentscope.app.storage import RedisStorage
            storage = RedisStorage(host="localhost", port=6379)
        except Exception:
            storage = None  # 没有 Redis 时跳过原生 create_app

        if storage is not None:
            agentscope_app = create_app(
                storage=storage,
                message_bus=message_bus,
                workspace_manager=workspace_manager,
                title="GerClaw Medical Agent",
                version="1.0.0",
                extra_middlewares=[
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],  # 生产请收敛到具体域名
                        allow_methods=["*"],
                        allow_headers=["*"],
                    ),
                ],
            )
    except ImportError:
        agentscope_app = None

    # ---- 2.2 创建 GerClaw 外层应用 ----
    app = FastAPI(title="GerClaw Medical API", version="1.0.0")

    # CORS 配置 —— 支持 Web/App/小程序多端访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://app.gerclaw.com",
            "https://app.gerclaw.cn",
            "capacitor://localhost",       # App 内嵌 WebView
            "https://servicewechat.com",   # 微信小程序
            "http://localhost:3000",       # 本地开发
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ---- 2.3 挂载 AgentScope 原生服务（如果可用） ----
    if agentscope_app is not None:
        # 将 AgentScope 完整服务挂在 /agentscope 路径下
        # 原生端点：/agentscope/chat, /agentscope/sessions, /agentscope/agent 等
        app.mount("/agentscope", agentscope_app)

    # ---- 2.4 GerClaw 自定义端点：/api/health ----
    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """健康检查端点，供 K8s liveness/readiness probe 使用。"""
        return {"status": "ok", "service": "gerclaw-medical-agent"}

    # ---- 2.5 GerClaw 自定义端点：/api/chat（非流式，fire-and-forget 语义） ----
    @app.post("/api/chat")
    async def chat_non_stream(request: Request) -> dict[str, Any]:
        """
        非流式医疗问答接口。

        请求体：
            {
                "session_id": "sess_xxx",
                "tenant_id": "family:f001",   # 家庭/社区/医院
                "message": "我奶奶血压150/95需要立即去医院吗？"
            }

        返回：
            { "session_id": "...", "status": "processing", "reply": "..." }

        适用于智能音箱、后台批量问诊等不关心逐字输出的场景。
        """
        body = await request.json()
        session_id = body.get("session_id", "sess_default")
        tenant_id = body.get("tenant_id", "family:default")
        message = body.get("message", "")

        # 实际生产中，这里将消息转发给 AgentScope /chat 端点，
        # 然后通过 /sessions/{id}/messages 轮询获取完整回复。
        # Demo 模式下返回模拟医疗建议。
        reply = _mock_medical_reply(message, stream=False)

        return {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "status": "completed",
            "reply": reply,
        }

    # ---- 2.6 GerClaw 自定义端点：/api/chat/stream（SSE 流式） ----
    @app.get("/api/chat/stream")
    async def chat_stream(request: Request) -> StreamingResponse:
        """
        SSE 流式医疗问答接口（推荐用于 Web/App 端）。

        Query 参数：
            - session_id: 会话 ID
            - tenant_id: 租户 ID
            - message: 用户问题（URL 编码）

        SSE 帧格式：
            event: delta
            data: {"content": "您", "done": false}

            event: done
            data: {"content": "", "done": true}
        """
        session_id = request.query_params.get("session_id", "sess_default")
        tenant_id = request.query_params.get("tenant_id", "family:default")
        message = request.query_params.get("message", "")

        async def event_generator():
            # 逐字输出模拟回复（真实场景从 Agent reply_stream 迭代）
            reply = _mock_medical_reply(message, stream=True)
            for char in reply:
                # 客户端断开时 CancelledError 会自动抛出
                if await request.is_disconnected():
                    break
                yield f"event: delta\ndata: {json.dumps({'content': char, 'done': False, 'session_id': session_id, 'tenant_id': tenant_id}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)  # 模拟 LLM 逐 token 延迟
            yield f"event: done\ndata: {json.dumps({'content': '', 'done': True, 'session_id': session_id}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )

    return app


def _build_mock_app():
    """当 fastapi 未安装时返回一个 mock 对象，仅用于演示 API 结构。"""

    class MockApp:
        """极简 mock app，展示端点定义结构。"""

        routes = [
            ("GET", "/api/health", "健康检查"),
            ("POST", "/api/chat", "非流式医疗问答"),
            ("GET", "/api/chat/stream", "SSE 流式医疗问答"),
            ("ANY", "/agentscope/*", "AgentScope 原生服务（挂载）"),
        ]

        def add_middleware(self, *args, **kwargs):
            pass

    return MockApp()


# ---------------------------------------------------------------------------
# 3. Mock 医疗回复生成（真实环境替换为 Agent reply_stream）
# ---------------------------------------------------------------------------

def _mock_medical_reply(message: str, stream: bool = False) -> str:
    """根据用户问题生成模拟医疗建议。"""
    msg = message.strip()
    if "血压" in msg or "高压" in msg:
        return (
            "您好，关于血压150/95的情况，属于一级高血压范围。建议："
            "1. 保持冷静，让老人静坐休息10-15分钟后再次测量；"
            "2. 若多次测量收缩压持续超过140mmHg，建议近期就医调整用药；"
            "3. 如果伴随剧烈头痛、胸闷、视物模糊等症状，请立即拨打120；"
            "4. 日常注意低盐饮食、规律作息、按时服药。"
            "以上建议仅供参考，不能替代专业医生诊断。"
        )
    if "药" in msg and ("忘" in msg or "漏" in msg):
        return (
            "关于漏服药物的建议："
            "1. 如果距离下次服药时间超过一半间隔，可以补服；"
            "2. 如果接近下次服药时间，跳过本次，不要双倍剂量；"
            "3. 降压药、降糖药漏服需特别注意监测血压/血糖；"
            "4. 如有不适请及时联系社区医生或拨打120。"
        )
    return (
        "您好！我是GerClaw老年健康助手，可以为您提供健康咨询、用药提醒和就医建议。"
        "请问您具体想了解什么健康问题？例如血压管理、用药指导、慢病随访等。"
        "提醒：我的建议仅供参考，紧急情况请立即拨打120。"
    )


# ---------------------------------------------------------------------------
# 4. Mock Client 演示：不启动服务器，直接调用端点验证逻辑
# ---------------------------------------------------------------------------

async def _demo_with_mock_client() -> None:
    """使用 mock client 演示请求/响应流程（不依赖 httpx/TestClient）。"""
    print("=" * 60)
    print("GerClaw 医疗 AgentService 演示（Mock 模式）")
    print("=" * 60)

    app = build_app()

    # ---- 演示 1：健康检查 ----
    print("\n[1] GET /api/health")
    if hasattr(app, "routes"):
        print(f"    已注册路由: {app.routes}")
    print("    响应: {\"status\": \"ok\", \"service\": \"gerclaw-medical-agent\"}")

    # ---- 演示 2：非流式问答 ----
    print("\n[2] POST /api/chat  非流式问答")
    question = "我奶奶血压150/95需要立即去医院吗？"
    print(f"    请求: message={question!r}, tenant_id=family:f001")
    reply = _mock_medical_reply(question, stream=False)
    print(f"    响应(片段): {reply[:80]}...")

    # ---- 演示 3：SSE 流式问答（逐帧输出） ----
    print("\n[3] GET /api/chat/stream  SSE 流式问答")
    print(f"    请求: message={question!r}")
    print("    SSE 帧输出（模拟逐 token）:")
    reply = _mock_medical_reply(question, stream=True)
    chunk_size = 8
    for i in range(0, len(reply), chunk_size):
        chunk = reply[i : i + chunk_size]
        print(f"      [delta] {chunk!r}")
        await asyncio.sleep(0.01)
    print("      [done] 流结束")

    # ---- 演示 4：httpx TestClient 真实调用（如果可用） ----
    print("\n[4] 尝试使用 TestClient 进行真实 HTTP 调用...")
    try:
        from fastapi.testclient import TestClient

        # 仅当 build_app 返回真实 FastAPI 实例时才可以
        from fastapi import FastAPI
        if isinstance(app, FastAPI):
            client = TestClient(app)
            resp = client.get("/api/health")
            print(f"    /api/health status={resp.status_code} body={resp.json()}")

            resp = client.post("/api/chat", json={
                "session_id": "sess_demo_001",
                "tenant_id": "family:f001",
                "message": "忘记吃降压药怎么办？",
            })
            print(f"    /api/chat status={resp.status_code}")
            data = resp.json()
            print(f"    reply(片段): {data['reply'][:60]}...")

            # SSE 流
            with client.stream(
                "GET",
                "/api/chat/stream",
                params={"message": "血压150/95怎么办", "session_id": "s002"},
            ) as response:
                print(f"    /api/chat/stream status={response.status_code}")
                frames = 0
                for line in response.iter_lines():
                    if line and line.startswith("data: "):
                        frames += 1
                        if frames <= 3:
                            print(f"      frame: {line[:100]}")
                print(f"    共收到 {frames} 个 SSE 数据帧")
        else:
            print("    [跳过] 当前为 mock app，未安装 fastapi/agentscope 完整依赖")
    except ImportError:
        print("    [跳过] fastapi TestClient 不可用（pip install fastapi httpx）")

    print("\n" + "=" * 60)
    print("演示完成。生产环境启动命令：")
    print("  uvicorn fastapi_service:app --host 0.0.0.0 --port 8000 --workers 4")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 5. 入口
# ---------------------------------------------------------------------------

async def main() -> None:
    """主入口：构建应用并运行演示。"""
    await _demo_with_mock_client()


if __name__ == "__main__":
    asyncio.run(main())
