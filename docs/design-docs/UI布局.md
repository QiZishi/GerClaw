# UI布局与主题 — 设计文档

> 模块：UI布局与主题 | 关联产品规格：[product-specs/UI布局与主题.md](../product-specs/UI布局与主题.md)

---

## 1. 设计目标

基于 Next.js 16 + Tailwind CSS 4 + shadcn/ui 构建连接 FastAPI 的动态 Web 工作台与视觉设计系统，满足以下设计目标：

1. **Trae Work级布局体验**：实现三栏可折叠布局（左侧边栏270px↔64px、中间弹性聊天区、右侧动态面板380px可拖拽320-500px），对齐Trae Work的交互逻辑和视觉体验
2. **CSS变量主题系统**：基于Tailwind CSS 4的`@theme`指令定义设计Token（颜色、字体、间距、圆角、阴影），通过CSS变量实现深浅双主题无闪烁切换，支持`prefers-color-scheme`系统主题跟随
3. **响应式断点自适应**：四个断点（desktop≥1280px/small-desktop 1024-1279px/tablet 768-1023px/mobile<768px），窄屏自动收起两侧面板，手机端右侧面板全屏覆盖
4. **角色模式适配**：医生端（冷蓝#2563EB专业严谨）/患者端（暖蓝#0EA5E9亲和友好）主色调差异化，患者端老年模式（≥18px字体、≥48px按钮、≥7:1对比度、0.7x动画）
5. **状态持久化**：布局偏好（侧边栏折叠状态、右侧面板宽度、主题选择、老年模式开关）保存到localStorage，刷新页面恢复
6. **无障碍支持**：键盘导航、焦点可见、ARIA属性、颜色对比度达标（AA/AAA）、检测`prefers-reduced-motion`禁用动画
7. **组件解耦**：布局状态通过React Context全局管理，各功能模块（处方/CGA/技能等）通过统一接口调用右侧面板，不直接操作DOM

约束：
- 严格遵循gerclaw设计要求.md第3节界面设计规范、第13节UI/UX视觉设计系统
- 对齐Trae Work交互体验（三栏布局、面板展开/收起、折叠侧边栏Tooltip）
- 前端通过同源 BFF 调用 FastAPI；医疗事实、账号数据和会话记录均以服务端为准
- localStorage 仅保存无敏感信息的界面偏好；游客历史不能跨浏览器会话恢复

## 2. 架构设计

### 2.1 模块位置

在整体架构中的位置：**前端表现层最外层框架**，位于Next.js App Router的根布局（`app/layout.tsx`），是所有页面和功能模块的容器。

- **上层依赖**：无（是最外层容器，包裹整个应用）
- **本模块内部**：主题Provider、布局Provider（侧边栏/右侧面板/断点状态）、三栏布局组件、设计Token系统（CSS变量）、响应式监听、localStorage持久化
- **下层依赖（被使用）**：通用对话模块、五大处方模块、CGA评估模块、用药审查模块、联网搜索模块、技能管理模块、语音交互模块（所有模块都嵌套在本布局内，通过Context调用布局操作如打开右侧面板）

### 2.2 组件划分

