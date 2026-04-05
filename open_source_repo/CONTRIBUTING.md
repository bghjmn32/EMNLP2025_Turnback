# Contributing

## English

Thank you for considering a contribution.

Please keep pull requests aligned with the public release scope of this repository:

- `Path Builder`
- route generation
- reverse-instruction prompting adapters
- local similarity scoring
- documentation, tests, and packaging

Before opening a PR:

1. open an issue for large changes
2. keep the change narrow and reviewable
3. add or update tests when behavior changes
4. run:

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
```

## 中文

感谢你考虑为本仓库贡献代码。

请尽量让 PR 与本仓库的公开发布范围保持一致：

- `Path Builder`
- 路线生成
- 反转指令 prompt / provider 适配
- 本地相似度计算
- 文档、测试与打包

提交 PR 前建议：

1. 大改动先提 issue
2. 改动范围保持清晰、可审阅
3. 行为变化时补测试
4. 本地运行：

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
```

