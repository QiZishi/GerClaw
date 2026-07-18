# 11. 语音交互 TTS/STT — AgentScope 开发参考索引

> **模块定位**：为 GerClaw 老年医疗 AI 平台提供语音输入（STT/ASR）与语音输出（TTS）能力。覆盖老年人口语识别、慢速 TTS、方言支持、实时对话打断等适老化场景。
> **AgentScope 版本**：v2.0.3 (commit 3467754)
> **最后更新**：2026-07-02

---

## 1. 模块映射总览

### 1.1 GerClaw 需求 → AgentScope 能力映射

| GerClaw 需求 | AgentScope 能力 | 实现方式 | 备注 |
|---|---|---|---|
| 语音合成 TTS（慢速/老年友好） | 内置 `TTSModelBase` + `DashScopeTTSModel` | 直接使用内置 TTS 模型 | 支持 qwen3-tts-flash、CosyVoice 系列；通过 TTSMiddleware 自动将回复文本转语音 |
| 实时流式 TTS（边说边播） | `DashScopeRealtimeTTSModel` / `DashScopeCosyVoiceRealtimeTTSModel` | realtime TTS + push/synthesize 双模式 | 首包延迟低至 97ms，满足实时对话 TTFT < 500ms |
| 语音识别 STT/ASR（老年口语/方言） | **无内置 STT** | 自定义 `FunctionTool` 包装 DashScope Paraformer API 或 FunASR 服务 | 需自行集成第三方 STT 服务 |
| 多模态音频消息 | `DataBlock` + `Base64Source`/`URLSource` | 在 Msg 中通过 DataBlock 携带 audio/wav 或 audio/mpeg 数据 | user 角色可发送 DataBlock，assistant 可输出 DataBlock |
| 流式音频 chunk 处理 | `DataBlockStart/Delta/EndEvent` 事件流 | TTSMiddleware 将 TTS 音频注入事件流；STT 侧自行处理音频 chunk | DataBlockDeltaEvent.data 为 base64 增量 PCM/WAV |
| 语音打断（Barge-in） | 事件机制 + `CustomEvent` | 通过 CustomEvent 传递打断信号，在 on_reply 中间件中处理中断 | 需配合前端 VAD + AEC 实现 |
| TTS 自动语音输出 | `TTSMiddleware` | 作为 middleware 注册到 Agent，自动监听 TextBlockEndEvent 并合成语音 | 支持非实时和实时两种模式 |
| 音频预处理/后处理 | `MiddlewareBase.on_reply` / `on_acting` 钩子 | 自定义中间件实现降噪、音量调整、语速变换等预处理 | 可在 on_reply 中拦截 DataBlock 做音频变换 |
| 老年方言/热词支持 | STT Tool 参数 + 热词表 | STT Tool 接收 hotwords、dialect 参数；TTS 使用 voice 参数选择方言音色 | CosyVoice 支持四川话等方言 |

### 1.2 核心架构图

```
[老年用户语音输入]
       │
       ▼
[前端: 麦克风+AEC+VAD] ──WebSocket Opus──► [语音网关]
                                              │
                                    STT Tool (FunctionTool)
                                    调用 DashScope Paraformer/FunASR
                                              │
                                              ▼
                                    文字文本 (str)
                                              │
                                              ▼
                          ┌─── UserMsg(content=[TextBlock]) ───┐
                          │                                     │
                          ▼                                     │
              [Agent.reply()]                                   │
              医疗推理 + 工具调用                                 │
                          │                                     │
                          ▼                                     │
              回复文本 (TextBlock)                               │
                          │                                     │
              ┌───────────┼───────────┐                         │
              ▼           ▼           ▼                         │
        TTSMiddleware  (其他中间件)  直接文本回复                 │
              │                                                 │
              ▼                                                 │
      DashScopeTTSModel /                                        │
      DashScopeRealtimeTTSModel                                  │
              │                                                 │
              ▼                                                 │
      DataBlock(audio/wav) ◄────────────────────────────────────┘
              │
              ▼
      DataBlockStart/Delta/End Event 流
              │
              ▼
[前端: Opus解码+播放+音量放大+文字同步显示]
```

### 1.3 关键类型速查

```python
# 音频消息
from agentscope.message import DataBlock, Base64Source, URLSource
audio_block = DataBlock(
    source=Base64Source(data=base64_audio, media_type="audio/wav"),
    name="elderly_voice_input.wav",
)

# 内置 TTS
from agentscope.tts import (
    TTSModelBase, TTSResponse, TTSUsage,
    DashScopeTTSModel, DashScopeRealtimeTTSModel,
    DashScopeCosyVoiceRealtimeTTSModel,
)

# TTS 中间件
from agentscope.middleware import TTSMiddleware

# 自定义工具（用于 STT）
from agentscope.tool import FunctionTool, ToolBase, Toolkit, ParamsBase, ToolChunk
```

