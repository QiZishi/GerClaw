# UI布局与主题 — 产品规格

> 模块：UI布局与主题 | 优先级：P0 | 基于PRD.md第4节生成

---

## 1. 模块概述

GerClaw平台的界面框架与视觉系统核心模块，提供对齐Trae Work交互体验的三栏可折叠布局（左侧边栏+中间主聊天区+右侧动态面板）、深浅双主题切换（默认浅色，支持跟随系统/手动切换）、响应式自适应（窄屏自动收起两侧面板）、消息气泡与Markdown渲染样式、适老化老年模式适配，为老年患者和医生提供专业、流畅、无障碍的统一界面体验。

## 2. 用户故事

| 编号 | 作为... | 我想要... | 以便于... |
|------|---------|----------|----------|
| US-001 | 老年患者 | 使用大字体、大按钮、高对比度的界面 | 能看清文字、方便点击操作，不因视力问题影响使用 |
| US-002 | 老年患者 | 侧边栏可以折叠收起，只显示图标 | 有更大的聊天区域，界面更简洁不杂乱 |
| US-003 | 老年患者 | 右侧面板在需要时自动展开，不用时自动收起 | 专注于对话内容，不被无关信息干扰 |
| US-004 | 老年科医生 | 可以切换深色/浅色主题，或跟随系统设置 | 根据工作环境和个人喜好选择舒适的视觉模式，长时间使用不累眼 |
| US-005 | 老年科医生 | 右侧面板宽度可以拖拽调整 | 根据内容需要灵活调整预览区域大小，方便查看处方报告、CGA评估结果 |
| US-006 | 老年科医生 | 在平板/小屏设备上使用时自动收起两侧面板 | 在移动设备上也能正常使用核心对话功能 |
| US-007 | 访客用户 | 切换医生/患者模式时界面自动适配样式 | 快速体验不同角色的界面差异和功能 |
| US-008 | 所有用户 | 消息气泡样式美观、Markdown渲染清晰（含代码高亮） | 舒适地阅读AI回复内容，表格、代码块、引用都能正确显示 |
| US-009 | 所有用户 | 所有图标按钮hover时显示文字提示 | 知道每个按钮的功能，不会误操作 |

## 3. 功能清单