| 组件 | 职责 | 文件位置（预期） |
|------|------|----------------|
| **ThemeProvider** | 管理 light/dark/system 模式；主题入口位于设置面板，不设置重复的浮动按钮 | `context/ThemeProvider.tsx` |
| **AppProvider** | 根据账号身份初始化患者、医生或管理员工作台，并协调游客会话生命周期 | `context/AppProvider.tsx` |
| **Sidebar** | 左侧导航与账号历史；患者窄屏通过“菜单”抽屉展开，游客不显示可恢复历史 | `components/layout/Sidebar.tsx` |
| **ChatArea** | 患者聊天、欢迎页、CGA、五大处方及实时文档编辑主区域 | `components/layout/ChatArea.tsx` |
| **DoctorHome** | 站在医生服务视角组织患者资料、CGA、处方审核、用药审查和风险台账 | `components/layout/DoctorHome.tsx` |
| **RightPanel** | 引用、设置、帮助等辅助内容；窄屏全屏覆盖，宽屏可调宽 | `components/layout/RightPanel.tsx` |
| **SettingsPanel** | 主题、适老化、朗读和模型配置入口 | `components/settings/SettingsPanel.tsx` |
| **LoginPage** | 强制入口；允许无账号进入患者端，账号角色限制工作台，管理员可切换角色 | `components/account/LoginPage.tsx` |
| **TooltipProvider** | Tooltip全局Provider：基于shadcn/ui Tooltip，延迟300ms显示，折叠侧边栏图标必须有Tooltip | `components/ui/tooltip.tsx`（shadcn） |
| **useViewport** | 自定义Hook：监听window resize，防抖150ms，返回当前viewportWidth和breakpoint | `hooks/use-viewport.ts` |
| **useLocalStorage** | 自定义Hook：localStorage读写封装，异常降级为内存状态，支持默认值 | `hooks/use-local-storage.ts` |
| **design-tokens.css** | 全局CSS文件：Tailwind CSS 4 `@theme`定义设计Token，CSS变量定义深浅主题颜色，老年模式字体/间距覆盖 | `app/globals.css` |
| **tailwind.config.ts** | Tailwind配置：扩展主题（颜色、字体、间距、断点、动画），配置深色模式为class策略 | `tailwind.config.ts` |

### 2.3 数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           应用初始化（app/layout.tsx）                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 1. useLocalStorage读取UI偏好：theme/sidebarCollapsed/rightPanelWidth │   │
│  │ 2. useViewport检测当前视口宽度→breakpoint                            │   │
│  │ 3. 初始化ThemeProvider：解析resolvedTheme（system→检测系统主题）      │   │
│  │ 4. 初始化LayoutProvider：设置侧边栏默认状态（平板默认折叠）           │   │
│  │ 5. 注入CSS变量class到<html>：theme（light/dark）、elderly-mode        │   │
│  └──────────────────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────────────────┼───────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LayoutProvider (Context)                          │
│  状态：                                                                     │
│  - theme: 'light'/'dark'/'system'                                           │
│  - resolvedTheme: 'light'/'dark'                                            │
│  - sidebarCollapsed: boolean                                                │
│  - rightPanelOpen: boolean                                                  │
│  - rightPanelContentType: RightPanelContentType                             │
│  - rightPanelWidth: number (320-500)                                        │
│  - rightPanelData: unknown                                                  │
│  - viewportWidth: number                                                    │
│  - breakpoint: 'desktop'/'small-desktop'/'tablet'/'mobile'                  │
│  - userRole: 'doctor'/'patient'/'guest'                                     │
│  - elderlyMode: boolean                                                     │
│                                                                             │
│  Actions：                                                                  │
│  - setTheme/toggleTheme, toggleSidebar, openRightPanel/closeRightPanel,     │
│  - setRightPanelWidth, setUserRole, toggleElderlyMode                       │
└─────────┬──────────────────┬──────────────────┬────────────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    Sidebar      │ │    ChatArea     │ │   RightPanel    │
│  - 折叠/展开    │ │  - 弹性宽度     │ │  - 滑入/滑出    │
│  - 响应式抽屉   │ │  - 自动滚动     │ │  - 拖拽宽度     │
│  - Tooltip      │ │  - 内容自适应   │ │  - 内容分发     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────┐
        │  状态变更后自动持久化到localStorage（防抖300ms）│
        │  - 主题切换、侧边栏折叠、面板宽度、老年模式   │
        └─────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        功能模块调用右侧面板示例                              │
│  ┌──────────────┐                                                           │
│  │ 五大处方模块 │ ──openRightPanel('prescription', reportData)──→ RightPanel │
│  │ CGA评估模块  │ ──openRightPanel('cga-assessment', questions)──→          │
│  │ 技能管理模块 │ ──openRightPanel('skills')──→                             │
│  │ 通用对话模块 │ ──openRightPanel('citations', citationList)──→            │
│  └──────────────┘                                                           │
│  PanelContentRenderer根据type渲染对应组件，数据通过rightPanelData传递       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. 接口设计