---

## 2. 核心 API 参考

### 2.1 多模态消息 AudioMsg/VoiceMsg 使用

AgentScope 2.0.3 中**没有独立的 AudioMsg/VoiceMsg 类型**。音频数据通过通用的 `DataBlock` 承载，`media_type` 标识音频格式。

#### DataBlock 音频消息构造

```python
import base64
from agentscope.message import Msg, UserMsg, AssistantMsg, DataBlock, Base64Source, TextBlock

# 方式一：用户发送音频（base64 编码的 WAV/PCM）
with open("voice_input.wav", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode("ascii")

voice_msg = UserMsg(
    name="elderly_patient",
    content=[
        DataBlock(
            source=Base64Source(data=audio_b64, media_type="audio/wav"),
            name="patient_question.wav",
        ),
        # 可选：附带转写文本（如有前端预识别）
        TextBlock(text="医生，我那个降压药怎么吃来着？"),
    ],
)

# 方式二：通过 URL 引用音频
voice_msg_url = UserMsg(
    name="elderly_patient",
    content=[
        DataBlock(
            source=URLSource(
                url="https://example.com/audio/patient_001.wav",
                media_type="audio/wav",
            ),
            name="patient_question.wav",
        ),
    ],
)

# 方式三：Assistant 回复包含音频（TTS 合成结果）
from agentscope.message import ToolResultBlock
# TTSMiddleware 会自动注入 DataBlock 到 assistant 消息中
```

#### 支持的音频 MIME 类型

| media_type | 说明 | 使用场景 |
|---|---|---|
| `audio/wav` | WAV 格式（PCM 封装） | DashScope TTS 默认输出，推荐使用 |
| `audio/mpeg` | MP3 格式 | Edge TTS 等输出 |
| `audio/pcm` | 原始 PCM 数据 | 流式传输，需配合 sample_rate/channels 元数据 |
| `audio/ogg` | Ogg/Opus 格式 | WebSocket 传输压缩格式 |

#### 音频消息在 Agent 事件流中的表现

音频 DataBlock 在流式事件中通过三个事件传递：

```python
from agentscope.event import (
    DataBlockStartEvent, DataBlockDeltaEvent, DataBlockEndEvent,
)
# DataBlockStartEvent:  音频块开始，携带 block_id 和 media_type
# DataBlockDeltaEvent:  音频增量数据，data 为 base64 编码的增量 chunk
# DataBlockEndEvent:    音频块结束
```

注意：`DataBlockDeltaEvent.data` 是**独立编码的增量 chunk**（不是累积 buffer），需要 decode 后 concat 再 re-encode 才能得到完整音频。

### 2.2 自定义 Tool 实现 TTS 集成（DashScope CosyVoice/Sambert）

虽然 AgentScope 内置了 `DashScopeTTSModel`，但在 GerClaw 场景中，如需通过 Tool 方式让 Agent 自主决定是否进行语音合成（如关键信息重复播报、慢速重说），可以将 TTS 包装为 FunctionTool。

#### 方式一：直接使用内置 TTSModel（推荐用于自动语音回复）

```python
from agentscope.credential import DashScopeCredential
from agentscope.tts import DashScopeTTSModel
from agentscope.middleware import TTSMiddleware

# 初始化 TTS 模型
tts_model = DashScopeTTSModel(
    credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
    model="qwen3-tts-flash",
    parameters=DashScopeTTSModel.Parameters(
        voice="Cherry",  # 可选音色: Cherry, Serena, Ethan 等
    ),
    stream=True,
)

# 通过中间件自动将所有文本回复转为语音
agent = Agent(
    name="gerclaw_doctor",
    model=chat_model,
    middlewares=[TTSMiddleware(tts_model=tts_model)],
    ...
)
```

#### 方式二：将 TTS 包装为 FunctionTool（用于 Agent 主动控制语音输出）

```python
import asyncio
from agentscope.tool import FunctionTool
from agentscope.message import TextBlock, DataBlock, Base64Source
from agentscope.tts import TTSModelBase

async def text_to_speech(
    text: str,
    speed: float = 0.85,
    volume_gain: float = 1.2,
    voice: str = "Cherry",
) -> str:
    """将文本合成为语音，适用于老年医疗场景的语音播报。

    Args:
        text: 要合成的文本内容（医学建议、用药指导等）
        speed: 语速倍率，老年场景建议0.7-0.9（默认0.85慢速）
        volume_gain: 音量增益，老年听力下降建议1.2-1.5（默认1.2）
        voice: 音色选择，支持Cherry(女声清晰)/Ethan(男声沉稳)/Serena(女声温柔)
    """
    # 实际实现调用 DashScope TTS API 或 CosyVoice
    # 此处为接口示意
    return f"[TTS_AUDIO] voice={voice}, speed={speed}, volume={volume_gain}, text_len={len(text)}"

tts_tool = FunctionTool(
    func=text_to_speech,
    name="text_to_speech",
    is_read_only=True,
    is_concurrency_safe=True,
)
```

