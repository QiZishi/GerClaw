# 0009 全量需求实现 - Verification Checklist

## 紧急Bug修复
- [ ] Checkpoint 1.1: 普通聊天（包括老年模式）AI回复完成后不自动播放TTS语音
- [ ] Checkpoint 1.2: ThinkingBlock思考中显示spinner（Loader2），旋转速率1.5s适中，不是三点动画
- [ ] Checkpoint 1.3: StreamingText空内容等待时显示三点跳动动画
- [ ] Checkpoint 1.4: 代码中无autoReadIfSeniorMode/老年模式普通对话自动播放逻辑

## 消息操作按钮
- [ ] Checkpoint 2.1: 每条AI消息下方有完整按钮行：赞、踩、复制、重新生成、播放、分享、三点菜单
- [ ] Checkpoint 2.2: 赞/踩互斥，点击后弹出反馈输入框，可输入文字或直接提交
- [ ] Checkpoint 2.3: 复制按钮点击后复制纯文本到剪贴板，按钮显示✓ 2秒后恢复
- [ ] Checkpoint 2.4: 重新生成按钮仅在最后一条AI消息显示
- [ ] Checkpoint 2.5: 播放按钮点击切换播放/暂停，默认不播放
- [ ] Checkpoint 2.6: 分享按钮打开ExportDialog，默认选中当前问答对，支持PNG/PDF/DOCX/MD
- [ ] Checkpoint 2.7: 三点菜单包含"转为文档编辑"和"删除"选项
- [ ] Checkpoint 2.8: 删除按钮打开DeleteConfirmDialog，默认选中当前问答对，有取消和确认
- [ ] Checkpoint 2.9: 转为文档编辑在右侧栏打开MD编辑器，实时预览
- [ ] Checkpoint 2.10: 按钮样式为豆包风格圆角pill容器

## 搜索链接
- [ ] Checkpoint 3.1: 搜索结果标题是`<a target="_blank" rel="noopener noreferrer">`链接
- [ ] Checkpoint 3.2: 浏览器中点击搜索结果标题在新标签页打开

## CGA量表题数
- [ ] Checkpoint 4.1: PHQ-9 questions.length === 9
- [ ] Checkpoint 4.2: GAD-7 questions.length === 7
- [ ] Checkpoint 4.3: Mini-Cog questions.length === 3
- [ ] Checkpoint 4.4: MMSE questions.length === 30
- [ ] Checkpoint 4.5: 每个scale的questionCount与questions.length一致

## CGA预录音频
- [ ] Checkpoint 5.1: public/audio/cga/目录下有mp3音频文件
- [ ] Checkpoint 5.2: 进入CGA题目自动播放音频（默认开）
- [ ] Checkpoint 5.3: 点击暂停后音频停止，后续题目不自动播放
- [ ] Checkpoint 5.4: 重新开启后后续题目恢复自动播放
- [ ] Checkpoint 5.5: 返回量表选择页音频停止
- [ ] Checkpoint 5.6: 音频开关状态持久化到localStorage
- [ ] Checkpoint 5.7: 播放中按钮显示Volume2，暂停显示VolumeX

## CGA语音识别与跳转
- [ ] Checkpoint 6.1: 语音说"a"/"诶"/"选项a"选中第一个选项
- [ ] Checkpoint 6.2: 语音说"b"/"c"/"d"选中对应选项
- [ ] Checkpoint 6.3: 语音识别选完后不自动跳转到下一题
- [ ] Checkpoint 6.4: 键盘数字键选完后不自动跳转
- [ ] Checkpoint 6.5: 点击"下一题"按钮才前进

