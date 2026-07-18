# -*- coding: utf-8 -*-
"""
GerClaw 老年医疗AI平台 — TTS/STT 自定义工具示例

本示例演示在AgentScope中通过FunctionTool包装语音合成(TTS)和语音识别(STT)函数，
使Agent能够在对话中自主调用语音工具：
  - text_to_speech: 将文本回复合成为语音（模拟DashScope CosyVoice/Sambert API）
  - speech_to_text: 将语音音频识别为文字（模拟DashScope Paraformer API）

老年场景优化：
  - TTS默认语速0.85x（慢速），音量+20%，支持多种老年友好音色
  - STT支持方言识别、医疗热词增强、慢速口语优化
  - 关键医学信息（药名/剂量）播报时自动降速至0.75x

注意：本示例使用mock模拟语音API，不真实调用DashScope服务，不下载音频文件。
如需真实调用，请设置DASHSCOPE_API_KEY环境变量并替换mock实现。

运行方式：
    export DASHSCOPE_API_KEY="your-key"   # 可选，有则演示Agent真实推理
    python tts_stt_tools.py
"""
import asyncio
import base64
import json
import os
import random
import time
from typing import Optional

from pydantic import Field

from agentscope.credential import DashScopeCredential
from agentscope.message import (
    Msg, TextBlock, DataBlock, Base64Source,
    ToolCallBlock, ToolResultBlock, ToolResultState,
)
from agentscope.model import DashScopeChatModel
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit, ToolBase, ParamsBase, ToolChunk
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision


# ============================================================
# Mock 语音数据和工具函数
# ============================================================

# 模拟老年患者语音对应的文字（mock STT结果）
MOCK_STT_RESULTS = {
    "降压药": "医生，我那个降压药怎么吃来着？最近血压有点高，头有点晕。",
    "血糖": "大夫，我早上测血糖8.5，是不是太高了？降糖药要不要加量？",
    "睡眠": "医生啊，我最近老是睡不着觉，一晚上醒好几次，能不能开点安眠药？",
    "腿疼": "我这膝盖疼了好几个月了，上下楼梯特别费劲，是不是骨质疏松啊？",
    "用药确认": "好的医生，我记住了，氨氯地平每天早上吃一片，饭后吃对不对？",
}

# 模拟医疗热词表（药名/疾病名/俗称映射）
MEDICAL_HOTWORDS = {
    "降压药": "氨氯地平/硝苯地平/缬沙坦",
    "降糖药": "二甲双胍/格列美脲/胰岛素",
    "钙片": "碳酸钙D3/骨化三醇",
    "安眠药": "艾司唑仑/佐匹克隆",
    "阿托伐他听": "阿托伐他汀",
    "二加双胍": "二甲双胍",
}

# TTS音色配置（老年友好）
TTS_VOICES = {
    "Cherry": "女声清晰，适合医学指导播报",
    "Ethan": "男声沉稳，适合健康建议",
    "Serena": "女声温柔，适合安抚和心理疏导",
}


