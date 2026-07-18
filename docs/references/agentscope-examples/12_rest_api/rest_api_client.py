# -*- coding: utf-8 -*-
"""
GerClaw AgentScope REST API 客户端示例。

演示如何通过 HTTP 客户端（httpx）调用 AgentScope Agent Service 的核心端点：
  1. 健康检查（/health，自定义端点）
  2. 创建/列出 Agent（/agent）
  3. 创建/列出 Session（/sessions）
  4. 触发聊天（/chat，fire-and-forget）
  5. SSE 流式订阅（/sessions/{sid}/stream，Server-Sent Events 解析）

支持两种运行模式：
  - mock 模式（默认）：内置 FastAPI mock server，无需 Redis 和真实 AgentScope 服务即可演示 SSE 协议解析
  - real 模式：连接真实 AgentScope 服务（需先启动 gerclaw_api_server.py 并配置 Redis）

运行方式：
  # mock 模式（不需要 Redis，演示 SSE 解析流程）
  python rest_api_client.py

  # real 模式（连接真实服务，需要先启动 gerclaw_api_server.py）
  python rest_api_client.py --mode real --base-url http://localhost:8000

环境变量：
  DASHSCOPE_API_KEY   DashScope API Key（real 模式下用于凭证配置）
  GERCLAW_USER_ID     用户 ID（默认 "doctor_zhang3"）
  GERCLAW_JWT_TOKEN   JWT Token（real 模式下若服务启用 JWT 鉴权）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any, AsyncIterator

import httpx

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_USER_ID = os.environ.get("GERCLAW_USER_ID", "doctor_zhang3")
DEFAULT_JWT = os.environ.get("GERCLAW_JWT_TOKEN", "")
DASHSCOPE_KEY = os.environ.get("DASHSCOPE_API_KEY", "")


def build_headers(jwt: str = DEFAULT_JWT, user_id: str = DEFAULT_USER_ID) -> dict:
    """构造请求头。

    AgentScope 2.0.3 默认使用 X-User-ID header 标识用户；
    GerClaw 生产环境替换为 JWT Bearer Token（参见 gerclaw_api_server.py）。
    两种 header 同时发送以兼容两种认证配置。
    """
    headers = {
        "Content-Type": "application/json",
        "X-User-ID": user_id,
    }
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers


# ---------------------------------------------------------------------------
# SSE 解析器
# ---------------------------------------------------------------------------
async def parse_sse_stream(
    response: httpx.Response,
    timeout: float = 30.0,
) -> AsyncIterator[dict[str, Any]]:
    """解析 Server-Sent Events 流。

    AgentScope SSE 格式：
      data: {JSON}\\n\\n          # 事件帧
      :\\n\\n                     # 心跳注释帧（每 30s）

    Yields:
        解析后的事件 dict，含 type、timestamp 等字段
    """
    started = time.monotonic()
    buffer = ""
    async for chunk in response.aiter_text():
        if time.monotonic() - started > timeout:
            print("[SSE] 达到超时时间，停止解析")
            break
        buffer += chunk
        # SSE 帧以 \\n\\n 分隔
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            frame = frame.strip()
            if not frame:
                continue
            # 心跳帧：以冒号开头的注释
            if frame.startswith(":"):
                yield {"type": "heartbeat", "data": None}
                continue
            # data: 帧
            data_lines = []
            for line in frame.split("\n"):
                if line.startswith("data:"):
                    data_lines.append(line[len("data:"):].strip())
            if data_lines:
                payload = " ".join(data_lines)
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    yield {"type": "raw", "data": payload}


# ---------------------------------------------------------------------------
# Mock Server：模拟 AgentScope REST API，用于无依赖演示
# ---------------------------------------------------------------------------
def run_mock_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """在后台线程启动一个 mock FastAPI server，模拟 Agent Service 的关键行为。

    提供端点：
      GET  /health
      POST /agent         → 返回 mock agent_id
      POST /sessions      → 返回 mock session_id
      POST /chat          → 返回 {status:"started"}
      GET  /sessions/{id}/stream → SSE 流，发送若干模拟事件后结束
    """
    import threading
    import uvicorn
    from fastapi import FastAPI, Header
    from fastapi.responses import StreamingResponse
    import asyncio as _asyncio

    mock_app = FastAPI(title="GerClaw Mock AgentScope Server", version="1.0.0")

    @mock_app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "GerClaw-Mock",
            "version": "2.0.3-mock",
            "timestamp": time.time(),
        }

    @mock_app.post("/agent")
    async def create_agent(x_user_id: str = Header(default="anonymous")):
        return {"agent_id": f"agent-mock-{abs(hash(x_user_id)) % 10000}"}

    @mock_app.post("/sessions")
    async def create_session(x_user_id: str = Header(default="anonymous")):
        return {"session_id": f"session-mock-{int(time.time())}"}

    @mock_app.post("/chat")
    async def trigger_chat(x_user_id: str = Header(default="anonymous")):
        return {"status": "started", "session_id": "session-mock-latest"}

    @mock_app.get("/sessions/{session_id}/stream")
    async def sse_stream(session_id: str, x_user_id: str = Header(default="anonymous")):
        async def _gen():
            # 模拟 Agent 思考→回复→工具调用→完成 的事件序列
            events = [
                {"type": "msg", "role": "assistant", "content": [
                    {"type": "thinking", "thinking": "正在分析老年患者的主诉症状..."}
                ]},
                {"type": "msg", "role": "assistant", "content": [
                    {"type": "text", "text": "您好张医生，患者李大爷的初步分析结果如下："}
                ]},
                {"type": "msg", "role": "assistant", "content": [
                    {"type": "text", "text": "1. 主诉：头晕、乏力持续一周\n2. 既往史：高血压10年，糖尿病5年\n3. 建议：先测量卧位/立位血压，排除体位性低血压"}
                ]},
                {"type": "custom", "name": "cga_recommendation", "value": {
                    "domain": "mobility", "risk": "medium",
                    "suggestion": "建议进行起立-行走计时测试(TUG)"
                }},
                {"type": "msg", "role": "assistant", "content": [
                    {"type": "tool_call", "name": "search_guideline",
                     "state": "finished", "input": "老年头晕鉴别诊断",
                     "output": "参考《老年头晕诊断治疗专家共识》..."}
                ]},
            ]
            import json as _json
            for i, evt in enumerate(events):
                await _asyncio.sleep(0.4)  # 模拟网络延迟
                yield f"data: {_json.dumps(evt, ensure_ascii=False)}\n\n"
            # 结束帧
            yield f"data: {_json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    config = uvicorn.Config(mock_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # 等待 server 启动
    time.sleep(1.0)
    return server


# ---------------------------------------------------------------------------
# 核心客户端逻辑
# ---------------------------------------------------------------------------
async def call_health(client: httpx.AsyncClient) -> dict:
    """调用健康检查端点。"""
    print("\n[1] 健康检查 GET /health")
    r = await client.get("/health")
    r.raise_for_status()
    data = r.json()
    print(f"    响应: status={data.get('status')}, service={data.get('service')}")
    return data


async def create_agent(
    client: httpx.AsyncClient,
    name: str = "GerClaw老年科AI助手",
    system_prompt: str = "你是GerClaw平台的老年科AI助手，擅长老年综合评估(CGA)、慢病管理和用药审查。",
) -> str:
    """创建一个 Agent。"""
    print(f"\n[2] 创建 Agent POST /agent  name={name!r}")
    payload = {
        "name": name,
        "system_prompt": system_prompt,
        "context_config": {"trigger_ratio": 0.8, "tool_result_limit": 3000},
        "react_config": {"max_iters": 15, "stop_on_reject": False},
    }
    r = await client.post("/agent", json=payload)
    r.raise_for_status()
    data = r.json()
    agent_id = data.get("agent_id", "unknown")
    print(f"    agent_id = {agent_id}")
    return agent_id


async def list_agents(client: httpx.AsyncClient) -> list:
    """列出所有 Agent。"""
    print("\n[2b] 列出 Agent GET /agent")
    r = await client.get("/agent")
    r.raise_for_status()
    data = r.json()
    print(f"    共 {data.get('total', 0)} 个 Agent")
    return data.get("agents", [])


async def create_credential_dashscope(client: httpx.AsyncClient) -> str | None:
    """创建 DashScope 凭证（real 模式，需要 DASHSCOPE_API_KEY）。"""
    if not DASHSCOPE_KEY:
        print("\n[3] 跳过凭证创建（未设置 DASHSCOPE_API_KEY）")
        return None
    print("\n[3] 创建 DashScope 凭证 POST /credential")
    payload = {
        "data": {
            "type": "dashscope_chat",
            "api_key": DASHSCOPE_KEY,
        }
    }
    try:
        r = await client.post("/credential", json=payload)
        r.raise_for_status()
        cid = r.json().get("credential_id")
        print(f"    credential_id = {cid}")
        return cid
    except Exception as e:
        print(f"    创建凭证失败（mock 模式下忽略）: {e}")
        return None


async def create_session(
    client: httpx.AsyncClient,
    agent_id: str,
    credential_id: str | None = None,
) -> str:
    """创建会话。"""
    print(f"\n[4] 创建 Session POST /sessions  agent_id={agent_id}")
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "workspace_id": None,
        "name": "老年科问诊会话",
    }
    if credential_id:
        payload["chat_model_config"] = {
            "type": "dashscope_chat",
            "credential_id": credential_id,
            "model": "qwen-plus",
            "parameters": {"temperature": 0.7},
        }
    r = await client.post("/sessions", json=payload)
    r.raise_for_status()
    sid = r.json().get("session_id", "unknown")
    print(f"    session_id = {sid}")
    return sid


async def trigger_chat(
    client: httpx.AsyncClient,
    agent_id: str,
    session_id: str,
    message: str = "患者李大爷，78岁，主诉头晕一周，既往高血压、糖尿病，请给出初步评估建议。",
) -> dict:
    """触发聊天（fire-and-forget，立即返回）。"""
    print(f"\n[5] 触发聊天 POST /chat")
    print(f"    消息: {message[:50]}...")
    # 构造 Msg 对象（AgentScope 的标准消息格式）
    payload = {
        "agent_id": agent_id,
        "session_id": session_id,
        "input": {
            "name": "doctor_zhang3",
            "role": "user",
            "content": [{"type": "text", "text": message}],
        },
    }
    r = await client.post("/chat", json=payload)
    r.raise_for_status()
    data = r.json()
    print(f"    响应: status={data.get('status')}, session_id={data.get('session_id')}")
    return data


async def subscribe_sse(
    client: httpx.AsyncClient,
    agent_id: str,
    session_id: str,
    max_events: int = 20,
    timeout: float = 30.0,
) -> list[dict]:
    """订阅 SSE 事件流并打印解析后的事件。"""
    print(f"\n[6] 订阅 SSE GET /sessions/{session_id}/stream?agent_id={agent_id}")
    print("    --- 事件流开始 ---")
    url = f"/sessions/{session_id}/stream"
    events_received: list[dict] = []
    started = time.monotonic()

    async with client.stream(
        "GET",
        url,
        params={"agent_id": agent_id},
        timeout=httpx.Timeout(connect=10.0, read=timeout+5.0, write=10.0, pool=10.0),
    ) as response:
        response.raise_for_status()
        async for event in parse_sse_stream(response, timeout=timeout):
            elapsed = time.monotonic() - started
            etype = event.get("type", "unknown")

            if etype == "heartbeat":
                print(f"    [{elapsed:5.1f}s] ♥ 心跳")
                continue
            if etype == "done":
                print(f"    [{elapsed:5.1f}s] ■ 流结束标记")
                events_received.append(event)
                break

            # 打印事件摘要
            role = event.get("role", "")
            content = event.get("content", [])
            text_parts = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(block.get("text", "")[:80])
                elif btype == "thinking":
                    text_parts.append(f"[思考] {block.get('thinking', '')[:50]}")
                elif btype == "tool_call":
                    text_parts.append(
                        f"[工具调用] {block.get('name')} state={block.get('state')}"
                    )
            summary = " | ".join(text_parts) if text_parts else json.dumps(event, ensure_ascii=False)[:100]
            print(f"    [{elapsed:5.1f}s] {etype}/{role}: {summary}")
            events_received.append(event)

            if len(events_received) >= max_events:
                print(f"    达到最大事件数 {max_events}，断开连接")
                break

    print("    --- 事件流结束 ---")
    print(f"    共接收 {len(events_received)} 个事件")
    return events_received


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(description="GerClaw AgentScope REST API 客户端示例")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock",
                        help="运行模式：mock（内置模拟服务器）或 real（连接真实服务）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="服务端 URL")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="用户 ID")
    parser.add_argument("--timeout", type=float, default=20.0, help="SSE 超时秒数")
    args = parser.parse_args()

    mock_server = None
    base_url = args.base_url

    if args.mode == "mock":
        print("=" * 60)
        print("GerClaw REST API 客户端 — MOCK 模式")
        print("=" * 60)
        # 启动 mock server
        mock_port = 8765
        mock_server = run_mock_server(port=mock_port)
        base_url = f"http://127.0.0.1:{mock_port}"
        print(f"Mock server 已启动: {base_url}")
    else:
        print("=" * 60)
        print("GerClaw REST API 客户端 — REAL 模式")
        print(f"目标服务: {base_url}")
        print("=" * 60)

    headers = build_headers(user_id=args.user_id)
    try:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:
            # 1. 健康检查
            await call_health(client)

            # 2. 创建 Agent
            agent_id = await create_agent(client)
            await list_agents(client)

            # 3. 创建凭证（real 模式）
            cred_id = await create_credential_dashscope(client)

            # 4. 创建 Session
            session_id = await create_session(client, agent_id, cred_id)

            # 5. 触发聊天
            await trigger_chat(client, agent_id, session_id)

            # 等待少许时间让后台任务启动
            await asyncio.sleep(0.5)

            # 6. 订阅 SSE 流
            await subscribe_sse(client, agent_id, session_id, timeout=args.timeout)

    except httpx.ConnectError as e:
        print(f"\n[错误] 无法连接到 {base_url}: {e}")
        if args.mode == "real":
            print("  提示：请先启动 gerclaw_api_server.py 并确保 Redis 可用")
        else:
            print("  提示：mock server 启动可能需要稍等，重试即可")
    except httpx.HTTPStatusError as e:
        print(f"\n[错误] HTTP {e.response.status_code}: {e.response.text[:200]}")
    finally:
        if mock_server is not None:
            mock_server.should_exit = True
            print("\nMock server 已关闭")

    print("\n演示完成。")


if __name__ == "__main__":
    asyncio.run(main())
