# 0007 Trae Work过程可视化与体验对齐 - Product Requirement Document

## Overview
- **Summary**: 重构GerClaw的AI回复过程可视化，对齐Trae Work的阶段式工作流展示。将思维链按步骤拆分为独立折叠卡片，搜索工具卡片可展开查看搜索结果链接，优化模型推理效率，完善多格式导出、单条消息删除等功能，修复光标闪烁等UI问题。
- **Purpose**: 当前系统把所有思维链放在一个卡片里、所有输出放在一个文本框里，缺乏Trae Work那样清晰的分阶段过程可视化（思考→搜索→查看结果→再思考→回答）。用户无法理解AI"在做什么"，体验不够专业和透明。
- **Target Users**: 老年患者（需要清晰易懂的过程反馈）、老年科医生（需要专业透明的推理过程追踪）

## Goals
- 实现Trae Work风格的分阶段过程可视化：每一步thinking→tool_call→tool_result→thinking→text按时间顺序从上到下排列，各自独立卡片
- 搜索工具卡片可展开，展示搜索到的资料标题+链接列表，点击链接可跳转原文
- "查看原文"按钮真实可用，点击在新标签页打开对应URL
- 优化系统提示语，减少冗余思维链输出，提高推理效率
- 移除回复末尾"|"字符闪烁光标，流式效果对齐思维链的文字呈现方式
- 多格式导出（MD/PDF/PNG/JPG/DOCX），支持选择导出范围（当前消息/全部对话/勾选指定消息）
- 每条消息支持删除，删除后不进入模型上下文
- 搜索工具完成后展示"已找到N个结果"并可展开查看结果列表
- 全量回归测试通过

## Non-Goals (Out of Scope)
- 不重构后端API架构（SSE协议保持不变）
- 不实现子智能体树可视化（二阶段AgentScope能力）
- 不实现PDF/DOCX的复杂排版（使用基础html2canvas/jsPDF/docx库）
- 不修改CGA评估和五大处方的核心业务逻辑
- 不实现消息编辑/撤回功能（仅删除）

## Background & Context
当前架构问题分析：
1. **client.ts**: `thinkingStarted/thinkingEnded`是全局变量，多轮工具调用中第一轮thinking结束后第二轮thinking不会重新触发`onThinkingStart`，所有thinking内容累积到一个thinking块中
2. **chatStore.ts**: `initMessageThinking`只创建一个thinking block，且用`hasThinking`检查防止重复创建，不支持多轮thinking block
3. **ChatArea.tsx**: 流式回调中`onToolCallStart`后没有重新启动新的thinking block的逻辑
4. **ToolCallBlock**: 搜索完成后不显示搜索结果列表，result数据虽然已存储但没有渲染
5. **CitationPopover**: "查看原文"按钮可能没有正确的链接跳转
6. **StreamingText**: 末尾typing-cursor始终显示，流式结束后不消失
7. **Export**: 仅支持Markdown导出，无格式选择和范围选择

Trae Work的关键体验特征：
- 每个ReAct循环（Thought→Action→Observation）独立展示为一个步骤
- Thinking块始终可折叠，每个工具调用前后都有独立的thinking
- 搜索工具调用完成后内联展示搜索结果列表（标题+URL+snippet），点击可跳转
- 最终回答在所有步骤完成后流式输出，末尾无光标闪烁
- 过程从上到下时间序排列，清晰展示AI"先思考→搜索→看结果→再思考→得出结论"的工作流

## Functional Requirements

- **FR-1**: 多轮thinking独立卡片 — LLM进行多轮思考（工具调用前后）时，每轮thinking都生成独立的折叠卡片，按时间序排列
- **FR-2**: 分阶段过程可视化 — 消息内blocks按执行顺序排列：[thinking1]→[tool_call1+搜索结果]→[thinking2]→[text最终回答]，从上到下清晰展示
- **FR-3**: 搜索卡片可展开结果 — web_search工具调用完成后，卡片显示"已找到N个结果"，点击展开显示搜索结果列表（标题可点击跳转URL、来源、snippet摘要）
- **FR-4**: 引用链接真实跳转 — CitationPopover中"查看原文"按钮点击后在新标签页（target=_blank）打开对应url
- **FR-5**: 系统提示语优化 — 在三个system prompt中添加"思考要简洁高效，不要输出冗长的思维链。先快速判断是否需要搜索，需要则直接调用工具，不需要则直接回答。"减少不必要的长thinking
- **FR-6**: 移除末尾光标 — StreamingText在streaming=false时不显示typing-cursor，streaming=true时在文本末尾显示柔和光标（与thinking块中文字渲染效果一致）
- **FR-7**: 多格式导出对话框 — 点击导出按钮弹出对话框，支持选择格式（MD/PDF/PNG/JPG/DOCX），顶部导出按钮默认选中全部消息且可取消勾选，消息旁导出按钮默认选中当前消息对
- **FR-8**: 单条消息删除 — 每条AI/用户消息显示删除按钮（hover时可见），点击二次确认后删除，删除的消息不进入LLM上下文构建
- **FR-9**: 搜索结果内联链接 — ToolCallBlock展开的搜索结果中，每个结果标题是可点击链接