def _generate_mock_audio_base64(text: str, sample_rate: int = 24000) -> str:
    """生成模拟音频数据的base64编码（实际应为WAV/PCM数据）。

    在真实场景中，这里应调用DashScope TTS API返回真实音频。
    此处生成伪造的WAV头+随机字节来模拟音频数据。
    """
    # 构建44字节WAV头
    import struct
    channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    # 根据文本长度估算音频时长（约每秒4个汉字）
    duration_sec = max(1.0, len(text) * 0.25)
    data_size = int(sample_rate * channels * bits_per_sample // 8 * duration_sec)
    wav_header = (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", 16)
        + struct.pack("<HHIIHH", 1, channels, sample_rate, byte_rate, block_align, bits_per_sample)
        + b"data"
        + struct.pack("<I", data_size)
    )
    # 模拟PCM数据（静音/噪声模式，实际应为TTS合成的语音波形）
    mock_pcm = bytes([random.randint(0, 255) for _ in range(min(data_size, 1000))])
    if data_size > 1000:
        mock_pcm = mock_pcm * (data_size // 1000 + 1)
        mock_pcm = mock_pcm[:data_size]
    return base64.b64encode(wav_header + mock_pcm).decode("ascii")


# ============================================================
# STT 语音识别工具（FunctionTool方式）
# ============================================================

async def speech_to_text(
    audio_base64: str = "",
    audio_format: str = "wav",
    sample_rate: int = 16000,
    language: str = "zh",
    dialect: str = "auto",
    enable_hotwords: bool = True,
    hotwords: Optional[str] = None,
) -> str:
    """将语音音频识别为文字，专门优化老年人口语识别场景。

    支持方言识别、医疗热词增强、慢速口语识别。当接收到音频数据时，
    将老年患者的语音输入转换为文字供AI医生分析。识别结果会自动进行
    医疗术语纠错（如'阿托伐他听'→'阿托伐他汀'）。

    Args:
        audio_base64: base64编码的音频数据（WAV/PCM格式）
        audio_format: 音频格式，支持wav/pcm/mp3，默认wav
        sample_rate: 采样率，推荐16000Hz，老年语音建议不低于16kHz
        language: 语言代码，zh(中文)/en(英文)/auto(自动检测)，默认zh
        dialect: 方言选择: auto(自动检测)/cantonese(粤语)/sichuanhua(四川话)
                 /northeast(东北话)/mandarin(普通话)，默认auto
        enable_hotwords: 是否启用医疗热词增强，提高药名/疾病名识别准确率，默认True
        hotwords: 自定义热词，逗号分隔，如'阿托伐他汀,二甲双胍,氨氯地平'

    Returns:
        str: 识别出的文字内容，包含标点符号
    """
    await asyncio.sleep(0.3)  # 模拟STT API延迟（真实Paraformer流式约100-300ms）

    audio_len = len(audio_base64) if audio_base64 else 0

    # Mock: 根据音频数据长度或随机选择一个预设的识别结果
    # 真实实现应调用: dashscope.audio.asr.Recognition 或 FunASR WebSocket
    if audio_len > 0:
        # 简单模拟：根据base64长度伪随机选择一个结果
        idx = audio_len % len(MOCK_STT_RESULTS)
        result_text = list(MOCK_STT_RESULTS.values())[idx]
    else:
        result_text = "医生你好，我想咨询一下用药的问题。"

    # 医疗热词纠错后处理
    if enable_hotwords:
        for wrong, correct in MEDICAL_HOTWORDS.items():
            if wrong in result_text and wrong != correct:
                result_text = result_text.replace(wrong, correct)

    # 方言信息附加（mock）
    dialect_info = ""
    if dialect == "cantonese":
        dialect_info = " [粤语模式]"
    elif dialect == "sichuanhua":
        dialect_info = " [四川话模式]"
    elif dialect == "auto":
        dialect_info = " [自动检测方言]"

    return f"[STT识别{dialect_info}] {result_text}"


# ============================================================
# TTS 语音合成工具（ToolBase方式，更精细控制）
# ============================================================

class ElderlyTTSTool(ToolBase):
    """老年医疗语音合成工具。

    将文本合成为语音，针对老年用户做了专门优化：
    - 默认语速0.85x（慢速），确保听清楚
    - 默认音量增益+20%，补偿听力下降
    - 医学建议/用药指导自动降速至0.75x
    - 支持多种老年友好音色选择
    - 支持关键信息重复播报
    """

    name: str = "text_to_speech"
    description: str = (
        "将文本内容合成为语音播报给老年患者。当需要向用户传达用药指导、"
        "健康建议、就诊提醒等信息时调用此工具。"
        "自动优化语速和音量适合老年人收听，"
        "关键医学信息会慢速清晰播报并可重复。"
        "播报完成后返回音频数据和播报确认信息。"
    )

    class Params(ParamsBase):
        """TTS参数定义"""
        text: str = Field(
            ...,
            description="要合成语音的文本内容",
        )
        voice: str = Field(
            "Cherry",
            description="音色选择: Cherry(女声清晰)/Ethan(男声沉稳)/Serena(女声温柔)",
        )
        speed: float = Field(
            0.85,
            ge=0.5, le=1.5,
            description="语速倍率，老年场景建议0.7-0.9（默认0.85慢速），医学建议建议0.75",
        )
        volume_gain: float = Field(
            1.2,
            ge=0.5, le=2.0,
            description="音量增益倍数，老年听力下降建议1.2-1.5（默认1.2即+20%）",
        )
        is_medical_advice: bool = Field(
            False,
            description="是否为医学建议/用药指导（True时自动降速至0.75x，清晰播报）",
        )
        repeat_count: int = Field(
            1,
            ge=1, le=3,
            description="重复播报次数，关键信息可设置2-3次重复",
        )

    input_schema: dict = Params.model_json_schema()
    is_concurrency_safe: bool = True
    is_read_only: bool = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        """权限检查：语音合成为安全操作，默认允许。"""
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="语音合成为只读安全操作，允许执行。",
        )

    async def call(self, **kwargs) -> ToolChunk:
        """执行TTS合成。"""
        params = self.Params(**kwargs)

        # 医学建议自动降速
        actual_speed = params.speed
        if params.is_medical_advice and params.speed > 0.75:
            actual_speed = 0.75

        await asyncio.sleep(0.2)  # 模拟TTS API延迟

        # 生成模拟音频数据（真实实现调用DashScope TTS API）
        audio_b64 = _generate_mock_audio_base64(params.text)

        # 构造结果文本描述
        voice_desc = TTS_VOICES.get(params.voice, "默认音色")
        result_text = (
            f"[TTS语音合成完成]\n"
            f"- 音色: {params.voice}({voice_desc})\n"
            f"- 语速: {actual_speed}x"
            f"{' (医学建议慢速模式)' if params.is_medical_advice else ''}\n"
            f"- 音量: {params.volume_gain}x ({'+' if params.volume_gain > 1 else ''}"
            f"{int((params.volume_gain - 1) * 100)}%)\n"
            f"- 重复次数: {params.repeat_count}\n"
            f"- 文本长度: {len(params.text)}字\n"
            f"- 音频数据: base64编码WAV格式（{len(audio_b64)}字符）\n"
            f"- 合成文本: {params.text[:100]}{'...' if len(params.text) > 100 else ''}"
        )

        # 返回音频DataBlock + 文本描述
        return ToolChunk(content=[
            DataBlock(
                source=Base64Source(data=audio_b64, media_type="audio/wav"),
                name=f"tts_output_{int(time.time())}.wav",
            ),
            TextBlock(text=result_text),
        ])


# ============================================================
# 工具注册与演示
# ============================================================

SYSTEM_PROMPT = (
    "你是GerClaw老年医疗AI平台的语音医生助手。"
    "你可以使用speech_to_text工具将语音转为文字，使用text_to_speech工具将回复转为语音。"
    "与老年患者交流时：\n"
    "1. 说话要慢、清晰、简洁，避免使用专业术语\n"
    "2. 用药指导必须使用text_to_speech合成语音（设置is_medical_advice=true）\n"
    "3. 关键信息（药名、剂量、时间）要重复强调\n"
    "4. 每次回复都应该用语音播报给老人\n"
    "5. 如老人描述紧急症状（胸痛/呼吸困难/意识障碍），立即建议拨打120"
)


async def demo_stt_function_tool() -> FunctionTool:
    """演示创建STT FunctionTool。"""
    print("=" * 60)
    print("步骤1：创建STT语音识别工具（FunctionTool方式）")
    print("=" * 60)

    stt_tool = FunctionTool(
        func=speech_to_text,
        name="speech_to_text",
        is_read_only=True,
        is_concurrency_safe=True,
    )

    # 查看工具schema
    print(f"\n工具名称: {stt_tool.name}")
    print(f"工具描述: {stt_tool.description[:80]}...")
    schema = stt_tool.input_schema
    params = schema.get("properties", {})
    print(f"参数列表: {list(params.keys())}")

    return stt_tool


async def demo_tts_toolbase() -> ElderlyTTSTool:
    """演示创建TTS ToolBase工具。"""
    print("\n" + "=" * 60)
    print("步骤2：创建TTS语音合成工具（ToolBase方式）")
    print("=" * 60)

    tts_tool = ElderlyTTSTool()

    print(f"\n工具名称: {tts_tool.name}")
    print(f"工具描述: {tts_tool.description[:80]}...")
    params = tts_tool.input_schema.get("properties", {})
    print(f"参数列表: {list(params.keys())}")

    return tts_tool


async def demo_direct_stt_call(stt_tool: FunctionTool) -> None:
    """演示直接调用STT工具进行语音识别。"""
    print("\n" + "=" * 60)
    print("步骤3：直接调用STT工具 — 模拟老年患者语音输入")
    print("=" * 60)

    state = AgentState()

    # 模拟老年患者语音数据（mock base64音频）
    mock_audio = base64.b64encode(b"\x00" * 32000).decode("ascii")  # ~1秒@16kHz

    test_cases = [
        {"audio_base64": mock_audio, "dialect": "auto", "enable_hotwords": True},
        {"audio_base64": mock_audio, "dialect": "cantonese", "enable_hotwords": True},
    ]

    for i, tc in enumerate(test_cases, 1):
        tool_call = ToolCallBlock(
            id=f"stt_call_{i:03d}",
            name="speech_to_text",
            input=json.dumps(tc),
        )
        print(f"\n[STT调用 #{i}] dialect={tc['dialect']}, hotwords={tc['enable_hotwords']}")
        async for result in Toolkit(tools=[stt_tool]).call_tool(tool_call, state):
            if hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        print(f"识别结果: {block.text}")


async def demo_direct_tts_call(tts_tool: ElderlyTTSTool) -> None:
    """演示直接调用TTS工具进行语音合成。"""
    print("\n" + "=" * 60)
    print("步骤4：直接调用TTS工具 — 合成老年用药指导语音")
    print("=" * 60)

    state = AgentState()

    test_cases = [
        {
            "text": "您好，您的血压药氨氯地平，每天早上饭后吃一片，"
                    "不要自己随便停药。吃药期间注意监测血压，"
                    "如果有头晕、乏力的情况要及时告诉家人或者来医院看。",
            "is_medical_advice": True,
            "voice": "Ethan",
        },
        {
            "text": "好的，您的情况我了解了。请您不要担心，"
                    "保持心情愉快，适当散步，饮食清淡一些。",
            "is_medical_advice": False,
            "voice": "Serena",
            "speed": 0.9,
        },
    ]

    for i, tc in enumerate(test_cases, 1):
        tool_call = ToolCallBlock(
            id=f"tts_call_{i:03d}",
            name="text_to_speech",
            input=json.dumps(tc),
        )
        print(f"\n[TTS调用 #{i}] voice={tc.get('voice', 'Cherry')}, "
              f"medical={tc.get('is_medical_advice', False)}")
        print(f"合成文本: {tc['text'][:60]}...")
        async for result in Toolkit(tools=[tts_tool]).call_tool(tool_call, state):
            if hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        print(f"合成结果:\n{block.text}")
                    elif hasattr(block, "source"):
                        data_len = len(block.source.data) if block.source else 0
                        print(f"音频块: {block.name}, 格式={block.source.media_type}, "
                              f"数据大小={data_len}字符base64")


async def demo_agent_with_tools(stt_tool: FunctionTool, tts_tool: ElderlyTTSTool) -> None:
    """当DASHSCOPE_API_KEY存在时，演示Agent通过ReAct循环调用语音工具。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("\n" + "=" * 60)
        print("步骤5：Agent推理演示（跳过）")
        print("=" * 60)
        print("未检测到 DASHSCOPE_API_KEY 环境变量，跳过Agent推理演示。")
        print("如需运行Agent推理，请设置: export DASHSCOPE_API_KEY='your-key'")
        print("\n示例运行完成。")
        return

    print("\n" + "=" * 60)
    print("步骤5：Agent真实推理演示（语音对话流程）")
    print("=" * 60)

    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen3.5-plus",
        stream=False,
        context_size=131072,
    )

    toolkit = Toolkit(tools=[stt_tool, tts_tool])
    tools = await toolkit.get_tool_schemas()

    # 模拟：老年患者语音输入 -> STT识别 -> Agent处理 -> TTS语音输出
    mock_audio = base64.b64encode(b"\x00" * 32000).decode("ascii")
    msgs = [
        Msg(name="system", role="system", content=[TextBlock(text=SYSTEM_PROMPT)]),
        Msg(
            name="elderly_patient",
            role="user",
            content=[
                DataBlock(
                    source=Base64Source(data=mock_audio, media_type="audio/wav"),
                    name="patient_voice.wav",
                ),
                TextBlock(text="[用户发送了一段语音消息，请先使用speech_to_text工具识别]"),
            ],
        ),
    ]

    print("\n[Round 1] 发送语音消息给Agent...")
    response = await model(msgs, tools=tools)
    assistant_content = response.content if response else []

    tool_calls = [b for b in assistant_content if isinstance(b, ToolCallBlock)]
    text_blocks = [b for b in assistant_content if isinstance(b, TextBlock)]

    for tb in text_blocks:
        if tb.text.strip():
            print(f"Agent思考: {tb.text[:200]}")

    if not tool_calls:
        print("Agent未调用工具，直接回复（可能需要调整prompt）")
        return

    # 执行工具调用（STT + TTS）
    state = AgentState()
    tool_result_blocks = []
    for tc in tool_calls:
        print(f"\nAgent调用工具: {tc.name}")
        args = json.loads(tc.input)
        async for result in toolkit.call_tool(tc, state):
            if hasattr(result, "content"):
                output_parts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        output_parts.append(block.text[:200])
                    elif hasattr(block, "source"):
                        output_parts.append(f"[音频数据 {len(block.source.data)}字符]")
                tool_result_blocks.append(
                    ToolResultBlock(
                        id=tc.id,
                        name=tc.name,
                        output="\n".join(output_parts),
                        state=ToolResultState.SUCCESS,
                    )
                )

    # 组装第二轮消息
    assistant_msg = Msg(name="voice_doctor", role="assistant", content=assistant_content)
    tool_msg = Msg(name="tool", role="assistant", content=tool_result_blocks)
    msgs = msgs + [assistant_msg, tool_msg]

    print("\n[Round 2] 将工具结果发给Agent，生成语音回复...")
    response2 = await model(msgs, tools=tools)
    final_text = ""
    for block in (response2.content if response2 else []):
        if isinstance(block, TextBlock):
            final_text += block.text
        elif isinstance(block, ToolCallBlock):
            print(f"Agent再次调用工具: {block.name}")

    print(f"\nAgent文字回复:\n{final_text[:500]}")
    print("\n示例运行完成。")


async def main() -> None:
    """主入口：创建工具 → 直接调用演示 → Agent推理演示。"""
    print("GerClaw 老年医疗AI平台 — TTS/STT语音工具演示")
    print("AgentScope FunctionTool + ToolBase 双模式示例\n")

    stt_tool = await demo_stt_function_tool()
    tts_tool = await demo_tts_toolbase()

    toolkit = Toolkit(tools=[stt_tool, tts_tool])
    schemas = await toolkit.get_tool_schemas()
    print(f"\nToolkit中已注册 {len(schemas)} 个工具:")
    for s in schemas:
        print(f"  - {s['function']['name']}")

    await demo_direct_stt_call(stt_tool)
    await demo_direct_tts_call(tts_tool)
    await demo_agent_with_tools(stt_tool, tts_tool)


if __name__ == "__main__":
    asyncio.run(main())
