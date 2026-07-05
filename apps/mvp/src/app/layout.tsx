import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/context/AppProvider";
import { Toaster } from "@/components/ui/toast";

export const metadata: Metadata = {
  title: "GerClaw 老年AI诊疗平台",
  description:
    "面向老年患者和老年科医生的Web端AI双向诊疗平台，以老年专科医生智能体为核心，提供语音优先的适老化交互和专业CGA评估/五大处方能力。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      data-scroll-behavior="smooth"
      className="h-full antialiased"
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col">
        <AppProvider>{children}</AppProvider>
        <Toaster />
      </body>
    </html>
  );
}
