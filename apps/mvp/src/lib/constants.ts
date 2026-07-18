/**
 * 常量定义
 * 对齐 gerclaw设计要求.md §13 UI设计规范 / §4.16 通信协议
 */

/** §3.1 三栏布局尺寸 */
export const LAYOUT = {
  sidebar: {
    expanded: 272, // 260-280px 区间中值
    collapsed: 64, // 60-70px 区间中值
  },
  rightPanel: {
    default: 480,
    min: 200,
    max: 2000,
  },
} as const;

/** 输入限制 */
export const INPUT_LIMITS = {
  maxMessageLength: 4000, // 单次输入字符数
  maxFileCount: 10,
  maxFileSize: 10 * 1024 * 1024, // 10MB
  maxAudioDuration: 60, // 秒
  maxImageCount: 10,
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
export const PRESCRIPTION_COMPLETING_MAX_TURNS = 5;

/** 医疗安全：免责声明 */
export const MEDICAL_DISCLAIMER =
  "内容由 AI 生成，仅供参考。身体不适请及时就医。";
