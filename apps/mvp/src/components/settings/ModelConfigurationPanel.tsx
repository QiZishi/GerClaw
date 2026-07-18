"use client";

import { useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { KeyRound, LoaderCircle, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { getModelConfiguration, saveModelConfiguration, type ModelSlot, type ServiceOverrides } from "@/services/model-configuration";
import { toast } from "@/components/ui/toast";

type Preference = ModelSlot["preference"];
type Draft = Omit<ModelSlot, "api_key"> & { api_key: string };
type SearchDraft = { anysearch_url: string; anysearch_api_key: string; tavily_url: string; tavily_api_key: string };
type VectorDraft = { url: string; api_key: string; embedding_model: string; rerank_model: string };
type VoiceDraft = { api_key: string; asr_url: string; asr_model: string; tts_url: string; tts_model: string; tts_voice: string };
type MinerUDraft = { url: string; api_key: string };

const SLOT_META: Array<{ preference: Preference; title: string; detail: string }> = [
  { preference: "primary", title: "主模型", detail: "优先处理新咨询与需要图像、工具或结构化输出的任务。" },
  { preference: "backup1", title: "备用模型 1", detail: "主模型在尚未产生可见结果前不可用时使用。" },
  { preference: "backup2", title: "备用模型 2", detail: "前两个模型都不可用时使用。" },
];

function emptyDraft(preference: Preference): Draft {
  return { preference, url: "", api_key: "", model_name: "", protocol: "openai", supports_image_input: true, supports_tool_calling: true, supports_structured_output: true };
}
function emptySearch(): SearchDraft { return { anysearch_url: "", anysearch_api_key: "", tavily_url: "", tavily_api_key: "" }; }
function emptyVector(): VectorDraft { return { url: "", api_key: "", embedding_model: "", rerank_model: "" }; }
function emptyVoice(): VoiceDraft { return { api_key: "", asr_url: "", asr_model: "", tts_url: "", tts_model: "", tts_voice: "" }; }
function emptyMinerU(): MinerUDraft { return { url: "", api_key: "" }; }
function hasValue(item: Record<string, string>) { return Object.values(item).some(Boolean); }

export function ModelConfigurationPanel({ senior }: { senior: boolean }) {
  const [revision, setRevision] = useState(0);
  const [drafts, setDrafts] = useState<Draft[]>(SLOT_META.map((item) => emptyDraft(item.preference)));
  const [search, setSearch] = useState<SearchDraft>(emptySearch);
  const [vector, setVector] = useState<VectorDraft>(emptyVector);
  const [voice, setVoice] = useState<VoiceDraft>(emptyVoice);
  const [mineru, setMineru] = useState<MinerUDraft>(emptyMinerU);
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
      const services = configuration.services;
      setSearch(services.search ? { anysearch_url: services.search.anysearch_url ?? "", anysearch_api_key: "", tavily_url: services.search.tavily_url ?? "", tavily_api_key: "" } : emptySearch());
      setVector(services.vector ? { url: services.vector.url, api_key: "", embedding_model: services.vector.embedding_model, rerank_model: services.vector.rerank_model } : emptyVector());
      setVoice(services.voice ? { api_key: "", asr_url: services.voice.asr_url, asr_model: services.voice.asr_model, tts_url: services.voice.tts_url, tts_model: services.voice.tts_model, tts_voice: services.voice.tts_voice } : emptyVoice());
      setMineru(services.mineru ? { url: services.mineru.url, api_key: "" } : emptyMinerU());
    }).catch(() => { if (active) toast.show("暂时无法读取模型配置"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const configuredCount = useMemo(() => {
    const models = drafts.filter((slot) => slot.url || slot.model_name || slot.api_key).length;
    return models + [search, vector, voice, mineru].filter(hasValue).length;
  }, [drafts, search, vector, voice, mineru]);
  const update = (preference: Preference, key: keyof Draft, value: string | boolean) => setDrafts((current) => current.map((item) => item.preference === preference ? { ...item, [key]: value } : item));
  const updateService = <T extends Record<string, string>>(setter: Dispatch<SetStateAction<T>>, key: keyof T, value: string) => setter((current) => ({ ...current, [key]: value }));
  const save = async () => {
    const selected = drafts.filter((slot) => slot.url || slot.model_name || slot.api_key);
    if (selected.some((slot) => !slot.url || !slot.model_name || !slot.api_key)) return toast.show("启用模型槽位时，请完整填写地址、模型名和 API Key");
    const services: ServiceOverrides = {};
    if (hasValue(search)) {
      if ((Boolean(search.anysearch_url) !== Boolean(search.anysearch_api_key)) || (Boolean(search.tavily_url) !== Boolean(search.tavily_api_key))) return toast.show("联网搜索的每个服务都需同时填写地址和 API Key");
      services.search = { ...(search.anysearch_url ? { anysearch_url: search.anysearch_url, anysearch_api_key: search.anysearch_api_key } : {}), ...(search.tavily_url ? { tavily_url: search.tavily_url, tavily_api_key: search.tavily_api_key } : {}) };
    }
    if (hasValue(vector)) {
      if (Object.values(vector).some((value) => !value)) return toast.show("Embedding 与 Rerank 服务需要完整填写");
      services.vector = vector;
    }
    if (hasValue(voice)) {
      if (Object.values(voice).some((value) => !value)) return toast.show("ASR/TTS 服务需要完整填写");
      services.voice = voice;
    }
    if (hasValue(mineru)) {
      if (!mineru.url || !mineru.api_key) return toast.show("MinerU 服务需要同时填写地址和 API Key");
      services.mineru = mineru;
    }
    setSaving(true);
    try {
      const saved = await saveModelConfiguration(revision, selected, services);
      setRevision(saved.revision);
      setDrafts(SLOT_META.map(({ preference }) => {
        const slot = saved.slots.find((item) => item.preference === preference);
        return slot ? { ...slot, api_key: "" } : emptyDraft(preference);
      }));
      setSearch(saved.services.search ? { anysearch_url: saved.services.search.anysearch_url ?? "", anysearch_api_key: "", tavily_url: saved.services.search.tavily_url ?? "", tavily_api_key: "" } : emptySearch());
      setVector(saved.services.vector ? { url: saved.services.vector.url, api_key: "", embedding_model: saved.services.vector.embedding_model, rerank_model: saved.services.vector.rerank_model } : emptyVector());
      setVoice(saved.services.voice ? { api_key: "", asr_url: saved.services.voice.asr_url, asr_model: saved.services.voice.asr_model, tts_url: saved.services.voice.tts_url, tts_model: saved.services.voice.tts_model, tts_voice: saved.services.voice.tts_voice } : emptyVoice());
      setMineru(saved.services.mineru ? { url: saved.services.mineru.url, api_key: "" } : emptyMinerU());
      toast.show("模型配置已安全保存，将用于新的咨询和服务调用");
    } catch { toast.show("保存失败；配置未被修改，请稍后重试"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="grid min-h-40 place-items-center text-sm text-muted-foreground"><LoaderCircle className="size-5 animate-spin" aria-hidden />正在读取配置…</div>;

  return <section aria-labelledby="model-config-title" className="space-y-4 border-t border-border pt-5">
    <div><h3 id="model-config-title" className={cn("flex items-center gap-2 font-semibold", senior && "text-lg")}><KeyRound className="size-5 text-primary" aria-hidden />模型与服务配置</h3><p className={cn("mt-1 text-sm leading-relaxed text-muted-foreground", senior && "text-base")}>未填写的服务继续使用部署默认值。密钥仅加密保存到当前账号，读取时不会回显。</p></div>
    {SLOT_META.map(({ preference, title, detail }) => {
      const slot = drafts.find((item) => item.preference === preference)!;
      return <fieldset key={preference} className="space-y-3 rounded-xl border border-border p-3"><legend className={cn("px-1 font-medium", senior && "text-lg")}>{title}</legend><p className={cn("text-xs leading-relaxed text-muted-foreground", senior && "text-base")}>{detail}</p><ConfigInput label="服务地址" value={slot.url} type="url" placeholder="https://api.example.com/v1" onChange={(value) => update(preference, "url", value)} guide="在模型服务商控制台的 API 文档中复制 Base URL。" senior={senior} /><ConfigInput label="API Key" value={slot.api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => update(preference, "api_key", value)} guide="在模型服务商控制台创建 API Key。密钥只会加密保存到当前账号。" senior={senior} /><ConfigInput label="模型名称" value={slot.model_name} placeholder="例如：gpt-4.1" onChange={(value) => update(preference, "model_name", value)} guide="填写服务商文档中的精确模型 ID，并确认所需能力可用。" senior={senior} /><label className={cn("grid gap-1 text-sm font-medium", senior && "text-base")}>接口协议<select value={slot.protocol} onChange={(event) => update(preference, "protocol", event.target.value)} className={cn("min-h-11 rounded-md border border-input bg-background px-3 font-normal", senior && "min-h-12 text-base")}><option value="openai">OpenAI 兼容</option><option value="dashscope">DashScope</option><option value="anthropic">Anthropic</option></select></label><Guide senior={senior}>OpenAI 兼容服务通常选择 OpenAI 兼容；阿里云百炼选择 DashScope；Anthropic 官方接口选择 Anthropic。</Guide></fieldset>;
    })}
    <ServiceCard title="联网搜索" detail="可分别配置 AnySearch 与 Tavily；只填写其中一个也可以。" senior={senior}><ConfigInput label="AnySearch 服务地址" value={search.anysearch_url} type="url" placeholder="https://api.anysearch.com" onChange={(value) => updateService(setSearch, "anysearch_url", value)} guide="在 AnySearch 控制台的 API 文档中复制服务地址。" senior={senior} /><ConfigInput label="AnySearch API Key" value={search.anysearch_api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => updateService(setSearch, "anysearch_api_key", value)} guide="在 AnySearch 控制台创建 API Key。" senior={senior} /><ConfigInput label="Tavily 服务地址" value={search.tavily_url} type="url" placeholder="https://api.tavily.com" onChange={(value) => updateService(setSearch, "tavily_url", value)} guide="在 Tavily API 文档中复制服务地址。" senior={senior} /><ConfigInput label="Tavily API Key" value={search.tavily_api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => updateService(setSearch, "tavily_api_key", value)} guide="在 Tavily 控制台创建 API Key。" senior={senior} /></ServiceCard>
    <ServiceCard title="Embedding 与 Rerank" detail="当前 RAG 适配器使用同一 OpenAI 兼容端点和密钥。" senior={senior}><ConfigInput label="服务地址" value={vector.url} type="url" placeholder="https://api.siliconflow.cn/v1" onChange={(value) => updateService(setVector, "url", value)} guide="从向量服务商 API 文档复制 OpenAI 兼容 Base URL。" senior={senior} /><ConfigInput label="API Key" value={vector.api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => updateService(setVector, "api_key", value)} guide="在向量服务商控制台创建 API Key。" senior={senior} /><ConfigInput label="Embedding 模型" value={vector.embedding_model} placeholder="例如：BAAI/bge-m3" onChange={(value) => updateService(setVector, "embedding_model", value)} guide="选择与当前知识库向量维度兼容的 Embedding 模型。" senior={senior} /><ConfigInput label="Rerank 模型" value={vector.rerank_model} placeholder="例如：BAAI/bge-reranker-v2-m3" onChange={(value) => updateService(setVector, "rerank_model", value)} guide="填写服务商支持的重排模型 ID。" senior={senior} /></ServiceCard>
    <ServiceCard title="语音服务" detail="同一兼容服务可提供语音识别与语音合成。" senior={senior}><ConfigInput label="语音 API Key" value={voice.api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => updateService(setVoice, "api_key", value)} guide="在语音服务商控制台创建 API Key。" senior={senior} /><ConfigInput label="ASR 服务地址" value={voice.asr_url} type="url" placeholder="https://api.example.com/v1" onChange={(value) => updateService(setVoice, "asr_url", value)} guide="从 ASR 服务文档复制兼容 API Base URL。" senior={senior} /><ConfigInput label="ASR 模型" value={voice.asr_model} placeholder="例如：mimo-v2.5-asr" onChange={(value) => updateService(setVoice, "asr_model", value)} guide="填写服务商提供的语音识别模型 ID。" senior={senior} /><ConfigInput label="TTS 服务地址" value={voice.tts_url} type="url" placeholder="https://api.example.com/v1" onChange={(value) => updateService(setVoice, "tts_url", value)} guide="从 TTS 服务文档复制兼容 API Base URL。" senior={senior} /><ConfigInput label="TTS 模型" value={voice.tts_model} placeholder="例如：mimo-v2.5-tts" onChange={(value) => updateService(setVoice, "tts_model", value)} guide="填写服务商提供的语音合成模型 ID。" senior={senior} /><ConfigInput label="TTS 音色" value={voice.tts_voice} placeholder="例如：冰糖" onChange={(value) => updateService(setVoice, "tts_voice", value)} guide="填写服务商允许的音色名称；当前语音适配器会校验可用音色。" senior={senior} /></ServiceCard>
    <ServiceCard title="MinerU 文档解析" detail="用于提取上传报告中的文本。" senior={senior}><ConfigInput label="MinerU 服务地址" value={mineru.url} type="url" placeholder="https://mineru.net/api/v1/agent" onChange={(value) => updateService(setMineru, "url", value)} guide="在 MinerU 开发者文档中复制 API 地址。" senior={senior} /><ConfigInput label="MinerU API Key" value={mineru.api_key} type="password" placeholder="已配置时请重新输入以修改" onChange={(value) => updateService(setMineru, "api_key", value)} guide="在 MinerU 控制台创建 API Token。" senior={senior} /></ServiceCard>
    <Button type="button" className={cn("w-full gap-2", senior && "min-h-12 text-base")} onClick={() => void save()} disabled={saving}>{saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Save className="size-4" aria-hidden />}{saving ? "正在保存…" : `保存模型配置${configuredCount ? `（${configuredCount} 项）` : ""}`}</Button>
  </section>;
}

function ServiceCard({ title, detail, senior, children }: { title: string; detail: string; senior: boolean; children: ReactNode }) { return <fieldset className="space-y-3 rounded-xl border border-border p-3"><legend className={cn("px-1 font-medium", senior && "text-lg")}>{title}</legend><p className={cn("text-xs leading-relaxed text-muted-foreground", senior && "text-base")}>{detail}</p>{children}</fieldset>; }
function Guide({ senior, children }: { senior: boolean; children: ReactNode }) { return <details className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground"><summary className={cn("cursor-pointer font-medium text-foreground", senior && "text-base")}>配置说明</summary><p className={cn("mt-2 leading-relaxed", senior && "text-base")}>{children}</p></details>; }
function ConfigInput({ label, value, type = "text", placeholder, onChange, guide, senior }: { label: string; value: string; type?: "text" | "url" | "password"; placeholder: string; onChange: (value: string) => void; guide: string; senior: boolean }) { return <div className="space-y-1"><label className={cn("grid gap-1 text-sm font-medium", senior && "text-base")}>{label}<Input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} autoComplete="off" className={cn("min-h-11 font-normal", senior && "min-h-12 text-base")} /></label><Guide senior={senior}>{guide}</Guide></div>; }