### 3.1 对外接口

| 接口 | 类型 | 参数 | 返回值 | 说明 |
|------|------|------|--------|------|
| `ThemeProvider` | React Context Provider | `children: ReactNode, defaultTheme?: ThemeMode, storageKey?: string` | - | 包裹应用根节点，提供主题上下文 |
| `useTheme()` | React Hook | 无 | `{ theme, resolvedTheme, setTheme, toggleTheme }` | 获取主题状态和切换方法 |
| `LayoutProvider` | React Context Provider | `children: ReactNode, defaultRole?: UserRole` | - | 包裹应用（在ThemeProvider内），提供布局上下文 |
| `useLayout()` | React Hook | 无 | `LayoutContextValue`（状态+所有actions） | 获取布局状态和操作方法 |
| `toggleSidebar()` | Context Action | 无 | `void` | 切换侧边栏折叠/展开，自动持久化；手机端切换抽屉显示/隐藏 |
| `openRightPanel(type, data?)` | Context Action | `type: RightPanelContentType, data?: unknown` | `void` | 打开右侧面板并显示指定类型内容，自动聚焦面板 |
| `closeRightPanel()` | Context Action | 无 | `void` | 关闭右侧面板，清空内容数据 |
| `setRightPanelWidth(width: number)` | Context Action | 宽度（像素，自动clamp到320-500） | `void` | 设置右侧面板宽度，拖拽时调用 |
| `toggleElderlyMode()` | Context Action | 无 | `void` | 切换老年模式开关，切换html根元素class |
| `setUserRole(role: UserRole)` | Context Action | `'doctor'/'patient'` | `void` | 切换用户角色，刷新页面应用对应主题色 |
| `useViewport()` | Custom Hook | 无 | `{ width, breakpoint, isMobile, isTablet, isDesktop }` | 获取当前视口宽度和断点信息 |
| `useLocalStorage<T>(key, initialValue)` | Custom Hook | storage key、默认值 | `[value, setValue, removeValue]` | localStorage读写封装，异常降级 |

**LayoutContextValue完整类型**：
```typescript
interface LayoutContextValue extends LayoutState {
  // 主题
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  
  // 侧边栏
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  
  // 右侧面板
  openRightPanel: (type: RightPanelContentType, data?: unknown) => void;
  closeRightPanel: () => void;
  setRightPanelWidth: (width: number) => void;
  
  // 角色与模式
  setUserRole: (role: UserRole) => void;
  toggleElderlyMode: () => void;
  setElderlyMode: (enabled: boolean) => void;
}
```

### 3.2 依赖接口

| 依赖 | 来源 | 用途 | 失败处理 |
|------|------|------|---------|
| Tailwind CSS 4 | npm包 `tailwindcss@4` | 原子化CSS、`@theme`定义Token、深色模式class策略 | 构建时依赖，失败则构建报错，开发阶段提前发现 |
| shadcn/ui | CLI初始化组件 | Tooltip、Button、Sheet（抽屉）、ResizablePanel（可选手写）、Switch、DropdownMenu | 组件不可用时降级为原生HTML元素，确保核心布局功能可用 |
| `window.matchMedia` | 浏览器原生API | 检测`prefers-color-scheme`和`prefers-reduced-motion` | 不支持matchMedia的旧浏览器回退到light主题、启用所有动画 |
| `window.localStorage` | 浏览器原生API | 布局偏好持久化 | 不可用时（隐私模式/禁用存储）降级为内存状态，仅控制台warn，功能正常但刷新丢失偏好 |
| `window.resize`事件 | 浏览器原生 | 视口宽度监听、响应式断点切换 | 使用debounce 150ms防止频繁触发；事件监听在组件unmount时清理，防止内存泄漏 |
| CSS Variables | 浏览器CSS支持 | 主题颜色、字体大小、间距等Token动态切换 | 不支持CSS变量的浏览器（IE11）不做兼容，PRD明确仅支持现代浏览器 |
| CSS Transforms/Transitions | 浏览器CSS | 侧边栏折叠、右侧面板滑入/滑出动画 | 检测`prefers-reduced-motion: reduce`时禁用所有transition和animation，瞬间切换 |
| 各功能模块（处方/CGA/技能等） | `components/prescription/`、`components/cga/`、`components/skills/` | 右侧面板内容渲染 | 对应模块未加载时显示空状态/加载中，不影响布局框架本身 |

