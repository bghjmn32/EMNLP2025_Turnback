# TurnBack 开源发布说明

## 1. 这个仓库是什么

这个仓库是 **TurnBack** 的一个聚焦型公开发布版本，核心只保留四类内容：

- 名为 `36kroutes/` 的原始路线集合
- `Path Builder` 执行引擎
- 公开的三档路线生成代码
- 面向外部大模型 API 的反转指令生成代码

它不是内部研究工作区的完整镜像，而是为了让公开用户能够稳定完成以下任务：

- 查看和使用已发布的路线目录
- 生成新的 `easy / medium / hard` 三档路线
- 用自己的大模型 API 生成反转路线指令
- 用 Path Builder 执行这些指令
- 用本地相似度实现进行打分

## 2. 有意不随仓库发布的内容

这个发布包不会把以下内容作为公开主线：

- 私有或内部使用的 `data_set/`
- 未公开的 audit manifest
- 内部相似度服务
- 本地缓存目录，例如冻结 OSM 图缓存

如果你的目标只是使用公开版本的代码和 `36kroutes`，并不需要这些内容。

## 3. 主要使用流程

### A. 查看已发布路线

`36kroutes/<city>/<difficulty>/<route_id>/` 下的每个路线目录都包含公开检查和执行所需的几何与指令文件。

### B. 生成新路线

使用 `path-builder generate-routes` 配合 OpenRouteService key。生成器会在城市图上采样候选路径，并把结果写成 `36kroutes` 风格的目录结构。

### C. 生成反转指令

使用 `path-builder generate-reverse` 配合 OpenAI 或 Gemini key。仓库只提供 prompt 构造和 provider 调用逻辑，模型与密钥由用户自行提供。

### D. 执行反转指令

使用 `path-builder execute` 把反转指令回放到 OSM 图上，由 Path Builder 生成恢复路线。

### E. 路线打分

使用 `path-builder score` 配合 `configs/similarity.paper.json` 计算本地相似度分数。

## 4. 安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

如果你只需要非 LLM 栈：

```bash
pip install -e .[dev]
```

环境变量：

- `ORS_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

示例文件见 [.env.example](.env.example)。

## 5. 面向发布的仓库结构

- `src/path_builder/cli.py`：公开 CLI 入口
- `src/path_builder/execution.py`：Path Builder 核心执行器
- `src/path_builder/generation.py`：路线生成流程
- `src/path_builder/prompting.py`：反转路线 prompt 与 API provider 适配
- `src/path_builder/similarity.py`：本地相似度实现
- `configs/`：公开配置文件
- `docs/`：GitHub Pages 文档

数据说明：

- `36kroutes/` 包含 `13` 个城市和 `40,752` 个路线文件夹
- 其中 `40,728` 个文件夹目前包含实际的 `route.geojson` 与指令文件
- 本次发布明确保留这一原始状态

## 6. 为什么这个仓库长这样

这个发布包参考了成熟研究代码仓的常见组织方式：

- 根目录 README 保持高信息密度
- 中英文长文档分开维护
- 单独提供 GitHub Pages 文档页
- 提供 citation 文件
- 提供 issue / PR 模板
- 提供只保护公开入口的轻量 CI

## 7. GitHub Pages

文档站点位于 `/docs`。将本目录作为独立仓库推送后，在 GitHub 设置中把 Pages 指向 `main` 分支的 `/docs` 即可。

已准备好的页面入口：

- [Landing page](docs/index.md)
- [中文总览](docs/zh/overview.md)
- [中文快速开始](docs/zh/quickstart.md)
- [中文仓库导览](docs/zh/repository.md)
- [中文数据说明](docs/zh/data.md)
- [中文模块导览](docs/zh/modules.md)
- [中文发布政策](docs/zh/release.md)
- [中文 FAQ](docs/zh/faq.md)

## 8. 测试与 CI

本发布包附带一套自包含测试子集和独立 GitHub Actions 工作流。

本地运行：

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
```

## 9. 引用与第三方说明

- 引用信息：[CITATION.cff](CITATION.cff)
- 第三方说明：[NOTICE.md](NOTICE.md)
- 发布清单：[PUBLISHING.md](PUBLISHING.md)
