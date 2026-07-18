"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, KeyRound, LoaderCircle, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { getModelConfiguration, saveModelConfiguration, type ModelSlot } from "@/services/model-configuration";
import { toast } from "@/components/ui/toast";

type Preference = ModelSlot["preference"];
type Draft = Omit<ModelSlot, "api_key"> & { api_key: string };

const SLOT_META: Array<{ preference: Preference; title: string; detail: string }> = [
  { preference: "primary", title: "主模型", detail: "优先处理新咨询与需要图像、工具或结构化输出的任务。" },
  { preference: "backup1", title: "备用模型 1", detail: "主模型在尚未产生可见结果前不可用时使用。" },
  { preference: "backup2", title: "备用模型 2", detail: "前两个模型都不可用时使用。" },
];

function emptyDraft(preference: Preference): Draft {
  return { preference, url: "", api_key: "", model_name: "", protocol: "openai", supports_image_input: true, supports_tool_calling: true, supports_structured_output: true };
}

export function ModelConfigurationPanel({ senior }: { senior: boolean }) {
  const [revision, setRevision] = useState(0);
  const [drafts, setDrafts] = useState<Draft[]>(SLOT_META.map((item) => emptyDraft(item.preference)));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    void getModelConfiguration().then((configuration) => {
      if (!active) return;
      setRevision(configuration.revision);
      setDrafts(SLOT_META.map(({ preference }) => {
        const saved = configuration.slots.find((slot) => slot.preference === preference);
        return saved ? { ...saved, api_key: "" } : emptyDraft(preference);
      }));
    }).catch(() => {
      if (active) toast.show("暂时无法读取模型配置");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const configuredCount = useMemo(() => drafts.filter((slot) => slot.url || slot.model_name || slot.api_key).length, [drafts]);
  const update = (preference: Preference, key: keyof Draft, value: string | boolean) => {
    setDrafts((current) => current.map((item) => item.preference === preference ? { ...item, [key]: value } : item));
  };
  const save = async () => {
    const selected = drafts.filter((slot) => slot.url || slot.model_name || slot.api_key);
    if (selected.some((slot) => !slot.url || !slot.model_name || !slot.api_key)) {
      toast.show("启用一个模型槽位时，请完整填写地址、模型名和 API Key");
      return;
    }
    setSaving(true);
    try {
      const saved = await saveModelConfiguration(revision, selected);
      setRevision(saved.revision);
      setDrafts(SLOT_META.map(({ preference }) => {
        const slot = saved.slots.find((item) => item.preference === preference);
        return slot ? { ...slot, api_key: "" } : emptyDraft(preference);
      }));
      toast.show("模型配置已安全保存，将用于新的咨询");
    } catch {
      toast.show("保存失败；配置未被修改，请稍后重试");
    } finally { setSaving(false); }
  };

  if (loading) return <div className="grid min-h-40 place-items-center text-sm text-muted-foreground"><LoaderCircle className="size-5 animate-spin" aria-hidden />正在读取配置…</div>;

  return (
    <section aria-labelledby="model-config-title" className="space-y-4 border-t border-border pt-5">
      <div>
        <h3 id="model-config-title" className={cn("flex items-center gap-2 font-semibold", senior && "text-lg")}><KeyRound className="size-5 text-primary" aria-hidden />模型配置</h3>
        <p className={cn("mt-1 text-sm leading-relaxed text-muted-foreground", senior && "text-base")}>未填写的槽位继续使用部署环境默认值。API Key 仅加密保存到当前账号，读取时不会回显。</p>
      </div>
      {SLOT_META.map(({ preference, title, detail }) => {
        const slot = drafts.find((item) => item.preference === preference)!;
        return <fieldset key={preference} className="space-y-3 rounded-xl border border-border p-3">
          <legend className={cn("px-1 font-medium", senior && "text-lg")}>{title}</legend>
          <p className={cn("text-xs leading-relaxed text-muted-foreground", senior && "text-base")}>{detail}</p>
          <ConfigInput label="服务地址" value={slot.url} type="url" placeholder="https://api.example.com/v1" onChange={(value) => update(preference, "url", value)} guide="填写服务商提供的 API Base URL；不要填写账号密码或带查询参数的临时链接。" senior={senior} />
          <ConfigInput label="API Key" value={slot.api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => update(preference, "api_key", value)} guide="在模型服务商控制台创建仅用于 API 调用的 Key。密钥不会显示、不会写入浏览器存储，也不会出现在对话或日志中。" senior={senior} />
          <ConfigInput label="模型名称" value={slot.model_name} placeholder="例如：gpt-4.1" onChange={(value) => update(preference, "model_name", value)} guide="填写服务商文档中的精确模型 ID；需要支持图片、工具或结构化输出时，请确认该模型具备相应能力。" senior={senior} />
          <label className={cn("grid gap-1 text-sm font-medium", senior && "text-base")}>接口协议<select value={slot.protocol} onChange={(event) => update(preference, "protocol", event.target.value)} className={cn("min-h-11 rounded-md border border-input bg-background px-3 font-normal", senior && "min-h-12 text-base")}><option value="openai">OpenAI 兼容</option><option value="dashscope">DashScope</option><option value="anthropic">Anthropic</option></select></label>
          <details className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground"><summary className={cn("cursor-pointer font-medium text-foreground", senior && "text-base")}>协议获取教程</summary><p className={cn("mt-2 leading-relaxed", senior && "text-base")}>OpenAI 兼容服务通常选择 OpenAI 兼容；阿里云百炼选择 DashScope；Anthropic 官方接口选择 Anthropic。保存前请以服务商当前文档为准。</p></details>
        </fieldset>;
      })}
      <Button type="button" className={cn("w-full gap-2", senior && "min-h-12 text-base")} onClick={() => void save()} disabled={saving}>
        {saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Save className="size-4" aria-hidden />}{saving ? "正在保存…" : `保存模型配置${configuredCount ? `（${configuredCount} 个槽位）` : ""}`}
      </Button>
    </section>
  );
}

function ConfigInput({ label, value, type = "text", placeholder, onChange, guide, senior }: { label: string; value: string; type?: "text" | "url" | "password"; placeholder: string; onChange: (value: string) => void; guide: string; senior: boolean }) {
  return <div className="space-y-1"><label className={cn("grid gap-1 text-sm font-medium", senior && "text-base")}>{label}<Input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} autoComplete="off" className={cn("min-h-11 font-normal", senior && "min-h-12 text-base")} /></label><details className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground"><summary className={cn("flex cursor-pointer items-center gap-1 font-medium text-foreground", senior && "text-base")}><ChevronDown className="size-4" aria-hidden />配置说明</summary><p className={cn("mt-2 leading-relaxed", senior && "text-base")}>{guide}</p></details></div>;
}
