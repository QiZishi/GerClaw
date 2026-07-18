# -*- coding: utf-8 -*-
"""
GerClaw 老年医疗AI平台 — 语音对话流程演示

本示例演示完整的语音对话流程：
  语音输入 → STT转文字 → Agent医疗推理 → TTS转语音输出

使用AgentScope的DataBlock/AudioMsg机制传递音频数据，模拟老年患者
与AI医生之间的多轮语音对话场景。演示了：
  1. 使用DataBlock + Base64Source构造音频消息（AudioMsg模式）
  2. STT语音识别将音频转为文字
  3. Agent处理医疗问题并生成回复
  4. TTS将文字回复转为语音输出
  5. 多轮语音对话上下文维护
  6. 打断信号处理（Barge-in）
  7. 医学关键信息的慢速语音播报

老年场景模拟：
  - 模拟78岁高血压患者张奶奶的语音咨询
  - 包含用药咨询、症状描述、确认理解等多轮对话
  - TTS输出使用慢速(0.8x)和大音量
  - 关键用药信息重复播报

注意：本示例使用mock音频数据和mock STT/TTS，不真实调用语音API，
不下载音频文件。如需真实模型调用，请设置DASHSCOPE_API_KEY。

运行方式：
    export DASHSCOPE_API_KEY="your-key"   # 可选
    python voice_conversation_demo.py
"""
import asyncio
import base64
import json
import os
import random
import struct
import time
from dataclasses import dataclass, field
from typing import Optional

from agentscope.credential import DashScopeCredential
from agentscope.message import (
    Msg, UserMsg, AssistantMsg, TextBlock, DataBlock, Base64Source,
    ToolCallBlock, ToolResultBlock, ToolResultState,
)
from agentscope.model import DashScopeChatModel
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit
from agentscope.event import CustomEvent


# ============================================================
# Mock 音频工具
# ============================================================

