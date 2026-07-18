# GerClaw 初始医学知识库

`md/` 保存随仓库提供的初始医学 Markdown 语料，并保持“主题目录 / 文档”结构。新用户复制 `.env.example` 后，可以直接建立 RAG 索引：

```bash
python3 app.py --index-only --no-docker
```

Docker 用户执行：

```bash
./docker.sh index
```

如需替换或扩充语料，可保持相同目录结构，将 `GERCLAW_KNOWLEDGE_BASE_HOST_PATH` 改为其他宿主机目录。索引器会根据文件内容哈希执行新增、更新和删除。

这些语料包含来自不同发布机构和文献来源的医学资料。仓库代码许可证不自动改变原始资料的著作权或使用条件；公开发布、再分发或用于生产服务前，应由发布者核实每份资料的授权范围和有效性。