#### TTSModelBase 核心方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `synthesize` | `async def synthesize(text, **kwargs) -> TTSResponse \| AsyncGenerator[TTSResponse, None]` | 合成语音；stream=True 返回 async generator，每个 chunk 为增量音频 |
| `connect` | `async def connect() -> None` | 连接实时 TTS（仅 realtime=True） |
| `close` | `async def close() -> None` | 关闭连接（仅 realtime=True） |
| `push` | `async def push(text, **kwargs) -> TTSResponse` | 追加文本块到实时 TTS，非阻塞 |
| `list_models` | `@classmethod def list_models(custom_yaml_dir=None) -> list[TTSModelCard]` | 列出可用 TTS 模型 |

#### TTSResponse 结构

```python
@dataclass
class TTSResponse:
    content: DataBlock | None    # 音频数据块（Base64Source，media_type="audio/wav"）
    is_last: bool = True         # 流式中是否为最后一块
    id: str                      # 响应ID
    usage: TTSUsage | None       # 用量统计
    metadata: dict | None        # 元数据
```

#### DashScope TTS 可用模型

| 模型名 | 类型 | 说明 | 流式 | 实时 |
|---|---|---|---|---|
| `qwen3-tts-flash` | 非实时 | Qwen3-TTS Flash 版，快速合成 | 是 | 否 |
| `qwen3-tts-flash-realtime` | 实时 | Qwen3-TTS 实时版，首包~97ms | 是 | 是 |
| `cosyvoice-v3-plus` | 非实时 | CosyVoice v3 Plus，3秒音色克隆 | 是 | 否 |
| `cosyvoice-v3-flash` | 非实时 | CosyVoice v3 Flash | 是 | 否 |

老年场景推荐音色：`Cherry`（女声清晰）、`Ethan`（男声沉稳），语速通过 TTS 中间件或前端播放控制设置 0.8-0.85x。

### 2.3 自定义 Tool 实现 STT 集成（DashScope Paraformer）

AgentScope 2.0.3 **没有内置 STT/ASR 模块**，需要通过自定义 Tool 集成。推荐使用 DashScope Paraformer（语音识别 API）或自部署 FunASR。

#### FunctionTool 包装 STT 函数

```python
import asyncio
import base64
from typing import Optional
from agentscope.tool import FunctionTool
from agentscope.message import TextBlock

async def speech_to_text(
    audio_base64: str,
    audio_format: str = "wav",
    sample_rate: int = 16000,
    language: str = "zh",
    dialect: str = "auto",
    enable_hotwords: bool = True,
    hotwords: Optional[str] = None,
) -> str:
    """将语音音频识别为文字，专门优化老年人口语识别场景。

    支持方言识别、医疗热词增强、慢速口语识别。适用于将老年患者的语音输入
    转换为文本供AI医生分析。

    Args:
        audio_base64: base64编码的音频数据
        audio_format: 音频格式，支持wav/pcm/mp3/opus
        sample_rate: 采样率，推荐16000Hz
        language: 语言，zh(中文)/en(英文)/auto(自动检测)
        dialect: 方言，auto(自动)/cantonese(粤语)/sichuanhua(四川话)/northeast(东北话)
        enable_hotwords: 是否启用医疗热词增强（药名、疾病名等）
        hotwords: 自定义热词，逗号分隔，如'阿托伐他汀,二甲双胍,氨氯地平'
    """
    # 实际实现调用 DashScope Paraformer API:
    # from dashscope.audio.asr import Recognition
    # recognition = Recognition(model='paraformer-realtime-v2', ...)
    # 此处返回 mock 结果
    return "医生，我那个降压药怎么吃来着？最近血压有点高。"

stt_tool = FunctionTool(
    func=speech_to_text,
    name="speech_to_text",
    is_read_only=True,
    is_concurrency_safe=True,
)
```

#### 继承 ToolBase 的 STT 工具（更精细控制）

