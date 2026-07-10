# 0006 UX打磨与Bug修复 - Product Requirement Document

## Overview
- **Summary**: 通过浏览器实际测试发现的严重体验问题修复，包括HTML语义错误、不必要联网搜索、默认老年模式、引用渲染重复、工具调用卡片展示优化，使产品体验对齐Trae Work和蚂蚁阿福，符合老年患者与专业医生的产品定位。
- **Purpose**: 解决浏览器实际测试中发现的P0/P1级体验问题，修复hydration错误、优化工具调用策略、修正默认设置、打磨细节体验。
- **Target Users**: 老年患者、老年科医生、访客用户

## Goals
- 修复SourceReferences组件button嵌套button导致的hydration错误
- 优化web_search工具触发逻辑，基础医学常识问题不触发联网搜索
- 修正默认模式：访客模式默认不开启老年模式，患者端可手动切换
- 修复引用角标重复渲染问题
- 优化ToolCallBlock搜索完成后的展示，不显示无意义的raw JSON
- 修复思考时间统计不准确问题（包含工具调用时间）
- 确保Web Interface Guidelines基础合规（aria-label、语义化等）
- 整体体验对齐Trae Work的简洁、流畅、不突兀

## Non-Goals (Out of Scope)
- 不进行大规模UI重构
- 不新增功能模块
- 不修改语音交互核心逻辑
- 不改变三栏布局架构

## Background & Context
通过内置浏览器实际端到端测试（发送普通健康咨询消息、观察加载状态、检查DOM结构、查看控制台错误），结合Web Interface Guidelines审查，发现以下问题：
1. 控制台报错：button嵌套button导致hydration错误
2. 基础医学问题（血压正常范围）触发了6个网页搜索，响应变慢且不必要
3. 默认进入就是老年模式（大字号+自动TTS朗读），访客体验差
4. 引用角标popover重复渲染3个"查看引用1"
5. ToolCallBlock搜索完成后仍显示"展开详情"按钮，展开是raw JSON无用户价值
6. 思考时间16.7s包含了工具调用时间，不是纯LLM思考时长

## Functional Requirements
- **FR-1**: SourceReferences组件的"查看全部"按钮不使用嵌套button，改为正确的HTML结构
- **FR-2**: web_search工具的description明确指引LLM"仅在需要最新信息、实时数据、具体药品说明书时才搜索，基础医学常识/定义类问题直接回答"
- **FR-3**: 默认role为visitor（访客），访客模式默认不开启老年模式；患者模式可切换老年模式
- **FR-4**: 引用角标(CitationPopover)正确渲染，不重复
- **FR-5**: ToolCallBlock搜索工具完成后默认不显示展开按钮（或展开后显示有用的信息而非raw JSON）
- **FR-6**: 思考时间仅计算LLM返回reasoning_content的时长，工具调用时间单独计算或不显示在思考块中

## Non-Functional Requirements
- **NFR-1**: 控制台无hydration错误、无React warning
- **NFR-2**: 基础医学问题响应速度提升（不触发不必要搜索）
- **NFR-3**: 符合Web无障碍基础要求（icon button有aria-label、语义化HTML）
- **NFR-4**: 所有现有功能不被破坏（lint/build通过）

## Constraints
- **Technical**: Next.js 16 + React 19 + Zustand + Tailwind CSS
- **Business**: 医疗安全底线不变，免责声明必须显示
- **Dependencies**: 现有组件架构，不引入新依赖

## Assumptions
- 默认进入访客模式是合理的（产品支持访客使用，无需登录）
- 搜索工具description优化能有效减少LLM不必要的搜索调用
- 用户可以手动切换到患者/医生模式和老年模式

## Acceptance Criteria

### AC-1: SourceReferences无button嵌套
- **Given**: 用户在聊天界面看到AI回复有参考来源
- **When**: 查看DOM结构或浏览器控制台
- **Then**: 无button嵌套button错误，SourceReferences展开/收起/查看全部功能正常
- **Verification**: `programmatic` + `human-judgment`

### AC-2: 基础医学常识不触发搜索
- **Given**: 用户问"老年人血压正常范围是多少"这类基础医学问题
- **When**: 发送消息并等待响应
- **Then**: 不显示联网搜索卡片，不显示参考来源列表（除非确实需要搜索），直接回答
- **Verification**: `human-judgment` + `programmatic`（检查ToolCallBlock是否出现）

### AC-3: 默认访客模式无自动TTS
- **Given**: 用户首次访问网站（清除localStorage后）
- **When**: 页面加载完成
- **Then**: 默认是访客模式，老年模式关闭，字号正常，不会自动触发TTS朗读
- **Verification**: `human-judgment` + `programmatic`

### AC-4: 引用角标正确不重复
- **Given**: AI回复中有引用标注[1][2]
- **When**: 查看消息区域
- **Then**: 每个引用角标对应一个popover，无重复的"查看引用"按钮
- **Verification**: `human-judgment`

### AC-5: ToolCallBlock搜索完成后展示简洁
- **Given**: AI执行了联网搜索
- **When**: 搜索完成后查看ToolCallBlock
- **Then**: 显示"已找到N个结果"简洁状态，默认不展开raw JSON，点击展开才显示（或不显示展开按钮直接折叠）
- **Verification**: `human-judgment`

### AC-6: 控制台无错误
- **Given**: 用户正常使用聊天功能
- **When**: 打开浏览器开发者工具Console
- **Then**: 无红色错误，无React warning
- **Verification**: `programmatic`

### AC-7: lint和build通过
- **Given**: 修改完成后
- **When**: 运行npm run lint和npm run build
- **Then**: 0错误0警告，构建成功
- **Verification**: `programmatic`

## Open Questions
- [ ] 默认角色应该是visitor还是patient？当前代码默认patient但有visitor选项，需要确认（按AGENTS.md"访客模式下所有功能可用"，默认visitor更合理）
- [ ] 搜索完成后的ToolCallBlock是否应该完全自动收起不显示？Trae Work中工具调用完成后卡片会收起只留一个小标识
