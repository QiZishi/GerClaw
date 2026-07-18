# 011 — 将模型配置加载收敛为稳定状态反馈

- **Status**: DONE
- **Commit**: b194771
- **Severity**: MEDIUM
- **Category**: Purpose & frequency / accessibility / cohesion
- **Estimated scope**: 2 files, focused state-presentation change

## Problem

模型与服务配置是设置页面中可能持续数秒的读写操作，但它仍使用持续旋转图标。这既与
聊天主路径唯一的 Codex 三点运行指示冲突，也与已完成的 `InlineLoadingState` 约定不一致；
在老年模式下，旋转图标既没有解释请求状态，也没有告诉用户操作仍在进行。

```tsx
// apps/mvp/src/components/settings/ModelConfigurationPanel.tsx:104 — current
if (loading) return <div className="grid min-h-40 place-items-center text-sm text-muted-foreground"><LoaderCircle className="size-5 animate-spin" aria-hidden />正在读取配置…</div>;

// apps/mvp/src/components/settings/ModelConfigurationPanel.tsx:116 — current
<Button type="button" className={cn("w-full gap-2", senior && "min-h-12 text-base")} onClick={() => void save()} disabled={saving}>{saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Save className="size-4" aria-hidden />}{saving ? "正在保存…" : `保存模型配置${configuredCount ? `（${configuredCount} 项）` : ""}`}</Button>
```

## Target

读取态使用既有 `InlineLoadingState`，复用唯一的三点 CSS 和 `role="status"`
语义；保存态在保留禁用按钮、短文本和即时按压反馈的前提下使用静态保存图标，绝不再旋转。
不添加计时器、伪进度条、第二套 keyframe 或额外依赖。

```tsx
// target loading branch
if (loading) {
  return (
    <InlineLoadingState
      className="min-h-40 place-content-center text-sm"
      message="正在读取配置"
    />
  );
}

// target save action — static icon and explicit state text
<Button type="button" disabled={saving} ...>
  <Save className="size-4" aria-hidden="true" />
  {saving ? "正在保存配置" : `保存模型配置${configuredCount ? `（${configuredCount} 项）` : ""}`}
</Button>
```

`InlineLoadingState` 的三点在正常偏好下使用现有
`.codex-activity-dot` 的 `1.35s ease-in-out` 低频反馈；在
`prefers-reduced-motion: reduce` 下既有全局规则将其冻结为静态点，文字仍保留。

## Repo conventions to follow

- `apps/mvp/src/components/ui/inline-loading-state.tsx` 是由计划 010 引入的共享、无计时器状态组件；复用它，不复制三点标记或 CSS。
- `apps/mvp/src/app/globals.css:385-411` 定义了唯一 Codex 运行指示和 reduced-motion 回退。
- `apps/mvp/src/components/settings/ModelConfigurationPanel.tsx:100-101` 已经在保存失败时保留页面和可重试操作；不得改变此错误恢复语义。

## Steps

1. 在 `apps/mvp/src/components/settings/ModelConfigurationPanel.tsx` 移除 `LoaderCircle` import，改为导入 `InlineLoadingState`。将第 104 行的内联读取分支替换为上面的共享组件，保留 `min-h-40`，并根据 `senior` 维持不小于当前正文的可读字号。
2. 在相同文件的保存按钮中，删除 `animate-spin` 和旋转图标分支。保存中保留 `disabled={saving}`、静态 `Save` 图标及明确的“正在保存配置”文字；成功/失败 toast 和所有 API 调用不得变更。
3. 在 `plans/011-model-configuration-loading-feedback.md` 的 `Result` 小节记录实际 commit、测试命令与 reduced-motion 浏览器观察；将 `plans/README.md` 中计划 011 的状态改为 DONE。若目标组件 API 或路径与本计划不一致，停止并报告，不要复制实现。

## Boundaries

- 不修改模型、搜索、Embedding/Rerank、ASR、TTS 或 MinerU 配置的字段、加密、revision 或 API 调用。
- 不将保存按钮改为不可见、不可取消的全页遮罩，也不加入假进度或估算时间。
- 不改动现有错误 toast、密钥不回显保证、老年模式按钮高度、键盘焦点或表单校验。
- 不引入新的动画依赖、全局 spinner 覆盖或循环装饰动画。

## Verification

- **Mechanical**：在 `apps/mvp` 依次执行 `npm run lint`、`npm test`、`npm run build`，预期均通过。
- **Feel check**：打开“设置 → 模型与服务配置”，节流网络后确认读取态只显示三点与“正在读取配置”，不出现旋转图标、布局跳动或伪进度；点击保存后按钮立即变为禁用和“正在保存配置”，图标保持静态，完成后恢复可操作。
- **Reduced motion**：在 DevTools Rendering 启用 `prefers-reduced-motion: reduce`，重新打开页面；三点应静止，状态文字与成功/失败反馈仍可见，保存按钮仍有明确禁用状态。
- **Done when**：`ModelConfigurationPanel.tsx` 不再含 `LoaderCircle`、`animate-spin` 或自建循环动画，且读取/保存时的语义状态、表单行为和 API 请求不变。

## Result

- 已在 `apps/mvp/src/components/settings/ModelConfigurationPanel.tsx` 复用
  `InlineLoadingState` 作为读取态；该组件沿用唯一的 Codex 三点和静态
  reduced-motion 回退。
- 保存按钮保留原有禁用、校验、toast 和 API 调用，仅将旋转图标改为静态
  `Save` 图标与“正在保存配置”文字；组件中不再有 `LoaderCircle` 或
  `animate-spin`。
- 已执行 `npm run lint`、`npm test`、`npm run build`，均通过；以
  `GERCLAW_E2E_BASE_URL=http://127.0.0.1:3052 scripts/quality-gate.sh e2e`
  运行的 Playwright origin smoke 通过。该 smoke 验证登录入口可渲染且无
  browser origin 漂移，不伪称已用真实账户保存配置。
