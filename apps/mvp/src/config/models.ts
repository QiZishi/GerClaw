export type FrontendModelId = "auto" | "doubao" | "deepseek" | "backup2";
export type BackendModelId = "primary" | "backup1" | "backup2" | "auto";

export interface ModelOption {
  id: FrontendModelId;
  label: string;
  supportsVision: boolean;
  backendId: BackendModelId;
  urlEnvKey: string;
}

export const MODEL_OPTIONS: ModelOption[] = [
  {
    id: "auto",
    label: "自动选择",
    supportsVision: false,
    backendId: "auto",
    urlEnvKey: "",
  },
  {
    id: "doubao",
    label: "豆包 Pro",
    supportsVision: true,
    backendId: "primary",
    urlEnvKey: "NEXT_PUBLIC_PRIMARY_URL",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    supportsVision: true,
    backendId: "backup1",
    urlEnvKey: "NEXT_PUBLIC_BACKUP1_URL",
  },
  {
    id: "backup2",
    label: "备用模型2",
    supportsVision: false,
    backendId: "backup2",
    urlEnvKey: "NEXT_PUBLIC_BACKUP2_URL",
  },
];

export function mapFrontendToBackend(frontendId: FrontendModelId): BackendModelId {
  const option = MODEL_OPTIONS.find((m) => m.id === frontendId);
  return option?.backendId ?? "auto";
}

export function getEnvValue(key: string): string | undefined {
  if (typeof window === "undefined") {
    return process.env[key];
  }
  return (process.env as Record<string, string | undefined>)[key];
}

export function isModelAvailable(option: ModelOption): boolean {
  if (option.id === "auto") return true;
  const url = getEnvValue(option.urlEnvKey);
  return !!url;
}

export function getAvailableModels(): ModelOption[] {
  return MODEL_OPTIONS.filter(isModelAvailable);
}