```python
from pydantic import Field
from agentscope.tool import ToolBase, ParamsBase, ToolChunk
from agentscope.message import TextBlock
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision

class GerClawSTTTool(ToolBase):
    """老年医疗语音识别工具。

    集成DashScope Paraformer/FunASR，支持老年口语优化、方言识别、
    医疗热词增强和VAD静音检测。
    """

    name: str = "gerclaw_speech_to_text"
    description: str = (
        "将老年患者的语音输入识别为文字。支持方言（粤语/四川话/东北话）、"
        "医疗热词增强（药名/疾病名识别优化）、慢速口语识别。"
        "当收到音频数据时调用此工具进行语音转文字。"
    )

    class Params(ParamsBase):
        audio_data: str = Field(..., description="base64编码的音频数据")
        media_type: str = Field("audio/wav", description="音频MIME类型")
        dialect: str = Field("auto", description="方言: auto/cantonese/sichuanhua/northeast")
        enable_medical_hotwords: bool = Field(True, description="启用医疗热词增强")

    input_schema: dict = Params.model_json_schema()
    is_concurrency_safe: bool = True
    is_read_only: bool = True

    # 老年医疗热词表（5000词规模，此处展示示例）
    MEDICAL_HOTWORDS = [
        "阿托伐他汀", "氨氯地平", "二甲双胍", "阿司匹林",
        "降压药", "降糖药", "钙片", "胰岛素",
        "高血压", "糖尿病", "骨质疏松", "阿尔茨海默病",
    ]

    async def check_permissions(self, tool_input, context):
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="语音识别为只读操作，允许执行。",
        )

    async def call(self, **kwargs):
        params = self.Params(**kwargs)
        # 实际调用 DashScope Paraformer API
        # result = await self._call_paraformer(params.audio_data, params.dialect)
        result_text = "[STT识别结果] 医生您好，我想问问降压药怎么吃。"
        return ToolChunk(content=[TextBlock(text=result_text)])
```

### 2.4 流式音频 chunk 处理

实时语音对话中，音频以 chunk 方式流式传输和处理。

#### TTS 流式合成（增量音频 chunk）

```python
async def stream_tts_demo(tts_model: TTSModelBase, text: str):
    """演示流式TTS，逐chunk接收音频数据。"""
    audio_chunks = []
    async for response in tts_model.synthesize(text):
        if response.content is not None:
            chunk_data = response.content.source.data  # base64增量chunk
            audio_chunks.append(base64.b64decode(chunk_data))
            print(f"收到音频chunk: {len(audio_chunks[-1])} bytes, is_last={response.is_last}")

            # 前端可立即播放此chunk（无需等待完整音频）
            # play_audio_chunk(audio_chunks[-1])

    # 拼接完整音频
    full_audio = b"".join(audio_chunks)
    print(f"完整音频大小: {len(full_audio)} bytes")
    return full_audio
```

#### 实时 TTS（边生成文本边合成）

```python
async def realtime_tts_demo(realtime_model, text_parts: list[str]):
    """演示实时TTS：文本逐段push，音频边接收。"""
    async with realtime_model:  # connect
        for part in text_parts:
            # 每收到一段文本立即push，不等待完整句子
            response = await realtime_model.push(part)
            if response.content is not None:
                # 立即播放已合成的音频
                play_chunk(response.content.source.data)

        # 所有文本push完成，drain剩余音频
        final_response = await realtime_model.synthesize()
        # final_response 包含最后的音频数据
```

#### STT 流式识别

```python
async def stream_stt_demo(audio_chunks: list[bytes]):
    """演示流式STT：边接收音频边识别。"""
    # 实际使用 DashScope Recognition 流式接口
    # 或 FunASR WebSocket 流式接口
    partial_results = []
    for chunk in audio_chunks:
        # 发送音频chunk到ASR服务
        # partial = await asr.send_audio_chunk(chunk)
        # partial_results.append(partial)
        pass
    # final_result = await asr.get_final_result()
```

### 2.5 语音打断机制通过事件处理

语音打断（Barge-in）是指 TTS 正在播放时，用户开始说话，系统立即停止播放并处理新输入。AgentScope 中通过 `CustomEvent` + 中间件实现。

#### 使用 CustomEvent 传递打断信号

```python
from agentscope.event import CustomEvent

# 前端检测到用户开始说话（VAD触发），发送打断事件
barge_in_event = CustomEvent(
    name="voice_barge_in",
    value={
        "reason": "user_started_speaking",
        "timestamp": "2026-07-02T10:30:00",
        "audio_level": 0.75,  # 音量阈值触发
    },
)
```

#### 打断处理中间件

```python
from agentscope.middleware import MiddlewareBase
from typing import AsyncGenerator, Callable, Any

class BargeInMiddleware(MiddlewareBase):
    """语音打断中间件：检测到用户打断时停止TTS播放和LLM生成。"""

    def __init__(self):
        self._barge_in_requested = False

    def request_barge_in(self):
        """前端VAD检测到用户说话时调用此方法。"""
        self._barge_in_requested = True

    async def on_reply(
        self,
        agent,
        input_kwargs,
        next_handler,
    ) -> AsyncGenerator:
        self._barge_in_requested = False

        async for evt in next_handler(**input_kwargs):
            # 检查是否收到打断信号
            if self._barge_in_requested:
                # 停止TTS播放（通过CustomEvent通知前端）
                yield CustomEvent(
                    name="tts_stop",
                    value={"reason": "barge_in"},
                )
                self._barge_in_requested = False
                break  # 终止当前reply

            yield evt
```

