# 0007 Trae Work过程可视化与体验对齐 - 任务清单

## Task 1: 重构SSE流式事件格式
- [x] 修改 client.ts，支持 thinking_start/thinking_done 显式事件
- [x] 工具调用结束后自动开启新的thinking周期
- [x] 确保text delta结束当前thinking

## Task 2: 重构chatStore支持多thinking blocks
- [x] 修改 MessageBlock 类型，支持多个thinking块
- [x] 修改 startMessageThinkingBlock 追加新block而非复用
- [x] 删除 finishReorderBlocks 逻辑

## Task 3: ChatArea多块架构
- [x] onThinkingStart 创建新的thinking block（currentThinkingBlockIdRef）
- [x] 按自然顺序排列blocks，无需手动重排
- [x] onDone正确收尾

## Task 4: ToolCallBlock搜索结果展开
- [x] 搜索工具完成后可展开显示结果列表
- [x] 包含可点击标题、来源域名、发布日期、摘要
- [x] 非搜索工具保持展开/折叠参数和结果

## Task 5: 修复多个小问题
- [x] CitationPopover"查看原文"链接在新标签页打开
- [x] StreamingText末尾光标闪烁修复（仅streaming时显示）
- [x] 系统提示语优化：思考效率指引，减少冗长

## Task 6: 多格式导出对话框
- [x] 创建ExportDialog组件，支持5种格式（MD/PDF/PNG/JPG/DOCX）
- [x] 消息选择列表（全选/取消全选、默认选中）
- [x] 截图导出使用html2canvas+jsPDF/docx/file-saver
- [x] 导出时隐藏消息操作按钮

## Task 7: 单条消息删除
- [x] MessageBubble添加删除按钮（Trash2图标）
- [x] DeleteConfirmDialog确认对话框
- [x] chatStore.removeMessage更新session元数据
- [x] 删除的消息不进入LLM上下文
- [x] 删除streaming消息时自动中止

## Task 8: 全量回归测试
- [x] npm run lint 0错误
- [x] npm run build 0错误
- [x] 浏览器功能测试验证