## 4. 数据设计

### 4.1 localStorage存储结构（"数据库表"）

MVP无后端数据库，UI偏好存储在浏览器localStorage：

| Key | 结构 | 说明 |
|-----|------|------|
| `gerclaw_ui_preferences` | `UIPreferences` | UI布局偏好，单一key存储所有布局相关设置 |

**UIPreferences字段详解**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `theme` | `'light'/'dark'/'system'` | `'system'` | 主题模式；首次访问为system，手动切换后变为light/dark |
| `sidebarCollapsed` | `boolean` | `false`（桌面）/`true`（平板） | 侧边栏是否折叠；响应式断点变化时自动调整默认值但不覆盖用户手动设置 |
| `rightPanelWidth` | `number` | `380` | 右侧面板展开宽度，单位px，范围320-500 |
| `elderlyMode` | `boolean` | `true`（患者端）/`false`（医生端） | 老年模式开关；仅患者端可切换 |
| `userRole` | `'doctor'/'patient'` | `'patient'`（访客默认） | 当前用户角色；账号模式锁定不可切换 |
| `version` | `number` | `1` | 数据版本号，用于后续版本迁移 |

**存储策略**：
- 主题切换、侧边栏折叠/展开、右侧面板宽度拖拽结束、老年模式切换时，防抖300ms写入localStorage
- 右侧面板拖拽过程中只更新内存状态，不写入localStorage（拖拽结束mouseup时写入）
- 读取时校验数据合法性（如rightPanelWidth不在320-500范围则重置为380）
- 版本不兼容时重置为默认值，记录error日志

### 4.2 状态机

**主题状态机**：

```
system ──用户点击主题切换──→ light ──用户点击切换──→ dark ──用户点击切换──→ light
  │                           ↑                     │
  │                           │                     │
  └─系统主题变化→resolvedTheme变化                  └─系统主题变化不影响（用户手动选择后停止跟随）
  （仅theme=system时跟随）
```

**侧边栏状态机（桌面端）**：

```
expanded(270px) ──用户点击折叠按钮──→ collapsed(64px) ──用户点击展开按钮──→ expanded
      │                                                                    ↑
      │                                                                    │
      └─视口变化到tablet断点（自动折叠，但用户可手动展开）───────────────────┘
```

**侧边栏状态机（手机端）**：

```
hidden(0px, 抽屉关闭) ──用户点击汉堡按钮──→ open(270px, 抽屉滑入)
      ↑                                       │
      │                                       ├─用户点击遮罩层──→ hidden
      │                                       ├─用户点击菜单项──→ hidden
      └───────────────────────────────────────┴─用户点击关闭按钮──→ hidden
```

**右侧面板状态机**：

```
closed(0px, 隐藏) ──openRightPanel(type)──→ open(380px或用户保存宽度，滑入)
      ↑                                          │
      │                                          ├─用户点击×关闭按钮──→ closed
      │                                          ├─功能完成（如导出报告）→ closed（可选自动关闭）
      │                                          └─视口变化到mobile断点→ 变为全屏覆盖
      └──────────────────────────────────────────┘
```

**右侧面板宽度拖拽状态机**：

```
idle ──mousedown on resize handle──→ dragging
       ↑                              │
       │                              ├─mousemove → 更新width（实时预览，clamp 320-500）
       │                              │
       └──mouseup/mouseleave─── 保存width到localStorage
```

## 5. 错误处理

