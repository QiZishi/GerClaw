# GerClaw — 老年AI双向诊疗平台

面向老年患者和老年科医生的Web端AI双向诊疗平台，提供智能对话、CGA老年综合评估、五大处方生成、用药审查、语音交互等核心能力。

## 项目状态

**当前阶段**：规范构建完成，即将进入MVP开发

## 技术架构

### MVP阶段（当前）
- **前端**：Next.js 15 (App Router) + TypeScript + Tailwind CSS 4 + shadcn/ui
- **AI SDK**：Vercel AI SDK（流式SSE对话）
- **状态管理**：Zustand + localStorage持久化
- **部署**：静态导出 → IGA Pages
- **API直连**：前端直接调用LLM/ASR/TTS/Search/MinerU API，Key通过环境变量注入

### 二阶段（全栈）
- **前端**：Next.js（同上）
- **后端**：FastAPI + AgentScope多智能体框架
- **数据层**：PostgreSQL + Redis + Qdrant向量库
- **部署**：Docker容器化 → ModelScope创空间

## 快速开始（MVP）

```bash
# 克隆项目
cd gerclaw-main/apps/mvp

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env.local
# 编辑 .env.local 填入各API Key

# 启动开发服务器
npm run dev
```

## 文档导航

| 文档 | 说明 |
|------|------|
| [PRD.md](docs/PRD.md) | 产品需求文档（所有开发的准绳） |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构总览 |
| [PRODUCT_SENSE.md](docs/PRODUCT_SENSE.md) | 产品直觉和好坏判断 |
| [DESIGN.md](docs/DESIGN.md) | 视觉和交互设计规范 |
| [FRONTEND.md](docs/FRONTEND.md) | 前端开发规范 |
| [SECURITY.md](docs/SECURITY.md) | 安全规范 |
| [RELIABILITY.md](docs/RELIABILITY.md) | 可靠性规范 |
| [product-specs/](docs/product-specs/) | 11个模块的产品规格 |
| [design-docs/](docs/design-docs/) | 11个模块的技术设计文档 |
| [PLANS.md](docs/PLANS.md) | 当前开发计划 |
| [长期规划.md](docs/长期规划.md) | 长期进度总览 |
| [AGENTS.md](AGENTS.md) | AI智能体操作指南 |

## 铁律（不可违反）

1. **医疗安全底线**：禁止确定性诊断，所有医疗输出必须附带免责声明
2. **禁止阅读参考外目录**：严禁阅读gerclaw-main-origin和gerclaw-design-origin
3. **读规范后改代码**：未读对应规范不允许写代码
4. **真实执行验证**：所有命令必须实际运行，禁止空谈
5. **前端必验**：涉及前端的变更必须启动服务让用户手动测试

## 许可证

内部项目，版权所有。
