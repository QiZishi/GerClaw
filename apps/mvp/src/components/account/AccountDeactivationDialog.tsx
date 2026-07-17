"use client";

import { type FormEvent, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { deactivateAccount } from "@/services/account";

export function AccountDeactivationDialog({
  open,
  onOpenChange,
  seniorMode,
  onDeactivated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
  onDeactivated: () => void;
}) {
  const [password, setPassword] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setPassword("");
      setUnderstood(false);
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !password || !understood) return;
    setPending(true);
    setError(null);
    try {
      await deactivateAccount(password);
      onDeactivated();
      handleOpenChange(false);
    } catch (requestError) {
      setError(requestError instanceof Error && requestError.message === "ACCOUNT_PASSWORD_INVALID"
        ? "当前密码不正确，请重新输入。"
        : "账户暂时无法停用，请稍后重试。"
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={cn("sm:max-w-md", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn("flex items-center gap-2 text-destructive", seniorMode && "text-2xl")}>
            <AlertTriangle className="size-5" /> 停用账户
          </DialogTitle>
          <DialogDescription className={textClass}>
            停用后您将立即退出，不能再使用这个账号登录。已保存的医疗数据不会因此删除。
          </DialogDescription>
        </DialogHeader>
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
            <p className={cn("font-medium", textClass)}>这不是删除医疗数据</p>
            <p className={cn("mt-1 text-muted-foreground", textClass)}>如需导出或删除数据，请等待相应功能上线后再操作。</p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="deactivate-password" className={cn(seniorMode && "text-lg")}>输入当前密码确认</Label>
            <Input id="deactivate-password" type="password" autoComplete="current-password" minLength={1} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} className={cn(seniorMode && "h-12 text-lg")} />
          </div>
          <label className={cn("flex items-start gap-3 rounded-lg border border-border p-3", textClass)}>
            <Checkbox checked={understood} onCheckedChange={(value) => setUnderstood(value === true)} className="mt-1" />
            <span>我已了解：停用后会立即退出，不能再使用这个账号登录。</span>
          </label>
          {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
          <DialogFooter className={cn("gap-2", seniorMode && "flex-row justify-end gap-3")}>
            <Button type="button" variant="outline" disabled={pending} className={cn(seniorMode && "min-h-12 text-lg")} onClick={() => handleOpenChange(false)}>取消</Button>
            <Button type="submit" variant="destructive" disabled={pending || !password || !understood} className={cn(seniorMode && "min-h-12 text-lg")}>
              {pending ? "正在停用…" : "确认停用账户"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