| 错误类型 | 处理方式 | 用户反馈 | 日志级别 |
|---------|---------|---------|---------|
| localStorage读取失败（隐私模式/损坏） | 降级为内存状态，使用默认值 | 无用户感知（功能正常，刷新后偏好重置）；仅控制台记录 | warn（含错误信息） |
| localStorage写入失败（QuotaExceeded） | 尝试清理不重要的缓存数据；仍失败则跳过写入，仅保留内存状态 | 无用户感知；如多次失败则显示toast提示"本地存储不可用，设置将在刷新后重置" | error |
| localStorage数据版本不兼容/损坏 | 捕获JSON.parse异常，重置为默认值 | 首次加载可能显示默认布局；控制台记录 | error |
| matchMedia API不支持（极旧浏览器） | 回退到light主题，不检测prefers-reduced-motion | 默认浅色主题，动画全部启用 | log |
| 拖拽右侧面板时鼠标移出窗口 | 监听document.mouseup，在mouseleave时也结束拖拽 | 拖拽正常结束，宽度保存到鼠标最后位置 | - |
| 视口resize时频繁触发 | 使用debounce 150ms，只在停止调整150ms后更新breakpoint | 无感知，布局平滑调整 | - |
| 面板内容模块加载失败（如处方组件报错） | ErrorBoundary包裹面板内容，显示错误状态+重试按钮 | 面板内显示"内容加载失败，点击重试"，不影响整体布局 | error |
| CSS过渡动画被中断（如快速连续折叠/展开侧边栏） | 使用CSS transition而非JS动画，浏览器自动处理中断；状态始终以React state为准 | 无视觉异常，最终状态正确 | - |
| 老年模式切换时样式异常 | 使用CSS类名整体切换（html.elderly-mode），不单独修改样式 | 样式正确应用；如发现异常刷新页面恢复 | error |

## 6. 测试策略

- **单元测试覆盖**：
  - `hooks/use-local-storage.ts`：读写、默认值、异常降级、版本迁移
  - `hooks/use-viewport.ts`：resize防抖、断点判断逻辑
  - `components/layout/theme-provider.tsx`：主题解析、system模式跟随逻辑、class注入
  - `components/layout/layout-context.tsx`：各action（toggleSidebar/openRightPanel/setRightPanelWidth）的状态更新、clamp逻辑
  - 工具函数：宽度clamp（320-500）、断点判断、localStorage序列化/反序列化

- **集成测试覆盖**：
  - 完整页面加载流程：读取localStorage→应用主题→渲染三栏布局→恢复折叠状态
  - 主题切换流程：点击切换按钮→CSS类变化→颜色更新→localStorage保存
  - 侧边栏折叠/展开流程：点击按钮→宽度变化→Tooltip显示→localStorage保存
  - 右侧面板流程：openRightPanel→面板滑入→拖拽调整宽度→关闭→面板滑出→宽度持久化
  - 响应式流程：缩放窗口→断点变化→自动收起侧边栏/面板→手机端抽屉模式
  - 老年模式切换：点击开关→字体放大→按钮变大→高对比度→localStorage保存

- **测试场景**：
  - **主流程**：
    - 首次访问页面（无localStorage）：默认system主题、侧边栏展开、右侧面板隐藏
    - 切换深色主题：页面立即变为深色，刷新后保持深色
    - 折叠侧边栏：宽度从270px变64px，hover图标显示Tooltip，刷新保持折叠
    - 打开右侧面板（点击技能管理）：面板滑入显示技能界面，拖拽到450px宽，关闭后面板隐藏，再次打开宽度保持450px
    - 切换到患者端：主色调变暖蓝，老年模式默认开启，字体变大
  - **失败路径1**：
    - 浏览器隐私模式（localStorage不可用）：布局功能正常，切换主题/折叠侧边栏都工作，刷新后恢复默认（控制台有warn）
  - **失败路径2**：
    - localStorage数据损坏（手动写入非法JSON）：重置为默认布局，控制台error日志，不崩溃
  - **边界情况**：
    - 右侧面板拖拽到<320px：自动停在320px，不能再缩小
    - 右侧面板拖拽到>500px：自动停在500px，不能再放大
    - 窗口缩放到手机宽度（<768px）：侧边栏自动隐藏，右侧面板全屏覆盖
    - 系统开启"减少动画"：所有折叠/展开/滑入动画消失，瞬间切换
    - 系统主题自动切换（如MacOS日落自动切深色）：theme=system时页面自动跟随变为深色
    - 快速连续点击折叠/展开按钮：最终状态与最后一次点击一致，无动画错乱
  - **无障碍测试**：
    - Tab键可遍历所有可交互按钮
    - Enter/Esc可操作按钮/关闭面板
    - 焦点环清晰可见
    - 颜色对比度检测：普通模式≥4.5:1，老年模式≥7:1

