export type FrontendModelId = "auto" | "doubao" | "deepseek" | "backup2";
export type BackendModelId = "primary" | "backup1" | "backup2" | "auto";

export interface ModelOption {
  id: FrontendModelId;
  label: string;
  supportsVision: boolean;
  backendId: BackendModelId;
}

export const MODEL_OPTIONS: ModelOption[] = [
  {
    id: "auto",
    label: "自动选择",
    supportsVision: false,
    backendId: "auto",
  },
  {
    id: "doubao",
    label: "豆包 Pro",
    supportsVision: true,
    backendId: "primary",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    supportsVision: true,
    backendId: "backup1",
  },
  {
    id: "backup2",
    label: "备用模型2",
    supportsVision: false,
    backendId: "backup2",
  },
];

export function mapFrontendToBackend(frontendId: FrontendModelId): BackendModelId {
  const option = MODEL_OPTIONS.find((m) => m.id === frontendId);
  return option?.backendId ?? "auto";
}

export function isModelAvailable(option: ModelOption): boolean {
  void option;
  // 可选模型由 BFF/FastAPI 的 server-only 配置与实际请求结果决定，浏览器不读取 Provider URL。
  return true;
}

export function getAvailableModels(): ModelOption[] {
  return MODEL_OPTIONS.filter(isModelAvailable);
}
