# 0007 完成检查清单

## 核心架构重构
- [x] Task 1: client.ts 新增thinking_start/thinking_done事件，支持多轮ReAct循环
- [x] Task 2: chatStore支持多个thinking blocks（不再合并为一个）
- [x] Task 3: ChatArea按时间顺序排列thinking→tool→thinking→text blocks

## UI组件
- [x] Task 4: ToolCallBlock搜索完成后展开显示搜索结果列表
- [x] Task 5: CitationPopover"查看原文"修复+末尾光标修复+提示语优化
- [x] Task 6: ExportDialog多格式导出（MD/PDF/PNG/JPG/DOCX）
- [x] Task 7: MessageBubble单条删除按钮+DeleteConfirmDialog

## 回归测试
- [x] npm run lint 通过（0错误）
- [x] npm run build 通过（0错误）
- [x] 浏览器测试：多轮thinking块按顺序显示、搜索结果展开正常、引用跳转正常、导出对话框正常、删除按钮正常
- [x] 老年模式字体/按钮大小符合规范
- [x] 医疗免责声明正常显示