| 编号 | 功能 | 描述 | 优先级 | 验收标准 |
|------|------|------|--------|---------|
| F-001 | 三栏可折叠布局-左侧边栏 | 左侧导航/会话列表区域，展开宽度260-280px，折叠宽度60-70px（图标栏） | P0 | 展开时显示完整导航+会话列表+功能入口；折叠时只显示图标，hover显示tooltip；折叠/展开有平滑过渡动画（200ms ease-in-out） |
| F-002 | 三栏可折叠布局-中间主聊天区 | 弹性宽度自适应，承载欢迎页、消息列表、输入框区域 | P0 | 两侧面板展开/折叠时聊天区宽度平滑调整；消息内容不溢出；长消息自动滚动 |
| F-003 | 三栏可折叠布局-右侧动态面板 | 默认隐藏（0px），功能触发时自动展开320-400px，宽度可拖拽调整320-500px | P0 | 技能管理/处方预览/CGA评估/文件预览/引用详情触发时自动展开；顶部有关闭按钮；拖拽分隔条可在320-500px范围内调整宽度，有最小/最大宽度限制 |
| F-004 | 深浅双主题-浅色主题（默认） | 医疗专业蓝白配色：主色调#2563EB，背景#FFFFFF/#F8FAFC，侧边栏#F1F5F9 | P0 | 所有组件（按钮、卡片、输入框、消息气泡、工具卡片）在浅色主题下样式正确；颜色对比度≥4.5:1（AA标准） |
| F-005 | 深浅双主题-深色主题 | 深色专业配色：主色调#3B82F6，背景#0F172A/#1E293B，侧边栏#1E293B | P0 | 所有组件在深色主题下样式正确；文字清晰可读；边框/阴影适配深色背景 |
| F-006 | 主题切换-手动切换 | 侧边栏底部主题切换按钮，点击切换浅色/深色，即时生效不刷新页面 | P0 | 点击按钮主题立即切换；切换状态持久化到localStorage；按钮图标随当前主题变化（太阳/月亮） |
| F-007 | 主题切换-跟随系统 | 默认检测系统prefers-color-scheme设置，系统主题变化时自动跟随 | P0 | 首次访问自动应用系统主题；系统主题切换时（如MacOS自动切换深色模式）页面自动跟随；手动切换后停止跟随系统 |
| F-008 | 响应式布局-桌面端（≥1280px） | 三栏完整显示，侧边栏默认展开，右侧面板按需展开 | P0 | 在1920×1080及以上分辨率下三栏布局正常显示，无内容挤压 |
| F-009 | 响应式布局-小屏桌面（1024-1279px） | 右侧面板默认收起，按需展开；侧边栏可正常折叠/展开 | P0 | 在1280宽度下右侧面板默认隐藏，点击触发时覆盖或挤压显示 |
| F-010 | 响应式布局-平板端（768-1023px） | 左侧边栏默认折叠为图标栏，右侧面板覆盖式展开 | P0 | 在iPad尺寸下侧边栏自动折叠，点击展开为抽屉；右侧面板不挤压聊天区，采用浮层覆盖模式 |
| F-011 | 响应式布局-手机端（<768px） | 侧边栏抽屉式展开，右侧面板全屏覆盖，优先展示聊天区 | P0 | 在手机尺寸下侧边栏隐藏为汉堡菜单，点击滑出；右侧面板占满屏幕；语音输入按钮放大突出 |
| F-012 | 左侧边栏-顶部区域 | 系统标识区（Logo+名称+模式标签）、折叠控制按钮、新建对话按钮、历史搜索框、历史对话列表（按时间分组）、技能管理入口 | P0 | 新建按钮为突出主按钮样式；会话按今天/昨天/最近7天/更早分组；会话项hover显示重命名/删除/固定按钮；技能管理入口点击在右侧面板展开 |
| F-013 | 左侧边栏-底部区域 | 用户头像区（访客/医生/患者）、模式切换按钮（仅访客）、老年模式开关（仅患者端，默认开启）、主题切换按钮 | P0 | 点击头像展开菜单；医生/患者模式切换后刷新页面加载对应UI；老年模式开关即时生效不刷新 |
| F-014 | 右侧面板-动态内容 | 根据触发场景显示不同内容：技能管理界面、处方预览/导出、CGA评估量表、文件预览、引用详情列表 | P0 | 不同场景切换时面板内容正确替换；面板内支持滚动；长内容不溢出；关闭后回到隐藏状态 |
| F-015 | 消息气泡样式-用户消息 | 靠右对齐，主色调背景气泡，右侧显示用户头像 | P0 | 气泡圆角8px；文字白色；最大宽度不超过聊天区70%；长文本自动换行 |
| F-016 | 消息气泡样式-AI消息 | 靠左对齐，浅色/透明背景气泡，左侧显示GerClaw头像 | P0 | 气泡圆角8px；文字为主题正文色；最大宽度不超过聊天区75%；支持Markdown完整渲染 |
| F-017 | Markdown渲染 | 完整支持标题、列表、引用、表格、代码块、链接、粗体/斜体 | P0 | 标题层级清晰；表格边框对齐正确；引用块有左侧边框标识；列表缩进正确 |
| F-018 | 代码高亮 | 代码块语法高亮，显示语言标签，右上角提供复制按钮 | P0 | 支持JavaScript/TypeScript/Python/JSON/HTML/CSS等常见语言高亮；点击复制按钮一键复制代码，显示"已复制"提示 |
| F-019 | 医生/患者端主题差异化 | 医生端主色调冷蓝#2563EB（专业严谨），患者端主色调暖蓝#0EA5E9（亲和友好） | P0 | 切换医生/患者模式后主色调随之变化；按钮、链接、激活状态颜色对应调整 |
| F-020 | 老年模式适老化 | 患者端默认开启：基础字号18px（普通14px）、按钮最小48px（普通32px）、对比度≥7:1（AAA）、行高1.8（普通1.6）、动画速度0.7x、关键操作二次确认 | P0 | 开启老年模式后所有字体立即放大；按钮点击区域足够大；颜色对比明显；动画放慢不闪烁；删除等危险操作弹出二次确认对话框 |
| F-021 | Tooltip提示 | 所有图标按钮（尤其是折叠侧边栏时）hover延迟300ms显示文字Tooltip | P0 | 折叠状态下边栏所有图标hover显示Tooltip；Tooltip位置正确不遮挡；延迟300ms显示避免误触 |
| F-022 | 面板拖拽调整宽度 | 右侧面板左边缘提供拖拽手柄，鼠标拖动可在320-500px范围内调整宽度 | P0 | 拖拽时光标变为col-resize；拖拽过程有视觉反馈（分隔线高亮）；松开后面板宽度固定；宽度值持久化到localStorage |
| F-023 | 状态持久化 | 侧边栏折叠/展开状态、右侧面板宽度、主题选择、老年模式开关都保存到localStorage | P0 | 刷新页面后布局状态保持上次设置；清除localStorage后恢复默认值 |