## 7. 安全考虑

- **XSS防护**：
  - 所有用户输入（会话标题、自定义技能名等）渲染时进行React自动转义，不使用`dangerouslySetInnerHTML`
  - 右侧面板内容通过React组件渲染，不直接注入HTML字符串
  - Tooltip内容为预定义的纯文本，不包含用户可控的HTML

- **localStorage安全**：
  - localStorage仅存储UI偏好（主题/折叠状态/宽度等），不存储敏感医疗数据、API Key、用户身份信息
  - 存储的数据进行合法性校验，防止JSON注入导致页面崩溃
  - 用户可通过"清除所有数据"功能清空localStorage

- **点击劫持防护**：
  - 部署时配置`X-Frame-Options: DENY`或`Frame-Options: SAMEORIGIN`（由部署平台IGA Pages保证）
  - 重要按钮（删除会话等，非本模块职责）需二次确认

- **无障碍安全**：
  - 颜色不仅靠色相区分，状态同时使用图标+文字（如成功不仅是绿色，还有✓图标）
  - 老年模式下颜色对比度≥7:1，符合WCAG AAA标准，避免色弱/视力障碍用户无法识别
  - 动画不闪烁（无快速频闪内容），老年模式下动画放慢，防止诱发癫痫等问题

- **API Key保护（本模块不涉及API调用，但需注意）**：
  - 本模块仅负责UI布局，不直接调用任何外部API
  - 主题配置、布局设置不包含任何敏感信息

## 8. 可观测性

- **日志（console）**：
  - `info`：应用初始化完成、主题切换、侧边栏折叠/展开、右侧面板打开/关闭
  - `warn`：localStorage不可用/读写失败、matchMedia不支持、数据版本不兼容使用默认值、面板内容加载降级
  - `error`：localStorage读写致命错误、面板内容组件崩溃（ErrorBoundary捕获）
  - 日志格式统一前缀：`[GerClaw][Layout]`，便于过滤

- **性能指标（开发阶段可选监控）**：
  - 首屏布局渲染时间（从初始化到首次paint）
  - 主题切换耗时（应<50ms，CSS变量切换无重排）
  - 侧边栏/面板动画帧率（应60fps）
  - resize事件处理耗时（防抖后<10ms）

- **开发工具提示**：
  - 开发模式下React DevTools可查看LayoutProvider和ThemeProvider状态
  - 开发模式下无效props（如rightPanelWidth超出范围）控制台warn提示

- **告警**：
  - 服务端异常进入结构化日志与 Trace/bad-case 闭环；前端不记录医疗正文或密钥
  - 关键布局错误（如ErrorBoundary捕获面板崩溃）显示用户可见的错误提示卡片，提供重试按钮

## 9. 技术选型说明

