"use client";

import { type FormEvent, useState } from "react";
import { Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { loginAccount, registerAccount, type AccountIdentity } from "@/services/account";

export function LoginPage({ onAuthenticated, onGuest }: { onAuthenticated: (identity: AccountIdentity) => void; onGuest: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"patient" | "doctor">("patient");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true); setError(null);
    try {
      onAuthenticated(mode === "login" ? await loginAccount(username, password) : await registerAccount(username, password, role));
    } catch {
      setError(mode === "login" ? "账号或密码不正确。" : "无法创建账户，请检查账号名和密码。 ");
    } finally { setPending(false); }
  }

  return <main className="min-h-screen bg-[radial-gradient(circle_at_top,_hsl(var(--primary)/0.12),transparent_38%),hsl(var(--background))] px-4 py-8 sm:grid sm:place-items-center">
    <Card className="mx-auto w-full max-w-md border bg-card/95 shadow-xl backdrop-blur">
      <CardHeader className="gap-3 text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-primary text-primary-foreground"><Stethoscope className="size-7" /></div>
        <CardTitle className="text-2xl tracking-tight">GerClaw</CardTitle>
        <CardDescription className="text-base">{mode === "login" ? "登录，或暂不登录进入患者服务" : "创建您的工作台账户"}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-2"><Label htmlFor="login-username">账号名</Label><Input id="login-username" autoComplete="username" minLength={3} maxLength={48} required value={username} onChange={(event) => setUsername(event.target.value)} className="min-h-12 text-base" /></div>
          <div className="grid gap-2"><Label htmlFor="login-password">密码</Label><Input id="login-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} className="min-h-12 text-base" /></div>
          {mode === "register" && <fieldset className="grid grid-cols-2 gap-2"><legend className="sr-only">账户身份</legend><Button type="button" variant={role === "patient" ? "default" : "outline"} className="min-h-12" onClick={() => setRole("patient")}>患者</Button><Button type="button" variant={role === "doctor" ? "default" : "outline"} className="min-h-12" onClick={() => setRole("doctor")}>医生</Button></fieldset>}
          {error && <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <Button className="min-h-12 text-base" type="submit" disabled={pending}>{pending ? "正在验证…" : mode === "login" ? "登录" : "创建账户"}</Button>
          <Button type="button" variant="ghost" className="min-h-12" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>{mode === "login" ? "创建账户" : "已有账户，去登录"}</Button>
          {mode === "login" && <Button type="button" variant="outline" className="min-h-12" onClick={onGuest}>暂不登录，进入患者服务</Button>}
        </form>
      </CardContent>
    </Card>
  </main>;
}