打断检测策略（前端实现）：
1. **能量阈值**：用户语音能量 > TTS 回声能量的 2 倍（需 AEC 回声消除）
2. **VAD 持续检测**：检测到 > 200ms 连续语音
3. **关键词触发**："停"、"等等"、"别说了"等打断词

### 2.6 ToolMiddlewareBase 音频预处理

通过自定义中间件在音频数据进入 STT 之前进行预处理（降噪、音量归一化、VAD 裁剪等）。

```python
from agentscope.middleware import MiddlewareBase

class AudioPreprocessingMiddleware(MiddlewareBase):
    """音频预处理中间件：对用户发送的音频DataBlock进行预处理。

    处理步骤：
    1. 音量归一化（老年用户音量可能偏小，自动增益到目标dB）
    2. 降噪处理（WebRTC NS 或 RNNoise）
    3. VAD裁剪（去除首尾静音段）
    4. 格式转换（统一为16kHz/16bit/mono PCM）
    """

    def __init__(
        self,
        target_db: float = -20.0,    # 目标音量(dB)
        enable_noise_suppression: bool = True,
        enable_vad_trimming: bool = True,
        sample_rate: int = 16000,
    ):
        self.target_db = target_db
        self.enable_ns = enable_noise_suppression
        self.enable_vad = enable_vad_trimming
        self.sample_rate = sample_rate

    async def on_reply(
        self,
        agent,
        input_kwargs,
        next_handler,
    ) -> AsyncGenerator:
        # 在输入消息中查找音频DataBlock并预处理
        inputs = input_kwargs.get("inputs")
        if inputs is not None:
            self._preprocess_audio_inputs(inputs)

        async for evt in next_handler(**input_kwargs):
            yield evt

    def _preprocess_audio_inputs(self, inputs):
        """预处理输入消息中的音频数据。"""
        msgs = inputs if isinstance(inputs, list) else [inputs]
        for msg in msgs:
            if not hasattr(msg, "content"):
                continue
            for block in msg.content:
                if (hasattr(block, "type") and block.type == "data"
                        and hasattr(block, "source")
                        and "audio" in block.source.media_type):
                    # 执行预处理链：解码→降噪→AGC→VAD裁剪→重编码
                    audio_bytes = base64.b64decode(block.source.data)
                    processed = self._process_audio(audio_bytes)
                    block.source.data = base64.b64encode(processed).decode("ascii")

    def _process_audio(self, audio_bytes: bytes) -> bytes:
        """音频处理链（mock实现，实际使用pydub/soundfile/librosa等库）。"""
        # 1. 解码WAV/PCM
        # 2. AGC自动增益控制到target_db
        # 3. 降噪处理
        # 4. VAD裁剪首尾静音
        # 5. 重采样到目标sample_rate
        return audio_bytes  # mock: 返回原始数据
```

---

## 3. 源码路径索引

### 3.1 TTS 模块

| 文件路径（相对于 `src/agentscope/`） | 说明 |
|---|---|
| `tts/__init__.py` | TTS 模块公开 API 导出 |
| `tts/_tts_base.py` | `TTSModelBase` 抽象基类，定义 synthesize/connect/close/push 接口 |
| `tts/_tts_model_card.py` | `TTSModelCard` 模型卡片定义 |
| `tts/_tts_response.py` | `TTSResponse`、`TTSUsage` 数据类 |
| `tts/_dashscope/__init__.py` | DashScope TTS 实现导出 |
| `tts/_dashscope/_model.py` | `DashScopeTTSModel` 标准 TTS（非实时），基于 MultiModalConversation API |
| `tts/_dashscope/_realtime_model.py` | `DashScopeRealtimeTTSModel` 实时 TTS（WebSocket 流式输入） |
| `tts/_dashscope/_cosyvoice_realtime_model.py` | `DashScopeCosyVoiceRealtimeTTSModel` CosyVoice 实时 TTS |
| `tts/_dashscope/_models/` | 标准 TTS YAML 模型卡片（qwen3-tts-flash 等） |
| `tts/_dashscope/_cosyvoice_models/` | CosyVoice YAML 模型卡片（cosyvoice-v3-plus/flash） |

### 3.2 消息模块（音频相关）

| 文件路径 | 说明 |
|---|---|
| `message/__init__.py` | 消息模块公开 API |
| `message/_base.py` | `Msg`、`UserMsg`、`AssistantMsg`、`SystemMsg` 定义 |
| `message/_block.py` | `DataBlock`、`Base64Source`、`URLSource`（承载音频数据的多模态块） |

### 3.3 中间件（TTS/音频相关）