## Non-Functional Requirements
- **NFR-1**: 流式渲染性能 — 多轮thinking block追加不导致UI卡顿，每个delta更新只重渲染对应block
- **NFR-2**: 无障碍 — 所有可折叠卡片支持键盘操作（Enter/Space切换），链接有正确的aria-label
- **NFR-3**: 适老化 — 患者老年模式下卡片间距、字体大小、按钮尺寸符合适老化规范
- **NFR-4**: 构建稳定性 — npm run build无TypeScript错误，npm run lint 0错误0警告
- **NFR-5**: 向后兼容 — localStorage中已保存的历史消息（旧格式单thinking block）能正常渲染

## Constraints
- **Technical**: Next.js 16 + React 19 + Zustand + TailwindCSS + shadcn/ui，导出使用纯前端库（html2canvas + jsPDF + docx）
- **Business**: 医疗安全底线不变，所有医疗输出带免责声明
- **Dependencies**: 搜索结果数据来自web_search工具的返回值，已有result字段存储

## Assumptions
- 后端SSE已发送thinking_start/thinking_done/tool_call_start/tool_result等事件，前端需要正确处理多轮切换
- web_search工具返回的result包含results数组，每项有title/url/snippet/source字段
- html2canvas/jsPDF/docx库可通过npm安装使用

## Acceptance Criteria

### AC-1: 多轮thinking独立卡片
- **Given**: 用户提问触发搜索（如"2025高血压指南更新"）
- **When**: LLM完成第一轮思考→调用搜索→查看结果→第二轮思考→输出回答
- **Then**: 消息中应按顺序出现：[思考过程1（折叠）]→[搜索工具卡片（可展开）]→[思考过程2（折叠）]→[最终回答文本]
- **Verification**: `human-judgment`

### AC-2: 搜索卡片展开结果
- **Given**: 搜索工具调用完成
- **When**: 用户点击搜索工具卡片
- **Then**: 展开显示搜索结果列表，每项包含可点击标题（跳转原文URL）、来源名、snippet摘要
- **Verification**: `human-judgment`

### AC-3: 引用链接可跳转
- **Given**: 回答中有引用角标
- **When**: 用户点击角标弹出popover，点击"查看原文"
- **Then**: 浏览器在新标签页打开对应URL
- **Verification**: `programmatic`

### AC-4: 无末尾闪烁光标
- **Given**: AI回复完成
- **When**: 消息状态变为done
- **Then**: 文本末尾不显示"|"光标，文字呈现稳定
- **Verification**: `human-judgment`

### AC-5: 思维链更简洁
- **Given**: 用户问基础医学问题
- **When**: AI回答
- **Then**: thinking内容长度适中（<200字），不输出冗长自我辩论
- **Verification**: `human-judgment`

### AC-6: 多格式导出对话框
- **Given**: 用户点击导出按钮
- **When**: 弹出导出对话框
- **Then**: 可选择MD/PDF/PNG/JPG/DOCX格式，可勾选要导出的消息，点击导出下载对应格式文件
- **Verification**: `human-judgment`

### AC-7: 单条消息删除
- **Given**: 对话中有多条消息
- **When**: 用户hover某条消息点击删除按钮，确认删除
- **Then**: 该消息从UI消失，后续发送消息时该消息不出现在LLM上下文中
- **Verification**: `programmatic`

### AC-8: 构建和Lint通过
- **Given**: 所有修改完成
- **When**: 运行npm run lint和npm run build
- **Then**: 0错误0警告，构建成功
- **Verification**: `programmatic`

## Open Questions
- [ ] PDF/DOCX导出是否需要包含图片？（首期可仅导出文本内容）
- [ ] 删除消息后是否需要支持撤销？（首期不支持，直接删除）
- [ ] 多轮thinking的折叠状态：第一轮默认展开还是折叠？（参考Trae Work，思考中自动展开，完成后自动折叠）
