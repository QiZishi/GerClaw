"use client";

import { Check, LockKeyhole, MonitorCog, Moon, Sun, Wifi, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useTheme } from "@/context/ThemeProvider";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Theme } from "@/types";

const THEME_OPTIONS: Array<{
  value: Theme;
  label: string;
  description: string;
  icon: typeof Sun;
}> = [
  { value: "light", label: "浅色", description: "高对比、适合日间使用", icon: Sun },
  { value: "dark", label: "深色", description: "降低夜间屏幕亮度", icon: Moon },
  { value: "system", label: "跟随设备", description: "随系统外观自动切换", icon: MonitorCog },
];

export function SettingsPanel() {
  const { theme, setTheme } = useTheme();
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const setSeniorMode = useAppStore((state) => state.setSeniorMode);
  const autoTtsPlayback = useAppStore((state) => state.autoTtsPlayback);
  const setAutoTtsPlayback = useAppStore((state) => state.setAutoTtsPlayback);
  const isOnline = useAppStore((state) => state.isOnline);
  const asrAvailable = useAppStore((state) => state.asrAvailable);
  const ttsAvailable = useAppStore((state) => state.ttsAvailable);
  const isPatient = role === "patient";
  const forceLightTheme = isPatient && seniorMode;

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto max-w-md space-y-6">
        <section aria-labelledby="appearance-title" className="space-y-3">
          <div>
            <h3 id="appearance-title" className="font-semibold">界面外观</h3>
            <p className={cn("mt-1 text-sm text-muted-foreground", forceLightTheme && "text-base leading-relaxed")}>选择看起来最舒服的显示方式。</p>
          </div>
          <div className="grid gap-2">
            {THEME_OPTIONS.map((option) => {
              const Icon = option.icon;
              const selected = forceLightTheme ? option.value === "light" : theme === option.value;
              const disabled = forceLightTheme && option.value !== "light";
              return (
                <Button
                  key={option.value}
                  type="button"
                  variant="outline"
                  onClick={() => setTheme(option.value)}
                  aria-pressed={selected}
                  disabled={disabled}
                  className={cn(
                    "h-auto justify-start gap-3 px-3 py-3 text-left",
                    forceLightTheme && "min-h-16 text-lg",
                    selected && "border-primary bg-primary/5"
                  )}
                >
                  <Icon className="size-5 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{option.label}</span>
                    <span className={cn("block whitespace-normal text-xs font-normal text-muted-foreground", forceLightTheme && "text-base leading-relaxed")}>{option.description}</span>
                  </span>
                  {selected && <Check className="size-4 shrink-0 text-primary" aria-hidden />}
                </Button>
              );
            })}
          </div>
          {forceLightTheme && (
            <p className="text-base leading-relaxed text-muted-foreground">适老模式固定使用浅色高对比界面；关闭适老模式后可选择其他外观。</p>
          )}
        </section>

        <section aria-labelledby="accessibility-title" className="space-y-3 border-t border-border pt-5">
          <div>
            <h3 id="accessibility-title" className="font-semibold">阅读与操作</h3>
            <p className={cn("mt-1 text-sm text-muted-foreground", isPatient && seniorMode && "text-base leading-relaxed")}>患者模式可开启大字、大按钮和更清楚的操作说明。</p>
          </div>
          <div className="flex min-h-14 items-center justify-between gap-4 rounded-xl border border-border px-3 py-2.5">
            <div>
              <div className="font-medium">适老模式</div>
              <div className={cn("text-xs text-muted-foreground", isPatient && seniorMode && "text-base")}>患者模式默认开启</div>
            </div>
            <Switch
              size={isPatient ? "lg" : "default"}
              checked={isPatient && seniorMode}
              onCheckedChange={setSeniorMode}
              disabled={!isPatient}
              aria-label="切换适老模式"
            />
          </div>
          {!isPatient && (
            <p className="text-xs text-muted-foreground">切换到患者模式后可调整适老模式。</p>
          )}
          {isPatient && seniorMode && (
            <div className="flex min-h-16 items-center justify-between gap-4 rounded-xl border border-border px-3 py-2.5">
              <div>
                <div className="text-lg font-medium">自动朗读回复</div>
                <div className="mt-1 text-base leading-relaxed text-muted-foreground">回答完成后自动开始朗读，您可以随时暂停、继续或停止。</div>
              </div>
              <Switch
                size="lg"
                checked={autoTtsPlayback}
                onCheckedChange={setAutoTtsPlayback}
                aria-label="切换自动朗读回复"
              />
            </div>
          )}
        </section>

        <section aria-labelledby="service-title" className="space-y-3 border-t border-border pt-5">
          <div>
            <h3 id="service-title" className="font-semibold">服务状态</h3>
            <p className={cn("mt-1 text-sm text-muted-foreground", isPatient && seniorMode && "text-base leading-relaxed")}>状态来自当前设备与本次会话，不代表医疗诊断结果。</p>
          </div>
          <dl className="divide-y divide-border rounded-xl border border-border">
            <StatusRow label="网络连接" available={isOnline} seniorMode={isPatient && seniorMode} />
            <StatusRow label="语音识别" available={isOnline && asrAvailable} seniorMode={isPatient && seniorMode} />
            <StatusRow label="语音朗读" available={isOnline && ttsAvailable} seniorMode={isPatient && seniorMode} />
          </dl>
        </section>

        <section className={cn("rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100", isPatient && seniorMode && "text-base leading-relaxed")}>
          <div className="flex items-start gap-2">
            <LockKeyhole className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div>
              <div className="font-medium">密钥由服务器安全管理</div>
              <p className="mt-1 leading-relaxed opacity-85">浏览器不会要求或保存模型、语音、搜索服务的 API Key。</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function StatusRow({ label, available, seniorMode }: { label: string; available: boolean; seniorMode: boolean }) {
  const Icon = available ? Wifi : WifiOff;
  return (
    <div className="flex min-h-12 items-center justify-between gap-3 px-3 py-2">
      <dt className={cn("text-sm font-medium", seniorMode && "text-base")}>{label}</dt>
      <dd className={cn("inline-flex items-center gap-1.5 text-sm", seniorMode && "text-base", available ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300") }>
        <Icon className="size-4" aria-hidden />
        {available ? "可用" : "暂不可用"}
      </dd>
    </div>
  );
}