## 4. 交互流程

### 4.1 主流程（Happy Path）

```
用户进入页面
  ↓
检测localStorage中的主题/布局偏好 → 无则使用系统主题+默认布局
  ↓
检测视口宽度 → 应用对应响应式断点布局
  ↓
渲染三栏布局：
  ├─ 左侧边栏：默认展开（桌面端）/折叠（平板）/抽屉（手机）
  ├─ 主聊天区：弹性宽度，显示欢迎页
  └─ 右侧面板：默认隐藏
  ↓
用户操作场景1：点击侧边栏折叠按钮
  ↓
侧边栏宽度从270px平滑过渡到64px（200ms）
  ↓
只显示图标，hover显示Tooltip
  ↓
主聊天区自动扩展宽度
  ↓
状态保存到localStorage

用户操作场景2：点击💊处方按钮
  ↓
右侧面板自动从右侧滑出（380px宽，200ms动画）
  ↓
面板内显示处方生成向导/预览界面
  ↓
主聊天区对应压缩宽度
  ↓
用户点击面板关闭按钮 → 面板滑出隐藏，聊天区恢复

用户操作场景3：点击主题切换按钮
  ↓
主题在浅色↔深色间切换（150ms过渡）
  ↓
所有组件颜色立即更新
  ↓
停止跟随系统主题
  ↓
选择保存到localStorage

用户操作场景4：视口宽度变化（如缩放浏览器、旋转平板）
  ↓
实时检测断点变化
  ↓
自动应用对应响应式布局（如桌面→平板：侧边栏自动折叠）
```

### 4.2 异常流程

| 异常场景 | 系统行为 | 用户提示 |
|---------|---------|---------|
| localStorage读写失败（如隐私模式、存储被禁用） | 降级为内存存储，使用默认布局和主题，关闭页面后重置 | 首次访问时控制台warn日志记录；不影响功能使用，仅状态不持久化 |
| 右侧面板拖拽超出范围（<320px或>500px） | 自动限制在最小/最大宽度，停止跟随鼠标 | 拖拽到边界时有视觉反馈（不能继续拖动），无额外提示 |
| 系统主题检测失败（如旧浏览器不支持prefers-color-scheme） | 回退到默认浅色主题 | 无用户提示，控制台log记录 |
| 视口 resize 事件频繁触发 | 使用防抖（debounce 150ms）处理，避免频繁重排 | 无用户感知，布局平滑调整 |
| 老年模式下高对比度颜色计算异常 | 使用预设的高对比度配色方案，不动态计算 | 颜色符合WCAG AAA标准，无用户提示 |
| CSS过渡动画被用户操作系统设置为"减少动画" | 检测prefers-reduced-motion，禁用所有非必要动画 | 所有过渡变为瞬间切换，不影响功能 |

## 5. 界面/API规格

### 5.1 界面

- **页面/组件名**：全局布局框架（AppLayout）
- **入口**：应用根组件，所有页面都嵌套在此布局内
- **关键元素**：
  - **左侧边栏（Sidebar）**：
    - 顶部：Logo区域（图标+GerClaw文字+医生/患者标签）、折叠按钮（≡）、新建对话按钮（+ 主按钮样式）、搜索框、历史会话分组列表（今天/昨天/最近7天/更早）、技能管理入口
    - 底部：用户头像、模式切换（医生/患者，仅访客）、老年模式开关（仅患者端）、主题切换按钮（太阳/月亮）
  - **侧边栏折叠状态**：宽度64px，只显示图标（Logo、+、会话图标、技能图标、头像、主题图标），所有图标hover显示Tooltip
  - **主聊天区（ChatArea）**：
    - 欢迎页：GerClaw大Logo、适配备选问候语、快捷入口卡片（五大处方/CGA评估/用药审查）、示例提示词
    - 消息列表：用户气泡（右，主色背景）、AI气泡（左，浅色背景）、消息操作按钮（复制/重新生成/语音朗读/导出，hover显示）、思考过程折叠块、工具调用卡片、引用角标[1][2]、回到底部悬浮按钮
    - 输入区域：标签栏（已加载技能/已上传文件，可×移除）、内嵌输入框（左侧：📎文件/⚡技能/💊处方/📋评估；中间：多行文本；右侧：🎤/✈️/⏹）、底部免责声明文字
  - **右侧动态面板（RightPanel）**：
    - 顶部：面板标题、关闭按钮（×）
    - 拖拽手柄：左边缘4px宽区域，鼠标hover变主色调
    - 内容区：动态内容（技能管理/处方预览/CGA评估/文件预览/引用列表），支持滚动
    - 展开/收起动画：从右侧滑入/滑出（200ms ease-in-out）
