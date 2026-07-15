# GerClaw MVP Web

这是 GerClaw 的唯一功能性 Web 客户端：患者端、医生端与同源 Next.js BFF 都位于此目录。`apps/web` 预留给二阶段重构，当前不承载功能。

## 本地启动

先在仓库根目录从模板创建配置，并填入服务端凭证：

```bash
cp .env.example .env
```

`npm run dev`、`npm run build` 与 `npm run start` 会在 Node.js 进程内读取根目录 `.env`。`NEXT_PUBLIC_*` 会进入浏览器 bundle；因此只允许 `NEXT_PUBLIC_APP_NAME` 与 `NEXT_PUBLIC_APP_VERSION` 两个显示项，其他有值的公开变量一律拒绝启动。模型、MinerU、语音和 BFF 凭证必须保持 server-only。若需要真实文档解析，除 `MINERU_URL`、`MINERU_API_KEY` 外，必须配置 `MINERU_ALLOWED_HOSTS`，并只列出 MinerU API、签名上传和 Markdown 下载所需的 HTTPS 主机。

启动前端：

```bash
npm install
npm run dev
```

默认地址为 `http://127.0.0.1:3000`。`GERCLAW_API_URL` 指向 FastAPI；未配置或服务不可用时 BFF 应明确失败，不能显示伪成功。

## 验证

```bash
npm run lint
npm run test:audio
npm run test:document
npm run build
```

生产构建后可运行：

```bash
npm run start
```

## 交互底线

- 患者老年模式正文不小于 18px，操作控件不小于 48px，图标操作必须有可见文字或等价可访问名称。
- 读取、解析、保存和语音播放只使用稳定文字状态；不得循环闪烁、伪进度或用旋转图标代替操作反馈。
- 文档、语音、模型和搜索均只能通过 Next.js BFF/服务层调用；浏览器不可直连外部 Provider。

完整设计与行为规范见仓库根目录的 [`docs/FRONTEND.md`](../../docs/FRONTEND.md)。
