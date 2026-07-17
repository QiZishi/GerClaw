"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { loginAccount, registerAccount, type AccountIdentity } from "@/services/account";

export function AccountDialog({
  open,
  onOpenChange,
  seniorMode,
  onAuthenticated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
  onAuthenticated: (identity: AccountIdentity) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"patient" | "doctor">("patient");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !username.trim() || !password) return;
    setError(null);
    setPending(true);
    try {
      const identity = mode === "login"
        ? await loginAccount(username, password)
        : await registerAccount(username, password, role);
      onAuthenticated(identity);
      onOpenChange(false);
      setPassword("");
    } catch {
      setError(mode === "login" ? "账号或密码不正确，请检查后重试。" : "无法创建账户。请检查账号名和密码要求后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("sm:max-w-md", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>{mode === "login" ? "登录账户" : "注册账户"}</DialogTitle>
          <DialogDescription className={cn(textClass)}>
            {mode === "login" ? "登录后会按账户身份打开对应端。医生账户尚未获得患者数据或临床权限。" : "账号名使用 3–48 位字母、数字、点、下划线或连字符；密码至少 12 位。"}
          </DialogDescription>
        </DialogHeader>
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          <div className="grid gap-2"><Label htmlFor="account-name" className={cn(seniorMode && "text-lg")}>账号名</Label><Input id="account-name" autoComplete="username" minLength={3} maxLength={48} pattern="[A-Za-z0-9][A-Za-z0-9_.\\-]{2,47}" required value={username} onChange={(event) => setUsername(event.target.value)} className={cn(seniorMode && "h-12 text-lg")} /></div>
          <div className="grid gap-2"><Label htmlFor="account-password" className={cn(seniorMode && "text-lg")}>密码</Label><Input id="account-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} className={cn(seniorMode && "h-12 text-lg")} /></div>
          {mode === "register" && <fieldset className="grid gap-2"><legend className={cn("font-medium", seniorMode && "text-lg")}>账户身份</legend><div className="grid grid-cols-2 gap-2"><Button type="button" variant={role === "patient" ? "default" : "outline"} className={cn(seniorMode && "min-h-12 text-lg")} onClick={() => setRole("patient")}>患者</Button><Button type="button" variant={role === "doctor" ? "default" : "outline"} className={cn(seniorMode && "min-h-12 text-lg")} onClick={() => setRole("doctor")}>医生</Button></div></fieldset>}
          {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
          <Button type="submit" disabled={pending || !username.trim() || !password} className={cn(seniorMode && "min-h-12 text-lg")}>{pending ? "正在验证…" : mode === "login" ? "登录" : "创建账户"}</Button>
          <Button type="button" variant="ghost" disabled={pending} onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }} className={cn(seniorMode && "min-h-12 text-lg")}>{mode === "login" ? "没有账户？注册" : "已有账户？登录"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
