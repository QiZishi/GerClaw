<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/context/overview -->

# 概述

上下文是智能体的工作记忆：大模型在每一步推理时看到的全部消息（用户输入、智能体回复、工具调用、工具结果）。上下文管理的意义不只是让内容不超过模型的上下文窗口，而是通过塑造模型每一步看到的内容，让智能体更好地完成任务。它包含三种机制：

| 机制 | 作用 | 页面 |
| --- | --- | --- |
| **上下文注入** | 把随对话变化的运行时状态（时间、任务、上下文用量）以提示形式注入上下文，让智能体持续感知环境 | [感知环境](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/context/environment-awareness) |
| **上下文压缩** | 把较早的消息汇总成摘要、截断过大的工具结果，让长对话保持在模型窗口之内 | [压缩上下文](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/context/compress-context) |
| **上下文卸载** | 把被移除的内容（压缩的消息、截断的工具结果）持久化到外部存储，细节仍可随时找回 | [卸载上下文](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/context/offload-context) |

三种机制相互配合：注入补充模型当下需要知道的信息，压缩移除不再需要逐字保留的内容，卸载让被移除的内容只需一次文件读取即可找回。

## 组装上下文

每次模型调用前，智能体会把三层内容拼成单次 API 输入。下图展示这次调用所包含的结构：

模型 API 输入

系统提示

基础系统提示

技能指令（来自 Toolkit）

on_system_prompt 中间件转换

摘要（已压缩历史，若存在）

上下文（最近未压缩消息）

每一层的构成方式：

1. 系统提示 system_prompt on_system_prompt 中间件
2. 摘要
3. 上下文

> **提示** 固定信息应放在系统提示中（可通过 `on_system_prompt` 中间件钩子动态组装）；会话中会变化的信息应以提示形式注入上下文。两者的区分参见[感知环境](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/context/environment-awareness)。

## 延伸阅读

## 感知环境

注入时间、任务与上下文用量，让智能体保持方向感。

## 压缩上下文

将上下文长度维护在预设的长度内。

## 卸载上下文

持久化被移除的内容，供智能体按需回查。

## 工作区

内置的卸载实现，以及智能体的工作环境。