| 文件路径 | 说明 |
|---|---|
| `middleware/__init__.py` | 中间件公开 API |
| `middleware/_base.py` | `MiddlewareBase` 基类，定义 5 个 hook 点 |
| `middleware/_tts_middleware.py` | `TTSMiddleware`，自动将 TextBlock 合成语音并注入 DataBlock 事件 |

### 3.4 工具模块（用于 STT 自定义 Tool）

| 文件路径 | 说明 |
|---|---|
| `tool/__init__.py` | 工具模块公开 API |
| `tool/_base.py` | `ToolBase`、`ParamsBase`、`ToolChunk` 基类 |
| `tool/_adapters.py` | `FunctionTool` 适配器，将普通 Python 函数包装为 Tool |

### 3.5 事件模块

| 文件路径 | 说明 |
|---|---|
| `event/__init__.py` | 事件模块公开 API |
| `event/_event.py` | 所有事件类定义，包括 `DataBlockStart/Delta/EndEvent`、`CustomEvent` |

### 3.6 音频工具

| 文件路径 | 说明 |
|---|---|
| `_utils/_audio.py` | `_build_streaming_wav_header()` 构建流式 WAV 头（44字节 RIFF 头，用于 PCM 流） |

### 3.7 测试文件（相对于 `references/agentscope/tests/`）

| 文件路径 | 说明 |
|---|---|
| `tests/tts_dashscope_test.py` | DashScope TTS 单元测试（非流式聚合、流式增量 delta、realtime WebSocket mock） |
| `tests/tts_middleware_test.py` | TTSMiddleware 测试 |
| `tests/message_test.py` | Msg/DataBlock 序列化测试 |

### 3.8 服务层（TTS 相关）

| 文件路径 | 说明 |
|---|---|
| `app/_service/_tts_model.py` | TTS 模型服务层管理 |
| `app/_router/_tts_model.py` | TTS 模型 HTTP 路由 |
| `app/_router/_schema/_tts_model.py` | TTS 路由 schema |

---

## 4. 官方示例参考

### 4.1 内置 TTS 使用示例

| 示例位置 | 说明 |
|---|---|
| `tests/tts_dashscope_test.py` | TTS 模型完整测试，涵盖非流式/流式/realtime 三种模式，使用 mock API 演示 synthesize/push/connect 流程 |
| `tests/tts_middleware_test.py` | TTSMiddleware 测试，展示如何在 Agent 回复流中自动注入音频 DataBlock |
| `scripts/model_examples/` | 模型调用示例目录 |

### 4.2 TTSMiddleware 核心用法（源码参考）

```python
# 来源: middleware/_tts_middleware.py
# TTSMiddleware 在 on_reply hook 中：
# 1. 监听 TextBlockDeltaEvent（实时模式）：每个 delta 立即 push 到 TTS
# 2. 监听 TextBlockEndEvent：
#    - 实时模式：调用 synthesize() drain 剩余音频
#    - 非实时模式：调用 synthesize(text) 合成完整文本
# 3. 将 TTSResponse 转换为 DataBlockStart/Delta/End 事件注入流
```

### 4.3 DashScope TTS 非流式模式测试参考

```python
# 来源: tests/tts_dashscope_test.py
# _DummyTTS 最小实现演示：只需实现 synthesize 方法
class _DummyTTS(TTSModelBase):
    async def synthesize(self, text=None, **kwargs):
        return TTSResponse(content=DataBlock(
            source=Base64Source(data=base64.b64encode(b"fake_audio"), media_type="audio/wav")
        ))
```

---

## 5. 文档链接

### 5.1 AgentScope 官方文档

| 文档主题 | 链接/位置 |
|---|---|
| AgentScope GitHub | https://github.com/modelscope/agentscope |
| TTS 模型文档 | https://agentscope.io （模型/TTS 章节） |
| DashScope TTS API 文档 | https://bailian.console.aliyun.com/?tab=doc#/doc/?type=model&url=2879134 |
| 多模态消息（DataBlock） | `source_map_core.md` 第 2.6 节 DataBlock |
| 中间件系统 | `source_map_core.md` 第 1.2 节 + `middleware/_base.py` |

### 5.2 DashScope 语音服务文档

| 服务 | 文档链接 |
|---|---|
| Paraformer 语音识别 | https://help.aliyun.com/zh/dashscope/paraformer-realtime-v2 |
| CosyVoice 语音合成 | https://help.aliyun.com/zh/dashscope/cosyvoice-v1 |
| Qwen3-TTS | https://bailian.console.aliyun.com/ 模型广场 qwen3-tts |
| Sambert 语音合成 | https://help.aliyun.com/zh/dashscope/sambert |

### 5.3 第三方语音服务