- **状态要求**：
  - **主流程**：三栏布局正常显示，折叠/展开/切换主题/拖拽面板都流畅工作
  - **加载中**：页面初次加载时有骨架屏或加载指示器；面板切换内容时显示加载状态
  - **为空**：历史会话列表为空时显示空状态引导（"开始新对话吧"）；右侧面板隐藏时聊天区占满宽度
  - **错误**：localStorage不可用时功能正常但状态不持久，控制台记录日志；主题切换失败时保持当前主题

### 5.2 API端点（如适用）

> MVP阶段为纯前端静态导出，无后端API。主题/布局状态全部通过localStorage在浏览器端持久化。

| 方法 | 路径 | 描述 | 认证 | 请求参数 | 响应格式 |
|------|------|------|------|---------|---------|
| - | - | 无自有API，纯前端实现 | - | - | - |

**localStorage存储键值**：
```typescript
// UI偏好设置存储结构
interface UIPreferences {
  theme: 'light' | 'dark' | 'system';
  sidebarCollapsed: boolean;
  rightPanelWidth: number; // 320-500
  elderlyMode: boolean; // 仅患者端有效
  userRole: 'doctor' | 'patient'; // 仅访客模式可切换
}

// localStorage键名
const STORAGE_KEYS = {
  UI_PREFERENCES: 'gerclaw_ui_preferences',
  CONVERSATIONS: 'gerclaw_conversations',
  MESSAGES: 'gerclaw_messages',
  CUSTOM_SKILLS: 'gerclaw_custom_skills',
};
```

## 6. 数据模型

```typescript
// 主题模式
type ThemeMode = 'light' | 'dark' | 'system';

// 视口断点
type Breakpoint = 'desktop' | 'small-desktop' | 'tablet' | 'mobile';

// 用户角色
type UserRole = 'doctor' | 'patient' | 'guest';

// 右侧面板内容类型
type RightPanelContentType = 
  | null  // 隐藏
  | 'skills'        // 技能管理
  | 'prescription'  // 处方预览
  | 'cga-assessment' // CGA评估
  | 'file-preview'  // 文件预览
  | 'citations'     // 引用详情
  | 'health-profile'; // 健康画像

// UI布局状态（Context管理）
interface LayoutState {
  // 主题
  theme: ThemeMode;
  resolvedTheme: 'light' | 'dark'; // 实际生效的主题（解析system后）
  
  // 侧边栏
  sidebarCollapsed: boolean;
  
  // 右侧面板
  rightPanelOpen: boolean;
  rightPanelContentType: RightPanelContentType;
  rightPanelWidth: number; // 320-500，默认380
  rightPanelData?: unknown; // 面板内容数据（如处方报告、CGA题目等）
  
  // 视口
  viewportWidth: number;
  breakpoint: Breakpoint;
  
  // 角色与模式
  userRole: UserRole;
  elderlyMode: boolean; // 仅patient角色时可切换
}

// UI布局操作（Context actions）
interface LayoutActions {
  // 主题操作
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  
  // 侧边栏操作
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  
  // 右侧面板操作
  openRightPanel: (type: RightPanelContentType, data?: unknown) => void;
  closeRightPanel: () => void;
  setRightPanelWidth: (width: number) => void;
  
  // 模式操作
  setUserRole: (role: UserRole) => void;
  toggleElderlyMode: () => void;
  setElderlyMode: (enabled: boolean) => void;
}

// 颜色系统Token（CSS变量实现）
interface ColorTokens {
  // 品牌色
  primary: string;
  primaryHover: string;
  primaryActive: string;
  primaryForeground: string;
  
  // 状态色
  success: string;
  warning: string;
  error: string;
  info: string;
  
  // 背景
  background: string;
  backgroundSecondary: string;
  sidebarBackground: string;
  panelBackground: string;
  cardBackground: string;
  hoverBackground: string;
  
  // 文本
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textInverse: string;
  
  // 边框
  border: string;
  borderFocus: string;
}

// 排版Token
interface TypographyTokens {
  fontFamily: string;
  fontFamilyCode: string;
  
  fontSize: {
    h1: string;
    h2: string;
    h3: string;
    body: string;
    caption: string;
    small: string;
  };
  
  fontWeight: {
    regular: number;
    medium: number;
    semibold: number;
  };
  
  lineHeight: {
    tight: number;
    normal: number;
    relaxed: number;
  };
}

// 间距/圆角/阴影Token
interface SpacingTokens {
  xs: string;  // 4px
  sm: string;  // 8px
  md: string;  // 12px
  lg: string;  // 16px
  xl: string;  // 24px
  '2xl': string; // 32px
  
  radiusSm: string;  // 4px
  radiusMd: string;  // 8px
  radiusLg: string;  // 12px
  radiusFull: string; // 9999px
  
  shadowSm: string;
  shadowMd: string;
  shadowLg: string;
  shadowXl: string;
}
```