## CGA多量表+完成页
- [ ] Checkpoint 7.1: 量表选择界面有"全选"按钮
- [ ] Checkpoint 7.2: 可勾选多个量表，开始作答后连续做完所有题目
- [ ] Checkpoint 7.3: 进度条显示"第X/总题数题"
- [ ] Checkpoint 7.4: 完成后右侧栏不自动弹出
- [ ] Checkpoint 7.5: 中间栏显示"✅ 作答完毕"+已完成量表名+三个按钮（重新评估/继续作答其他量表/查看报告）
- [ ] Checkpoint 7.6: "继续作答其他量表"返回选择界面，已作答题量disabled
- [ ] Checkpoint 7.7: 所有量表完成后显示"所有量表已作答完毕"+"生成评估报告"按钮
- [ ] Checkpoint 7.8: localStorage持久化作答进度，refresh后恢复
- [ ] Checkpoint 7.9: 退出确认框文案根据是否有报告区分

## 文件上传+MinerU
- [ ] Checkpoint 8.1: /api/mineru/parse API route存在且可调用
- [ ] Checkpoint 8.2: 上传8个文件全部成功加载（修复5个限制bug）
- [ ] Checkpoint 8.3: 文件上传后调用MinerU解析，显示解析中状态
- [ ] Checkpoint 8.4: 解析内容作为上下文传给LLM
- [ ] Checkpoint 8.5: 不传文件也可以进行五大处方（纯文本/语音输入）

## 本地知识库
- [ ] Checkpoint 9.1: /api/knowledge/search API route存在
- [ ] Checkpoint 9.2: 五大处方生成时优先检索本地知识库
- [ ] Checkpoint 9.3: 知识库有结果时减少或不触发联网搜索
- [ ] Checkpoint 9.4: public/knowledge/目录下有md文件

## 信息收集卡片
- [ ] Checkpoint 10.1: 信息不全时弹出对话卡片
- [ ] Checkpoint 10.2: 每轮卡片最多4个问题
- [ ] Checkpoint 10.3: 卡片支持文本输入和语音输入
- [ ] Checkpoint 10.4: 最多3轮卡片后用已有信息生成
- [ ] Checkpoint 10.5: 已收集字段以InfoCollectionCard绿色√显示

## 五大处方生成
- [ ] Checkpoint 11.1: Zod schema定义健康画像和五大处方结构
- [ ] Checkpoint 11.2: 先生成健康画像再生成五大处方
- [ ] Checkpoint 11.3: LLM输出JSON通过Zod校验，失败重试最多2次
- [ ] Checkpoint 11.4: JSON校验通过后转为Markdown在右侧栏显示
- [ ] Checkpoint 11.5: 发送给LLM前进行PII脱敏
- [ ] Checkpoint 11.6: 包含用药审查/药物相互作用检查

## 右侧栏MD编辑器
- [ ] Checkpoint 12.1: 右侧栏编辑区为左右分栏：textarea源码+Markdown实时预览
- [ ] Checkpoint 12.2: 输入Markdown时预览区实时渲染（延迟<100ms，使用debounce）
- [ ] Checkpoint 12.3: 工具栏有复制按钮（复制到剪贴板）
- [ ] Checkpoint 12.4: 导出按钮支持PDF/DOCX/MD三种格式
- [ ] Checkpoint 12.5: 导出使用编辑后的最新内容
- [ ] Checkpoint 12.6: 五大处方、CGA报告、用药审查、转为文档编辑都使用此编辑器

## CGA报告生成
- [ ] Checkpoint 13.1: "查看已作答量表评估报告"调用LLM生成综合报告
- [ ] Checkpoint 13.2: 报告在右侧栏MarkdownEditor中显示，可编辑和导出

## 全量验证
- [ ] Checkpoint 14.1: npm run lint 0错误0警告
- [ ] Checkpoint 14.2: npm run build成功（Next.js Turbopack编译通过）
- [ ] Checkpoint 14.3: 开发服务器启动正常（localhost:3000或3001）
- [ ] Checkpoint 14.4: 浏览器测试普通对话全流程无阻塞bug
- [ ] Checkpoint 14.5: 浏览器测试五大处方全流程无阻塞bug
- [ ] Checkpoint 14.6: 浏览器测试CGA全流程无阻塞bug
- [ ] Checkpoint 14.7: git commit已提交，使用conventional commits格式
- [ ] Checkpoint 14.8: docs/长期规划.md已更新0009记录