| 服务 | 链接 |
|---|---|
| FunASR (阿里开源ASR) | https://github.com/modelscope/FunASR |
| CosyVoice2 (开源TTS) | https://github.com/FunAudioLLM/CosyVoice |
| Qwen3-TTS (开源TTS) | https://github.com/QwenLM/Qwen3-TTS |
| Qwen3-ASR (开源ASR) | https://github.com/QwenLM/Qwen3-ASR |
| Silero VAD (语音活动检测) | https://github.com/snakers4/silero-vad |

---

## 6. GerClaw 适配要点

### 6.1 老年语音优化

#### 6.1.1 语速控制

- **TTS 语速**：默认 **0.85x**（约 200 字/分钟），比标准语速慢 15%
- **医学建议/用药指导**：语速降至 **0.75x**，确保老年用户听清楚
- **语速调节选项**：提供 0.7x/0.85x/1.0x 三档，用户可自行切换
- **实现方式**：TTS 模型参数（部分模型支持 speed_ratio）或前端 Web Audio API `playbackRate` 控制

#### 6.1.2 音量提升

- 默认输出音量比标准高 **20% (+3dB)**
- 提供音量放大选项（最大 +10dB）
- 自动增益控制（AGC），避免突发大声惊吓老人
- 实现方式：TTSMiddleware 后处理音频数据做增益，或前端 Web Audio API GainNode

#### 6.1.3 方言词汇表

- **STT 热词增强**：构建老年常见病医学术语热词表（2000-5000 词），包含：
  - 药品通用名和商品名（阿托伐他汀钙片、氨氯地平、二甲双胍等）
  - 疾病名（阿尔茨海默病、骨质疏松症、高血压、糖尿病）
  - 老年人常用俗称（"降压药"、"钙片"、"降糖片"）
  - 用药剂量表达（"吃两片"、"半粒"、"饭后一次"）
- **方言支持优先级**：
  - 第一梯队：普通话（带口音）、粤语、四川话、东北话
  - 第二梯队：吴语、闽南语、湖南话、河南话
- **实现方式**：STT Tool 的 hotwords 参数 + dialect 参数；Qwen3-ASR 原生支持 52 种语种/方言

#### 6.1.4 VAD 参数调优（老年人口语特点）

```python
# Silero VAD 推荐参数（中文老年场景）
vad_params = {
    "trig_sum": 0.30,           # 触发阈值（老年人语速慢，略高防噪声误触发）
    "neg_trig_sum": 0.10,       # 结束阈值（老年人停顿多，略高防截断）
    "min_silence_samples": 800, # 最小静音~50ms(16kHz)
    "min_speech_samples": 2048, # 最小语音片段~128ms，过滤咳嗽/噪声
    "speech_pad_samples": 1024, # 语音前后padding~64ms
}
# 后端点静音判定：老年人 800-1200ms（年轻人 300-500ms）
```

### 6.2 推荐配置

#### 6.2.1 核心架构：自定义 TTSTool + STTTool + AudioMsg

```python
# GerClaw 语音交互推荐配置
from agentscope.credential import DashScopeCredential
from agentscope.model import DashScopeChatModel
from agentscope.tts import DashScopeTTSModel
from agentscope.middleware import TTSMiddleware
from agentscope.tool import FunctionTool, Toolkit
from agentscope.agent import Agent

# 1. STT Tool（自定义FunctionTool包装DashScope Paraformer）
stt_tool = FunctionTool(func=speech_to_text, name="speech_to_text", ...)

# 2. TTS 模型（内置DashScopeTTSModel）
tts_model = DashScopeTTSModel(
    credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
    model="qwen3-tts-flash",
    parameters=DashScopeTTSModel.Parameters(voice="Cherry"),
    stream=True,
)

# 3. TTS 中间件（自动将文本回复转为语音）
tts_middleware = TTSMiddleware(tts_model=tts_model)

# 4. 音频预处理中间件
audio_middleware = AudioPreprocessingMiddleware(target_db=-20.0)

# 5. 注册工具和中间件
toolkit = Toolkit(tools=[stt_tool])
agent = Agent(
    name="gerclaw_voice_doctor",
    model=DashScopeChatModel(...),
    toolkit=toolkit,
    middlewares=[audio_middleware, tts_middleware],
    system_prompt="你是GerClaw老年医疗AI医生，说话要慢、清晰、简洁...",
)
```

#### 6.2.2 MVP 阶段推荐方案

| 组件 | 方案 | 理由 |
|---|---|---|
| STT | DashScope Paraformer API（云端） | 接入快、中文医疗识别率高、支持热词 |
| TTS | DashScope qwen3-tts-flash（云端）+ TTSMiddleware | AgentScope 原生支持、流式合成、音质好 |
| VAD | Silero VAD（前端/服务端） | 轻量快速、中文参数可调优 |
| 传输 | WebSocket + Opus | 低延迟、浏览器原生支持 |
| 部署 | 混合方案（ASR/TTS云端 + LLM云端） | MVP阶段快速验证 |