## 7. 非功能要求

| 维度 | 要求 |
|------|------|
| 性能 | 首屏布局渲染<100ms；主题切换无闪烁（CSS变量实现，避免重排）；面板折叠/展开动画60fps；侧边栏/面板过渡动画流畅不卡顿（200ms内完成）；resize防抖处理避免频繁重排 |
| 安全 | XSS防护：Markdown渲染时使用安全的Markdown解析器（如react-markdown+rehype-sanitize），转义危险HTML；不通过URL传递敏感状态；localStorage不存储医疗敏感数据 |
| 可靠性 | localStorage写入失败时优雅降级（内存状态）；不支持的浏览器API（如matchMedia）有polyfill或降级方案；CSS变量有fallback值；所有动画检测prefers-reduced-motion，用户开启"减少动画"时禁用过渡 |
| 可观测性 | 关键操作记录console日志（主题切换、面板打开/关闭、断点变化）；localStorage异常时记录warn级别日志；布局异常（如宽度计算错误）记录error日志 |
| 兼容性 | Chrome/Edge/Safari最新2个版本；支持CSS Variables、Flexbox、Grid；matchMedia API支持（IE11除外，不考虑）；桌面端/平板端/手机端核心布局功能可用 |
| 无障碍 | 支持键盘导航（Tab在可交互元素间切换，Enter/Esc操作按钮/关闭面板）；焦点可见（focus ring清晰）；颜色对比度达标（普通AA≥4.5:1，老年模式AAA≥7:1）；图标按钮有aria-label；折叠状态有aria-expanded属性；屏幕阅读器可正确识别主题切换、面板状态 |
| 适老化 | 患者端老年模式：正文≥18px，标题≥20px，按钮≥48px点击区域，对比度≥7:1（AAA），行高1.8，动画速度0.7x，关键操作（删除会话等）二次确认，语音入口突出，文字提示通俗易懂 |

## 8. 不做什么（Out of Scope）

- 自定义主题色/配色方案（MVP仅提供预设的深/浅双主题，医生/患者端仅主色调微调）
- 字体大小自定义调整（仅通过老年模式开关提供两档：普通/老年）
- 布局拖拽自定义（如左侧边栏宽度不能自由拖拽，仅支持展开/折叠两档；右侧面板仅宽度可在320-500px拖拽）
- 多语言/国际化（MVP仅支持中文界面）
- 右侧面板多标签页/同时打开多个面板（MVP同一时间右侧面板只能显示一种内容）
- 侧边栏位置调整（固定在左侧，不支持切换到右侧）
- 主题编辑器/颜色自定义（用户不能自定义颜色值，只能切换预设主题）
- 复杂的键盘快捷键自定义（MVP仅支持基础快捷键Enter发送/Shift+Enter换行）
- 消息气泡自定义（气泡形状/颜色固定，不支持用户自定义）
- 动画开关独立控制（仅跟随系统"减少动画"设置和老年模式自动放慢，不提供单独开关）
- 医生端/患者端完全不同的布局结构（仅配色和组件细节差异，整体三栏布局一致）
