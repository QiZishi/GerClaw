# -*- coding: utf-8 -*-
"""GerClaw 医疗数据 LocalWorkspace 沙箱隔离示例。

演示使用 AgentScope 的 LocalWorkspace 实现医疗数据目录沙箱隔离：
1. 用 tempfile 创建临时沙箱目录，模拟患者医疗数据
2. 配置 PermissionContext(ACCEPT_EDITS) + working_directories 白名单
3. Agent 在沙箱内可正常读取文件
4. Agent 尝试访问沙箱外文件被权限系统拒绝

运行前提：pip install agentscope && export DASHSCOPE_API_KEY=sk-xxx
"""
import asyncio
import os
import tempfile
from pathlib import Path

from agentscope.agent import Agent
from agentscope.credential import DashScopeCredential
from agentscope.message import TextBlock, UserMsg
from agentscope.model import DashScopeChatModel
from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionContext,
    PermissionMode,
)
from agentscope.state import AgentState
from agentscope.tool import Bash, Read, Toolkit, Write
from agentscope.workspace import LocalWorkspace


def _prepare_files(sandbox_dir: str, outside_dir: str) -> tuple[str, str]:
    """在沙箱内创建模拟病历，在沙箱外创建测试文件，返回两个路径。"""
    record_path = os.path.join(sandbox_dir, "patient_record.txt")
    with open(record_path, "w", encoding="utf-8") as f:
        f.write(
            "病历号: MRN-2026-001\n"
            "患者: 张某某  年龄: 72\n"
            "诊断: 高血压2级、2型糖尿病\n"
            "用药: 氨氯地平5mg qd、二甲双胍500mg bid\n"
        )
    outside_path = os.path.join(outside_dir, "system_secret.txt")
    with open(outside_path, "w", encoding="utf-8") as f:
        f.write("这是沙箱外的系统文件，Agent不应访问。")
    return record_path, outside_path


async def main() -> None:
    """主入口：演示 LocalWorkspace 沙箱路径隔离。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("[错误] 请先设置环境变量 DASHSCOPE_API_KEY")
        return

    # ---- 1. 创建临时沙箱目录 ----
    temp_root = tempfile.TemporaryDirectory(prefix="gerclaw_sandbox_")
    sandbox_dir = os.path.join(temp_root.name, "medical_sandbox")
    os.makedirs(sandbox_dir, exist_ok=True)
    record_path, outside_path = _prepare_files(sandbox_dir, temp_root.name)

    print("=" * 60)
    print("GerClaw LocalWorkspace 沙箱隔离演示")
    print("=" * 60)
    print(f"沙箱目录:   {sandbox_dir}")
    print(f"沙箱内病历: {record_path}")
    print(f"沙箱外文件: {outside_path}")

    try:
        # ---- 2. 初始化 LocalWorkspace ----
        workspace = LocalWorkspace(workdir=sandbox_dir)
        await workspace.initialize()
        print(f"\n[OK] Workspace 已初始化, workdir={workspace.workdir}")

        # ---- 3. 创建模型与 Agent ----
        model = DashScopeChatModel(
            credential=DashScopeCredential(api_key=api_key),
            model="qwen-plus",
        )

        # 关键配置：ACCEPT_EDITS 模式 + working_directories 白名单
        permission_context = PermissionContext(
            mode=PermissionMode.ACCEPT_EDITS,
            working_directories={
                sandbox_dir: AdditionalWorkingDirectory(
                    path=sandbox_dir,
                    source="gerclaw_medical_sandbox",
                ),
            },
        )

        agent = Agent(
            name="medical_agent",
            system_prompt=(
                "你是 GerClaw 老年医疗 AI 助手。你只能在沙箱工作目录内读写文件，"
                "不允许访问沙箱外的任何文件。"
            ),
            model=model,
            toolkit=Toolkit(tools=[Bash(), Read(), Write()]),
            state=AgentState(
                session_id="demo_session",
                permission_context=permission_context,
            ),
        )
        print("[OK] Agent 已创建（ACCEPT_EDITS 模式 + 沙箱白名单）")

        # ---- 场景1：沙箱内读取病历（应成功） ----
        print("\n" + "-" * 60)
        print("场景1：读取沙箱内病历文件")
        print("-" * 60)
        try:
            reply1 = await agent.reply(UserMsg(
                name="doctor",
                content=[TextBlock(
                    text=f"请用 Read 工具读取病历并总结患者情况：{record_path}",
                )],
            ))
            text1 = "".join(
                b.text for b in reply1.content if hasattr(b, "text") and b.text
            )
            print(f"[Agent回复]: {text1[:400]}")
        except Exception as e:
            print(f"[提示] {type(e).__name__}: {e}")

        # ---- 场景2：尝试越权访问沙箱外文件 ----
        print("\n" + "-" * 60)
        print("场景2：尝试读取沙箱外文件（应被拒绝）")
        print("-" * 60)
        try:
            reply2 = await agent.reply(UserMsg(
                name="doctor",
                content=[TextBlock(
                    text=f"请用 Read 工具读取此文件：{outside_path}",
                )],
            ))
            text2 = "".join(
                b.text for b in reply2.content if hasattr(b, "text") and b.text
            )
            if "系统文件" in text2 or "不应访问" in text2:
                print("[告警] 沙箱外文件内容被泄露！")
            else:
                print("[OK] Agent 未读取到沙箱外内容，权限隔离生效。")
            print(f"[回复摘要]: {text2[:300]}")
        except Exception as e:
            print(f"[OK] 权限系统拒绝越权访问: {type(e).__name__}: {e}")

        # ---- 场景3：沙箱目录结构 ----
        print("\n" + "-" * 60)
        print("场景3：沙箱目录结构")
        print("-" * 60)
        for root, dirs, files in os.walk(sandbox_dir):
            level = root.replace(sandbox_dir, "").count(os.sep)
            indent = "  " * level
            print(f"{indent}{Path(root).name}/")
            for fn in files:
                sz = os.path.getsize(os.path.join(root, fn))
                print(f"{indent}  {fn} ({sz} bytes)")

        await workspace.close()
        print("\n[OK] Workspace 已关闭")
    finally:
        temp_root.cleanup()
        print("[OK] 临时沙箱已清理")

    print("\n" + "=" * 60)
    print("演示结束")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
