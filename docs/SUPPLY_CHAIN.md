# 供应链与许可证策略

`apps/api/uv.lock`、`apps/mvp/package-lock.json` 是唯一可提交的依赖解析事实源。生产 API 容器必须从锁定依赖构建，不能在 build 或运行时解析未锁定版本。

## Python 运行时 SBOM

先构建 production target，再从该镜像实际安装的 Python 包生成确定性的 CycloneDX 1.5 报告：

```bash
docker compose build api
python3 scripts/generate_runtime_sbom.py \
  --image gerclaw-api \
  --lock apps/api/uv.lock \
  --output output/sbom/gerclaw-api-runtime.cdx.json
```

报告记录 image ID、`uv.lock` SHA-256 和组件的包名、版本、PURL、可获得的许可证 metadata。它不包含时间戳或宿主机绝对路径，因此相同 image 与 lock 会生成相同内容。

当前报告范围仅为 API image 中 Python runtime packages；Debian base image 包、前端 npm runtime、容器基础镜像来源和许可证法律结论仍须由最终发布审查补齐。未知/非 SPDX 的许可证 metadata 被明确标记为 `gerclaw:license-status=unknown`，不得自动视作获批。

## 发布门禁

- 提交前运行 `scripts/quality-gate.sh security`，它执行 Bandit、锁定 Python 依赖的 `pip-audit`、前端 production 依赖的 high/critical `npm audit` 和生产 Python runtime SBOM 生成。
- 每次发布审查 SBOM 中新增/变更组件、已知漏洞与 `unknown` 许可证；AGPL、GPL、商业/专有条款或许可证缺失必须由法务书面批准后才可进入发布镜像。
- 依赖升级必须同时更新锁文件、SBOM 证据、漏洞扫描结果和本文件中任何适用例外；不得以扫描通过替代许可证审核。

截至 2026-07-17，`npm audit --omit=dev --audit-level=high` 通过；npm 同时报告 Next 内嵌 PostCSS 的 2 项 moderate advisory（GHSA-qx2v-qp2m-jg93）。建议的自动修复会将 Next 16 降至 9.x，属于破坏性降级，禁止自动执行；应在 Next 上游发布兼容修复后受控升级，并重新运行全量前端回归。
