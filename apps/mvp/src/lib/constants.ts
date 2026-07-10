/**
 * 常量定义
 * 对齐 gerclaw设计要求.md §13 UI设计规范 / §4.16 通信协议
 */

/** §13.3 间距系统（4px 基准） */
export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
} as const;

/** §13.3 圆角系统 */
export const RADIUS = {
  sm: 4,
  md: 8,
  lg: 12,
  full: 9999,
} as const;

/** §13.4 阴影层级 */
export const SHADOW = {
  sm: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
  md: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
  lg: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
  xl: "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
} as const;

/** §13.5 动画时长 */
export const ANIMATION_DURATION = {
  fast: 150, // ms
  normal: 200,
  slow: 300,
  spin: 1000, // 旋转动画 1s
  pulse: 2000, // 脉冲动画 2s
} as const;

/** §13.7 适老化参数 */
export const SENIOR_MODE = {
  baseFontSize: 18, // px（普通模式 14px）
  titleFontSize: 28,
  heading1FontSize: 24,
  heading2FontSize: 22,
  minButtonSize: 48, // px（普通模式 32px）
  lineHeight: 1.8,
  animationScale: 0.7, // 动画速度 0.7x
  minContrastRatio: 7, // AAA 标准
} as const;

/** 普通模式参数 */
export const NORMAL_MODE = {
  baseFontSize: 14,
  titleFontSize: 24,
  heading1FontSize: 20,
  heading2FontSize: 18,
  minButtonSize: 32,
  lineHeight: 1.6,
  animationScale: 1,
  minContrastRatio: 4.5, // AA 标准
} as const;

/** §3.1 三栏布局尺寸 */
export const LAYOUT = {
  sidebar: {
    expanded: 272, // 260-280px 区间中值
    collapsed: 64, // 60-70px 区间中值
  },
  rightPanel: {
    default: 400,
    min: 320,
    max: 500,
  },
} as const;

/** §13.8 响应式断点 */
export const BREAKPOINTS = {
  mobile: 768,
  tablet: 1024,
  smallDesktop: 1280,
} as const;

/** API 超时（ms） */
export const API_TIMEOUT = {
  llm: 30_000, // LLM 流式首字 30s
  asr: 30_000,
  tts: 30_000,
  search: 15_000,
  document: 60_000,
} as const;

/** 重试配置 */
export const RETRY = {
  maxAttempts: 3,
  baseDelay: 1000, // 1s 指数退避基数
  maxDelay: 10_000,
} as const;

/** 输入限制 */
export const INPUT_LIMITS = {
  maxMessageLength: 4000, // 单次输入字符数
  maxFileCount: 5,
  maxFileSize: 10 * 1024 * 1024, // 10MB
  maxAudioDuration: 60, // 秒
  maxImageCount: 5,
  maxImageSize: 5 * 1024 * 1024, // 5MB
} as const;

/** 允许的图片 MIME 类型 */
export const ALLOWED_IMAGE_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
] as const;

/** 五大处方信息补全对话轮次上限（§6.4） */
export const PRESCRIPTION_COMPLETING_MAX_TURNS = 10;

/** 医疗安全：免责声明 */
export const MEDICAL_DISCLAIMER =
  "内容由 AI 生成，仅供参考。身体不适请及时就医。";

/** 高风险症状关键词（触发立即就医提示） */
export const HIGH_RISK_SYMPTOMS = [
  "胸痛",
  "呼吸困难",
  "意识丧失",
  "严重出血",
  "剧烈头痛",
  "言语障碍",
  "肢体无力",
  "持续高热",
] as const;

/** 紧急就医提示标题（高风险症状触发，对齐铁律5） */
export const EMERGENCY_ALERT = "检测到高风险症状，请立即就医";

/** z-index 层级（FRONTEND.md §6） */
export const Z_INDEX = {
  default: 0,
  sticky: 20,
  dropdown: 30,
  overlay: 40,
  modal: 50,
} as const;

/** 默认音色（§4.3.2 冰糖） */
export const DEFAULT_TTS_VOICE = "冰糖";

/** 患者端主色调（暖蓝 §13.1） */
export const PATIENT_PRIMARY_COLOR = "#0EA5E9";

/** 医生端主色调（冷蓝 §13.1） */
export const DOCTOR_PRIMARY_COLOR = "#2563EB";
