"use client";

import { BookOpenCheck, CheckCircle2, FileText, MessageCircle, ShieldCheck, Stethoscope } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import type { Role } from "@/types";

type GuideSection = {
  title: string;
  steps: string[];
  icon: typeof MessageCircle;
};

const PATIENT_GUIDE: GuideSection[] = [
  {
    title: "开始一次咨询",
    icon: MessageCircle,
    steps: [
      "在输入框中描述您最想解决的问题；也可以使用“说话”录入语音。",
      "需要参考资料时，可上传图片或文件；图片和文档会显示为本次咨询的依据。",
      "回复生成时可以查看已执行时间；完成后可查看引用和对结果评价。",
    ],
  },
  {
    title: "完成健康服务",
    icon: FileText,
    steps: [
      "选择“五大处方计划”，在对话中逐步补齐资料；系统最多追问 5 轮后生成待医生复核的草案。",
      "选择“健康综合评估”，可随时保存并稍后继续；报告仅作筛查参考。",
      "在“我的健康记录”“我的慢病记录”和“我的安全提醒”查看自己的已保存信息。",
    ],
  },
  {
    title: "资料与安全",
    icon: ShieldCheck,
    steps: [
      "对话、上传资料和健康记录仅在当前账户范围内使用；匿名使用结束后不会在下次显示对话历史。",
      "五大处方草案需要您明确授权后，指定医生才可查看并给出复核意见。",
      "遇到严重或紧急不适，请优先联系急救服务或线下医疗机构，不要等待线上回复。",
    ],
  },
];

const DOCTOR_GUIDE: GuideSection[] = [
  {
    title: "建立病例会话",
    icon: MessageCircle,
    steps: [
      "使用“新建病例会话”记录当前诊疗辅助任务，并在对话中输入病情、用药或需要核对的问题。",
      "上传的图片、文件和检索结果会作为本次会话的证据；引用面板可查看来源。",
      "生成过程可取消或重试；完成后保留可追溯的会话与草案状态。",
    ],
  },
  {
    title: "使用授权患者资料",
    icon: Stethoscope,
    steps: [
      "在“患者列表”中选择已向您授予资料权限的患者；未授权、撤回或到期资料不会显示。",
      "健康画像、CGA 摘要和五大处方草案分别受独立授权控制，请只在相应工作区查看。",
      "五大处方草案可给出通过或退回意见；它始终是待复核草案，不会自动执行医疗操作。",
    ],
  },
  {
    title: "评估与用药审查",
    icon: BookOpenCheck,
    steps: [
      "CGA 工作区只显示已完成的筛查摘要，不显示原始作答。",
      "用药审查会返回已安装规则的命中依据与来源；请结合完整病史、检查和专业判断复核。",
      "系统建议和引用用于辅助决策，不替代临床诊断、处方签发或现场处置。",
    ],
  },
];

export function HelpPanel({ role }: { role: Role }) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isPatient = role === "patient";
  const sections = isPatient ? PATIENT_GUIDE : DOCTOR_GUIDE;
  const heading = isPatient ? "患者端使用教程" : "医生端使用教程";

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto max-w-md space-y-5">
        <section className="rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-start gap-3">
            <BookOpenCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
            <div>
              <h3 className={cn("font-semibold", isPatient && seniorMode && "text-xl")}>{heading}</h3>
              <p className={cn("mt-1 text-sm leading-relaxed text-muted-foreground", isPatient && seniorMode && "text-base")}>按下面顺序操作即可；当前页面只展示您这个端口可用的功能。</p>
            </div>
          </div>
        </section>

        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <section key={section.title} className="space-y-3 border-t border-border pt-5">
              <h4 className={cn("flex items-center gap-2 font-semibold", isPatient && seniorMode && "text-lg")}>
                <Icon className="size-5 text-primary" aria-hidden />
                {section.title}
              </h4>
              <ol className="space-y-3">
                {section.steps.map((step, index) => (
                  <li key={step} className="flex items-start gap-3">
                    <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold", isPatient && seniorMode && "size-7 text-sm")}>{index + 1}</span>
                    <span className={cn("text-sm leading-relaxed text-muted-foreground", isPatient && seniorMode && "text-base leading-7")}>{step}</span>
                  </li>
                ))}
              </ol>
            </section>
          );
        })}

        <section className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p className={cn("leading-relaxed", isPatient && seniorMode && "text-base")}>医疗相关内容仅供辅助参考；紧急症状请立即寻求线下医疗帮助。</p>
        </section>
      </div>
    </div>
  );
}