def _make_mock_wav_base64(text: str, sample_rate: int = 16000, speaker: str = "elderly_female") -> str:
    """生成模拟WAV音频的base64编码。

    根据speaker参数模拟不同音色特征，实际应用中应替换为真实录音。
    """
    channels = 1
    bits_per_sample = 16
    duration_sec = max(1.0, len(text) * 0.2)  # ~5字/秒（老年语速慢）
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
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
    # 根据speaker生成不同特征的模拟PCM
    if speaker == "elderly_female":
        base_freq = 220  # 老年女声基频
    elif speaker == "elderly_male":
        base_freq = 120  # 老年男声基频
    else:
        base_freq = 180
    mock_pcm = bytes([(base_freq + i * 7) % 256 for i in range(min(data_size, 2000))])
    if data_size > 2000:
        mock_pcm = mock_pcm * (data_size // 2000 + 1)
        mock_pcm = mock_pcm[:data_size]
    return base64.b64encode(wav_header + mock_pcm).decode("ascii")


# ============================================================
# Mock STT/TTS 服务（模拟DashScope Paraformer/CosyVoice）
# ============================================================

@dataclass
class MockSTTService:
    """模拟语音识别服务。"""

    # 预设对话脚本（模拟老年患者张奶奶的语音内容）
    dialogue_script: list[dict] = field(default_factory=lambda: [
        {
            "text": "医生你好啊，我是张桂兰，今年78岁了。"
                    "我想问一下，我那个降压药是不是该调整了？"
                    "最近早上起来头有点晕。",
            "dialect": "mandarin",
            "confidence": 0.92,
        },
        {
            "text": "我现在吃的是氨氯地平，每天早上一片，吃了有两年了。"
                    "最近量血压有时候是150多、90多，是不是控制得不好啊？",
            "dialect": "mandarin",
            "confidence": 0.88,
        },
        {
            "text": "好的好的，我记住了。氨氯地平还是每天早上一片，"
                    "再加一个什么药来着？哦对，利尿剂，半片对吧？"
                    "我耳朵不太好使，你再说一遍呗。",
            "dialect": "mandarin",
            "confidence": 0.85,
        },
        {
            "text": "好的医生，谢谢你啊。那我下次什么时候来复诊啊？"
                    "要不要抽血查什么的？",
            "dialect": "mandarin",
            "confidence": 0.90,
        },
    ])
    turn_index: int = 0

    async def recognize(self, audio_base64: str, dialect: str = "auto") -> dict:
        """模拟STT识别，返回识别结果和置信度。"""
        await asyncio.sleep(0.25)  # 模拟识别延迟

        if self.turn_index < len(self.dialogue_script):
            result = self.dialogue_script[self.turn_index].copy()
            result["turn"] = self.turn_index + 1
            self.turn_index += 1
        else:
            result = {
                "text": "好的好的，谢谢你医生。",
                "dialect": "mandarin",
                "confidence": 0.95,
                "turn": self.turn_index + 1,
            }
            self.turn_index += 1
        return result


@dataclass
class MockTTSService:
    """模拟语音合成服务。"""

    async def synthesize(
        self,
        text: str,
        speed: float = 0.85,
        volume_gain: float = 1.2,
        voice: str = "Cherry",
        is_medical: bool = False,
    ) -> dict:
        """模拟TTS合成，返回音频base64和元信息。"""
        await asyncio.sleep(0.2)  # 模拟合成延迟

        actual_speed = 0.75 if (is_medical and speed > 0.75) else speed
        audio_b64 = _make_mock_wav_base64(text, sample_rate=24000, speaker="doctor_female")

        return {
            "audio_base64": audio_b64,
            "media_type": "audio/wav",
            "voice": voice,
            "speed": actual_speed,
            "volume_gain": volume_gain,
            "duration_sec": max(1.0, len(text) * 0.25 / actual_speed),
            "char_count": len(text),
            "is_medical_advice": is_medical,
        }


# 全局mock服务实例
mock_stt = MockSTTService()
mock_tts = MockTTSService()


# ============================================================
# STT/TTS FunctionTool 定义
# ============================================================

async def stt_recognize(audio_base64: str, dialect: str = "auto") -> str:
    """语音识别工具：将老年患者的语音音频识别为文字。

    支持中文普通话和多方言识别，针对老年人口语特点优化
    （慢速、停顿多、重复词语、口音等）。

    Args:
        audio_base64: base64编码的音频数据（WAV格式）
        dialect: 方言: auto(自动检测)/mandarin(普通话)/cantonese(粤语)/sichuanhua(四川话)

    Returns:
        str: JSON格式的识别结果，包含text(识别文本)、confidence(置信度)、dialect(方言)
    """
    result = await mock_stt.recognize(audio_base64, dialect)
    return json.dumps(result, ensure_ascii=False)


async def tts_synthesize(
    text: str,
    speed: float = 0.85,
    voice: str = "Cherry",
    is_medical_advice: bool = False,
) -> str:
    """语音合成工具：将回复文本合成为语音播放给老年患者。

    针对老年听力特点优化：默认慢速0.85x、音量+20%、清晰音色。
    医学建议自动降速至0.75x并强调关键词。

    Args:
        text: 要合成的文本内容
        speed: 语速倍率，默认0.85（慢速），建议0.7-0.9
        voice: 音色: Cherry(女声清晰)/Ethan(男声沉稳)
        is_medical_advice: 是否为医学建议（True时自动0.75x慢速播报）

    Returns:
        str: JSON格式的合成结果，包含音频数据和播放参数
    """
    result = await mock_tts.synthesize(
        text=text,
        speed=speed,
        voice=voice,
        is_medical=is_medical_advice,
    )
    # 音频数据较大，返回描述性信息而非完整base64
    return json.dumps({
        "status": "synthesized",
        "duration_sec": round(result["duration_sec"], 1),
        "voice": result["voice"],
        "speed": result["speed"],
        "char_count": result["char_count"],
        "is_medical_advice": result["is_medical_advice"],
        "audio_available": True,
    }, ensure_ascii=False)


# ============================================================
# 语音对话管理器
# ============================================================

class VoiceConversationManager:
    """语音对话流程管理器。

    管理完整的语音对话生命周期：
    1. 接收音频输入
    2. 调用STT识别
    3. 维护对话上下文
    4. 调用Agent处理
    5. 调用TTS合成回复语音
    6. 处理打断信号
    """

    def __init__(self, use_real_model: bool = False):
        self.use_real_model = use_real_model
        self.model = None
        self.toolkit = None
        self.tools = None
        self.conversation_history: list[Msg] = []
        self.is_speaking = False  # 是否正在播放TTS
        self.barge_in_requested = False

        # 系统提示词
        self.system_prompt = (
            "你是GerClaw老年医疗AI平台的家庭医生助手，正在与78岁的高血压患者张奶奶进行语音对话。\n"
            "对话规则：\n"
            "1. 说话要慢、清晰、简短，每次回复不超过3句话\n"
            "2. 避免专业术语，用老人能听懂的大白话\n"
            "3. 用药指导必须设置is_medical_advice=true进行慢速播报\n"
            "4. 关键信息（药名、剂量、时间）要重复强调\n"
            "5. 每次回复后调用tts_synthesize将回复转为语音\n"
            "6. 如果患者描述紧急症状（胸痛/呼吸困难/意识模糊），立即建议拨打120\n"
            "7. 语气温和、有耐心，像对待自己家人一样"
        )

    async def initialize(self) -> None:
        """初始化模型和工具。"""
        # 创建工具
        stt_tool = FunctionTool(
            func=stt_recognize,
            name="stt_recognize",
            is_read_only=True,
            is_concurrency_safe=True,
        )
        tts_tool = FunctionTool(
            func=tts_synthesize,
            name="tts_synthesize",
            is_read_only=True,
            is_concurrency_safe=True,
        )
        self.toolkit = Toolkit(tools=[stt_tool, tts_tool])
        self.tools = await self.toolkit.get_tool_schemas()

        # 初始化模型（如果有API Key）
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if self.use_real_model and api_key:
            self.model = DashScopeChatModel(
                credential=DashScopeCredential(api_key=api_key),
                model="qwen3.5-plus",
                stream=False,
                context_size=131072,
            )
            print("[系统] 已连接DashScope模型，将使用真实LLM推理")
        else:
            self.model = None
            print("[系统] 使用Mock模式（未连接真实LLM），将模拟回复")

        # 初始化对话历史
        self.conversation_history = [
            Msg(name="system", role="system", content=[TextBlock(text=self.system_prompt)]),
        ]

    def request_barge_in(self) -> None:
        """请求打断当前TTS播放（模拟VAD检测到用户说话）。"""
        self.barge_in_requested = True
        print("[打断信号] 检测到用户开始说话，请求打断当前TTS播放")

    async def process_voice_input(
        self,
        audio_b64: str,
        turn_num: int,
    ) -> dict:
        """处理一轮语音输入，返回语音输出。

        Returns:
            dict: 包含reply_text、reply_audio、is_barge_in等字段
        """
        self.barge_in_requested = False
        result = {
            "turn": turn_num,
            "stt_text": "",
            "reply_text": "",
            "reply_audio": None,
            "barge_in": False,
            "tool_calls": [],
        }

        # 步骤1: STT语音识别
        print(f"\n{'─' * 50}")
        print(f"[Turn {turn_num}] 收到语音输入，正在识别...")
        stt_result = await mock_stt.recognize(audio_b64)
        stt_text = stt_result["text"]
        confidence = stt_result["confidence"]
        result["stt_text"] = stt_text
        print(f"[STT] 识别结果(置信度{confidence:.0%}): {stt_text}")

        # 置信度低时提示
        if confidence < 0.8:
            print(f"[提示] 识别置信度较低({confidence:.0%})，建议用户重复或切换文字输入")

        # 步骤2: 构造用户消息（包含音频+识别文本）
        user_msg = UserMsg(
            name="张奶奶",
            content=[
                DataBlock(
                    source=Base64Source(data=audio_b64, media_type="audio/wav"),
                    name=f"patient_turn{turn_num}.wav",
                ),
                TextBlock(text=f"[患者语音转写] {stt_text}"),
            ],
        )
        self.conversation_history.append(user_msg)

        # 步骤3: Agent生成回复
        print(f"[Agent] AI医生正在思考...")
        self.is_speaking = True

        if self.model is not None:
            # 真实模型推理
            response = await self.model(self.conversation_history, tools=self.tools)
            assistant_content = response.content if response else []

            # 收集文本和工具调用
            reply_text = ""
            tool_calls = []
            for block in assistant_content:
                if isinstance(block, TextBlock) and block.text.strip():
                    reply_text += block.text
                elif isinstance(block, ToolCallBlock):
                    tool_calls.append(block)

            # 执行工具调用（TTS）
            state = AgentState()
            tool_results = []
            for tc in tool_calls:
                result["tool_calls"].append(tc.name)
                print(f"[Tool] Agent调用: {tc.name}")
                async for tr in self.toolkit.call_tool(tc, state):
                    if hasattr(tr, "content"):
                        for tb in tr.content:
                            if hasattr(tb, "text"):
                                tool_results.append(tb.text)

            # 如果没有自动调用TTS，手动合成
            if "tts_synthesize" not in [tc.name for tc in tool_calls] and reply_text:
                tts_result = await mock_tts.synthesize(reply_text, is_medical="药" in reply_text or "片" in reply_text)
                result["reply_audio"] = tts_result
            else:
                # 从工具结果中获取TTS信息
                tts_result = await mock_tts.synthesize(reply_text, is_medical="药" in reply_text or "片" in reply_text)
                result["reply_audio"] = tts_result

            result["reply_text"] = reply_text

            # 记录到历史
            assistant_msg = AssistantMsg(name="AI医生", content=assistant_content)
            self.conversation_history.append(assistant_msg)
        else:
            # Mock模式：基于关键词生成回复
            reply_text, is_medical = self._mock_doctor_reply(stt_text, turn_num)
            result["reply_text"] = reply_text
            result["reply_audio"] = await mock_tts.synthesize(
                reply_text,
                is_medical=is_medical,
                speed=0.8 if not is_medical else 0.75,
            )
            result["tool_calls"] = ["stt_recognize", "tts_synthesize"]

            # 记录到历史
            self.conversation_history.append(
                AssistantMsg(name="AI医生", content=[TextBlock(text=reply_text)]),
            )

        self.is_speaking = False
        print(f"[TTS] 语音合成完成: {result['reply_audio']['duration_sec']}秒, "
              f"语速{result['reply_audio']['speed']}x, "
              f"{'【医学建议慢速模式】' if result['reply_audio']['is_medical_advice'] else ''}")
        print(f"[AI医生回复] {result['reply_text']}")

        # 模拟打断检测
        if self.barge_in_requested:
            result["barge_in"] = True
            print("[打断] 检测到打断信号，停止播放！")
            self.barge_in_requested = False

        return result

    def _mock_doctor_reply(self, user_text: str, turn_num: int) -> tuple[str, bool]:
        """Mock医生回复逻辑（当没有真实LLM时使用）。"""
        if turn_num == 1:
            return (
                "张奶奶您好！别着急，我慢慢给您看。"
                "头晕可能和血压控制不好有关系。"
                "您先告诉我现在吃什么降压药、怎么吃的？",
                False,
            )
        elif "氨氯地平" in user_text and ("150" in user_text or "控制" in user_text):
            return (
                "张奶奶，您的血压确实偏高了一点。"
                "氨氯地平继续每天早上一片，我给您加半片氢氯噻嗪，"
                "也是早上吃，两种药一起吃效果更好。"
                "记住哦，氨氯地平一片，氢氯噻嗪半片，都是早上饭后吃。"
                "吃两个星期再来量血压看看。",
                True,  # 医学建议
            )
        elif "再说一遍" in user_text or "耳朵" in user_text:
            return (
                "好的好的，我慢一点再说一遍。"
                "您听好了：氨氯地平，每天早上饭后吃一片；"
                "氢氯噻嗪，每天早上饭后吃半片。"
                "两种药都是早上吃，饭后吃。听清楚了吗？",
                True,
            )
        elif "复诊" in user_text or "抽血" in user_text:
            return (
                "两个星期后来复诊就可以。"
                "到时候会给您量个血压，可能查一下血钾和肾功能，"
                "就是抽一点点血，不疼的。"
                "您要是中间有什么不舒服，随时来医院，别拖着。",
                False,
            )
        else:
            return (
                "好的张奶奶，我明白了。您还有什么不舒服的地方吗？"
                "吃药期间要是有头晕加重、胸口闷、手脚肿的情况，"
                "一定要及时告诉家人或者来医院。",
                False,
            )


# ============================================================
# 演示函数
# ============================================================

async def demo_single_voice_message() -> None:
    """演示单条语音消息处理：构造AudioMsg并发送。"""
    print("=" * 60)
    print("演示1：AudioMsg音频消息构造与识别")
    print("=" * 60)

    # 构造模拟老年语音（mock base64 WAV）
    mock_voice_text = "医生你好，我最近血压有点高"
    mock_audio_b64 = _make_mock_wav_base64(mock_voice_text, speaker="elderly_female")
    audio_bytes = base64.b64decode(mock_audio_b64)
    print(f"\n构造音频消息:")
    print(f"  - WAV大小: {len(audio_bytes)} bytes")
    print(f"  - 音频格式: audio/wav")
    print(f"  - 模拟语音内容: {mock_voice_text}")

    # 使用DataBlock构造音频消息（AgentScope中的"AudioMsg"模式）
    voice_msg = UserMsg(
        name="张奶奶",
        content=[
            DataBlock(
                source=Base64Source(data=mock_audio_b64, media_type="audio/wav"),
                name="patient_voice.wav",
            ),
        ],
    )

    print(f"\n消息构造成功:")
    print(f"  - name: {voice_msg.name}")
    print(f"  - role: {voice_msg.role}")
    print(f"  - content blocks: {len(voice_msg.content)}")
    for block in voice_msg.content:
        if hasattr(block, "type"):
            print(f"    * type={block.type}, ", end="")
            if block.type == "data":
                print(f"media_type={block.source.media_type}, "
                      f"data_len={len(block.source.data)}char(base64)")

    # STT识别
    print(f"\n调用STT识别...")
    stt_tool = FunctionTool(func=stt_recognize, name="stt_recognize", is_read_only=True)
    state = AgentState()
    tool_call = ToolCallBlock(
        id="stt_demo_001",
        name="stt_recognize",
        input=json.dumps({"audio_base64": mock_audio_b64, "dialect": "auto"}),
    )
    async for result in Toolkit(tools=[stt_tool]).call_tool(tool_call, state):
        for block in result.content:
            if hasattr(block, "text"):
                stt_data = json.loads(block.text)
                print(f"识别结果: {stt_data['text']}")
                print(f"置信度: {stt_data['confidence']:.0%}")
                print(f"方言: {stt_data['dialect']}")


async def demo_voice_conversation() -> None:
    """演示多轮语音对话流程。"""
    print("\n" + "=" * 60)
    print("演示2：多轮语音对话（老年患者咨询场景）")
    print("=" * 60)
    print("\n场景：78岁张奶奶通过语音咨询高血压用药调整")
    print("─" * 50)

    manager = VoiceConversationManager(use_real_model=False)
    await manager.initialize()

    # 模拟4轮对话
    mock_scripts = [
        "医生你好啊，我是张桂兰...",
        "我现在吃的是氨氯地平...",
        "好的好的，我记住了...",
        "好的医生，谢谢你啊...",
    ]

    for i, script in enumerate(mock_scripts, 1):
        # 模拟用户语音输入
        mock_audio = _make_mock_wav_base64(script, speaker="elderly_female")
        result = await manager.process_voice_input(mock_audio, turn_num=i)

        # 在第3轮模拟打断（用户等不及慢速播报就说话了）
        if i == 3 and not result["barge_in"]:
            # 模拟打断：在TTS播放到一半时用户说话
            await asyncio.sleep(0.1)
            print("\n[模拟] 第3轮TTS播放中...用户开始说话，触发打断！")
            manager.request_barge_in()

    # 对话统计
    print(f"\n{'=' * 60}")
    print("对话结束统计:")
    print(f"  - 总轮数: {mock_stt.turn_index}")
    print(f"  - 对话历史消息数: {len(manager.conversation_history)}")
    print(f"  - 打断次数: {1 if manager.barge_in_requested else 0}")


async def demo_barge_in_mechanism() -> None:
    """演示语音打断机制（Barge-in）。"""
    print("\n" + "=" * 60)
    print("演示3：语音打断机制（Barge-in）")
    print("=" * 60)
    print("\n场景：AI医生正在TTS播报用药指导，张奶奶突然说话打断")

    # 模拟TTS播放中的打断事件
    barge_in_event = CustomEvent(
        name="voice_barge_in",
        value={
            "reason": "vad_triggered",
            "audio_level": 0.72,
            "timestamp": time.strftime("%H:%M:%S"),
            "action": "stop_tts_and_listen",
        },
    )
    print(f"\n打断事件(CustomEvent):")
    print(f"  - name: {barge_in_event.name}")
    print(f"  - reason: {barge_in_event.value['reason']}")
    print(f"  - audio_level: {barge_in_event.value['audio_level']}")
    print(f"  - timestamp: {barge_in_event.value['timestamp']}")

    print("\n打断处理流程:")
    print("  1. 前端VAD检测到用户语音能量 > 阈值 → 发送barge_in信号")
    print("  2. 立即停止TTS音频播放（清空播放队列）")
    print("  3. 取消正在进行的TTS合成任务")
    print("  4. 向Agent发送打断信号（通过CustomEvent）")
    print("  5. 开始STT识别新的语音输入")
    print("  6. Agent处理新输入，生成新回复")

    # 模拟打断后的处理
    print("\n[系统] TTS播放已停止，开始聆听用户新输入...")
    await asyncio.sleep(0.2)
    print("[系统] VAD检测到语音结束，开始STT识别...")
    await asyncio.sleep(0.25)
    print("[STT] 识别结果: 医生你说的半片是多少毫克啊？")
    print("[Agent] AI医生调整回复，回答新问题...")
    print("[TTS] 合成新回复语音...")
    print("[系统] 打断处理完成，继续对话")


async def demo_audio_data_block_usage() -> None:
    """演示DataBlock在语音场景中的各种用法。"""
    print("\n" + "=" * 60)
    print("演示4：DataBlock多模态音频消息用法汇总")
    print("=" * 60)

    # 1. base64音频（最常用）
    audio_b64 = _make_mock_wav_base64("这是一段测试语音", speaker="elderly_female")
    msg1 = UserMsg(
        name="患者",
        content=[DataBlock(
            source=Base64Source(data=audio_b64, media_type="audio/wav"),
            name="voice.wav",
        )],
    )
    print(f"\n1. Base64音频消息: {len(msg1.content)}个DataBlock, media_type=audio/wav")

    # 2. 音频+文本混合（语音+文字确认）
    msg2 = UserMsg(
        name="患者",
        content=[
            DataBlock(
                source=Base64Source(data=audio_b64, media_type="audio/wav"),
                name="voice.wav",
            ),
            TextBlock(text="（语音转写）医生我头有点晕"),
        ],
    )
    print(f"2. 音频+文本混合消息: {len(msg2.content)}个blocks (DataBlock+TextBlock)")

    # 3. TTS返回音频（Assistant消息中的DataBlock）
    tts_audio_b64 = _make_mock_wav_base64("您好张奶奶，我是AI医生", speaker="doctor_female")
    msg3 = AssistantMsg(
        name="AI医生",
        content=[
            TextBlock(text="您好张奶奶，我是AI医生，有什么可以帮您的？"),
            DataBlock(
                source=Base64Source(data=tts_audio_b64, media_type="audio/wav"),
                name="reply_001.wav",
            ),
        ],
    )
    text_content = msg3.get_text_content()
    audio_blocks = msg3.get_content_blocks("data")
    print(f"3. TTS回复消息: 文本='{text_content[:20]}...', 音频block数={len(audio_blocks)}")

    # 4. 从消息中提取音频数据
    for block in msg3.content:
        if hasattr(block, "type") and block.type == "data":
            audio_data = base64.b64decode(block.source.data)
            print(f"4. 提取音频: {block.name}, {len(audio_data)}bytes WAV数据")

    print("\n支持的音频media_type:")
    print("  - audio/wav: WAV格式（推荐，DashScope TTS默认输出）")
    print("  - audio/mpeg: MP3格式")
    print("  - audio/pcm: 原始PCM（流式传输用）")
    print("  - audio/ogg: Ogg/Opus（WebSocket压缩传输）")


async def main() -> None:
    """主入口：运行所有语音对话演示。"""
    print("GerClaw 老年医疗AI平台 — 语音对话流程演示")
    print("AgentScope DataBlock/AudioMsg + STT + Agent + TTS 全链路示例")
    print("=" * 60)

    await demo_single_voice_message()
    await demo_voice_conversation()
    await demo_barge_in_mechanism()
    await demo_audio_data_block_usage()

    print(f"\n{'=' * 60}")
    print("所有语音对话演示完成！")
    print("\n关键要点回顾:")
    print("  1. AgentScope中无独立AudioMsg，使用DataBlock+Base64Source承载音频")
    print("  2. STT通过自定义FunctionTool包装Paraformer/FunASR API实现")
    print("  3. TTS可使用内置DashScopeTTSModel+TTSMiddleware自动语音化")
    print("  4. 也可通过FunctionTool让Agent主动调用TTS进行语音播报")
    print("  5. 语音打断通过CustomEvent+Middleware实现")
    print("  6. 老年场景：语速0.75-0.85x、音量+20%、医疗热词增强、关键信息重复")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