| 技术/库 | 用途 | 选型理由 | 替代方案 |
|---------|------|---------|---------|
| Tailwind CSS 4 | 样式框架、设计Token系统 | PRD指定；原子化CSS性能好；v4的`@theme`指令原生支持CSS变量定义主题，深浅主题切换无需重渲染；深色模式class策略灵活；断点响应式内置 | CSS Modules（需要手动管理主题类名和CSS变量，代码量大）、styled-components（运行时开销，SSR/SSG水合问题，主题切换可能闪烁）、UnoCSS（类似Tailwind但生态和shadcn/ui兼容性不如Tailwind） |
| shadcn/ui | 基础UI组件（Tooltip/Button/Switch/Sidebar Menu/Sheet） | PRD指定；无样式组件可完全定制Tailwind样式；基于Radix UI无障碍性好（键盘导航、ARIA属性）；Tooltip延迟显示、Sheet抽屉等组件开箱即用，无需手写交互逻辑 | Radix UI + 手动写样式（等同于shadcn但需要自己复制组件代码，效率低）、Headless UI（React生态但Tailwind集成度不如shadcn）、Ant Design（样式太重，定制困难，医疗风格不符） |
| React Context + useReducer | 布局状态管理 | 布局状态是全局低频更新（主题切换、面板开关等），Context足够；无需引入额外状态管理库；Provider嵌套简单（ThemeProvider + LayoutProvider两层） | Zustand（轻量但本模块状态更新不频繁，Context性能足够，引入额外库增加包体积）、Jotai/Redux（过重，MVP不需要） |
| CSS Variables（自定义属性） | 主题颜色/字体/间距Token | 原生CSS特性，性能最好；切换主题只需修改html根元素class，无需React重渲染整个组件树；无闪烁（水合前即可应用）；Tailwind CSS 4 `@theme`直接映射到CSS变量 | CSS-in-JS主题（运行时注入样式，性能差，SSR水合可能闪烁）、多套CSS文件（切换主题需要动态加载CSS，体验差） |
| CSS Transitions + Transform | 折叠/展开/滑入动画 | 性能好（GPU加速transform/width/opacity）；声明式CSS无需JS动画库；自动处理中断；可通过`prefers-reduced-motion`全局禁用 | Framer Motion（功能强大但包体积大~30KB，简单过渡动画不需要）、react-spring（物理动画，过于复杂） |
| 原生matchMedia API | 系统主题、减少动画检测 | 浏览器原生，无依赖；实时监听`prefers-color-scheme`变化；标准API | 无可靠替代，必须使用原生API |
| 原生localStorage | 偏好持久化 | PRD指定；浏览器原生API简单足够；键值对存储少量偏好数据（<1KB）性能好 | IndexedDB（复杂度高，存储几KB的偏好数据大材小用；二阶段用户系统再引入）、js-cookie（cookie有大小限制且每次请求携带，不适合） |
| 自定义useViewport hook + resize防抖 | 响应式断点检测 | Tailwind断点是CSS层面的，JS逻辑（如侧边栏默认折叠状态）需要JS获取当前断点；150ms防抖防止频繁重排 | react-use useMeasure（功能多但包体积大，只需要viewport宽度不需要元素尺寸）、@react-hook/resize-observer（监听元素尺寸而非窗口） |

## 10. 开放问题

- **Resizable Panel实现方式**：是手写拖拽逻辑（推荐，代码量小仅需监听mousedown/move/up）还是使用`react-resizable-panels`（shadcn/ui resizable组件依赖）？手写更轻量可控，但需要处理边界情况；使用库更稳定但增加包体积。倾向手写，因为右侧面板仅需单边拖拽，逻辑简单。
- **老年模式具体样式覆盖范围**：产品规格定义了字体/按钮/对比度/动画速度，但具体哪些组件需要放大（如工具卡片、引用角标、Tooltip文字）需要在实现阶段根据实际效果微调；已预留`.elderly-mode`全局类名，具体覆盖规则在globals.css中统一管理。
- **右侧面板内容切换动画**：不同类型内容切换时（如从技能管理切换到处方预览）是否需要过渡动画？还是直接替换？Trae Work中是直接替换，MVP先做直接替换，如体验不好再添加淡入淡出。
- **侧边栏手机端抽屉是否使用shadcn/ui Sheet组件**：shadcn Sheet内置了遮罩层、滑入动画、焦点管理、Esc关闭，无障碍性好；但需要确认样式是否能完全对齐设计规范，可能需要定制样式。优先使用shadcn Sheet，如样式定制困难再手写。
- **主题多图标切换**：主题切换按钮是仅显示太阳/月亮两个图标点击切换，还是点击后弹出下拉菜单选择浅色/深色/跟随系统？Trae Work是点击直接切换，长按或设置中选择system。MVP先做点击切换light↔dark，设置页面（二阶段）再添加system选项；system模式仅在首次访问默认启用，手动切换后停止跟随。