#### 6.2.3 规模化阶段推荐方案

| 组件 | 方案 | 理由 |
|---|---|---|
| STT | FunASR Paraformer-large（自部署）+ Qwen3-ASR（方言增强） | 零调用费、数据不出域、医疗隐私合规 |
| TTS | Qwen3-TTS-0.6B（自部署）+ CosyVoice2（音色克隆） | 97ms首包、4GB显存可部署、Apache 2.0 |
| VAD | Silero VAD（自部署） | <1ms延迟 |
| 部署 | 全私有化（GPU服务器 RTX 4090） | 数据安全、长期成本低 |

### 6.3 风险与注意事项

#### 6.3.1 长音频超时

- **风险**：老年用户说话可能持续较长时间（叙述病史、描述症状），超过 STT API 的单次音频长度限制
- **应对策略**：
  - 实现 VAD 分段，将长语音按静音段切分为多个短音频段（每段 < 30秒）
  - 使用流式 STT API，边说边识别，无需等待完整音频
  - 设置最大录音时长（如 60 秒），超时提示用户"您说的有点长，能再说一遍吗？"
  - STT Tool 中实现音频长度检测和自动分段逻辑

#### 6.3.2 噪音环境识别不准

- **风险**：老年用户可能在嘈杂的家庭环境中使用（电视声、家人交谈、厨房噪音等），导致 STT 识别率下降
- **应对策略**：
  - 前端启用 WebRTC 内置 AEC/AGC/ANS（`getUserMedia` 参数 `echoCancellation: true, noiseSuppression: true`）
  - 服务端使用 RNNoise 或 DeepFilterNet 做二次降噪
  - 识别置信度低时（< 0.8），自动要求用户重复或切换文字输入
  - 关键医学信息（药名、剂量）必须通过语音+文字双重确认
  - 构建噪声环境下的老年语音测试集，持续优化模型

#### 6.3.3 其他风险

| 风险 | 影响 | 应对策略 |
|---|---|---|
| 方言识别不准确 | 误判用户意图 | 方言自动检测 + 多模型路由 + 关键信息确认 |
| TTS 医学术语发音不准 | 老人误解用药指导 | 使用医疗热词表 + 术语逐字发音模式 + 文字同步显示 |
| 打断误触发 | 正常对话被打断 | VAD 参数保守设置 + 打断词确认 + 打断灵敏度可调 |
| API 调用延迟 | 对话不流畅 | 连接预热 + 边缘节点部署 + 流式全链路 |
| 隐私合规风险 | 医疗语音数据泄露 | 私有化部署 + 音频数据不存储 + 传输加密 |
| 老年人误唤醒 | 非对话时被激活 | 按键说话模式优先 + 唤醒词需2次确认 |

---

## 7. 可运行示例指引

### 7.1 示例文件列表

| 示例文件 | 路径 | 说明 |
|---|---|---|
| TTS/STT 自定义工具示例 | `agentscope-examples/11_voice/tts_stt_tools.py` | 演示 FunctionTool 包装 TTS/STT 函数，Agent 可调用语音合成和识别工具 |
| 语音对话流程演示 | `agentscope-examples/11_voice/voice_conversation_demo.py` | 演示完整语音对话流程：语音输入→STT→Agent→TTS→语音输出，使用 AudioMsg/DataBlock |

### 7.2 运行前准备

```bash
# 安装 AgentScope（如未安装）
pip install agentscope

# 设置 API Key（如需真实模型调用，示例中 mock 模式无需 key）
export DASHSCOPE_API_KEY="your-dashscope-api-key"
```

### 7.3 运行示例

```bash
# 示例1：TTS/STT 工具演示（mock 模式，无需 API Key 即可运行）
cd agentscope-examples/11_voice
python tts_stt_tools.py

# 示例2：语音对话流程演示（mock 模式，无需 API Key 即可运行）
python voice_conversation_demo.py
```

### 7.4 示例学习路径

1. **先运行 `tts_stt_tools.py`**：理解如何将 TTS/STT 包装为 FunctionTool，如何通过 Toolkit 注册工具，如何在 Agent 对话中自动调用语音工具
2. **再运行 `voice_conversation_demo.py`**：理解完整语音对话流程，包括 DataBlock 音频消息构造、STT 转文字、Agent 处理、TTS 转语音输出的全链路
3. **对照源码阅读**：结合 `references/agentscope/src/agentscope/middleware/_tts_middleware.py` 理解 TTSMiddleware 如何自动将文本转语音
4. **扩展实践**：
   - 将 mock STT 替换为真实 DashScope Paraformer API 调用
   - 将 mock TTS 替换为真实 DashScopeTTSModel 调用
   - 添加音频预处理中间件（降噪/AGC/VAD）
   - 实现 Barge-in 打断机制
   - 接入 WebSocket 实现实时流式语音对话
