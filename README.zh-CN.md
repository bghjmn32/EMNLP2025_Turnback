# TurnBack

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![Conference](https://img.shields.io/badge/EMNLP-2025-8A2BE2)
![Dataset](https://img.shields.io/badge/Data-36kroutes-0A7EA4)
![Core](https://img.shields.io/badge/Core-Path%20Builder-1f883d)

[English](README.md) | 简体中文

本仓库是 **TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models through Reverse Route** 的公开代码与数据发布版本。

这次公开发布只保留四类核心内容：

1. `36kroutes/`：公开发布的原始路线集合
2. `Path Builder`：路线执行引擎
3. `easy / medium / hard` 三档路线生成代码
4. 面向外部大模型 API 的反转指令生成代码

本仓库**不依赖**私有 benchmark split、隐藏图缓存、未公开 audit 工件或内部相似度服务。

## 你可以用这个仓库做什么

- 查看和复用 `36kroutes` 原始路线语料
- 生成新的三档步行路线
- 用自己的 OpenAI 或 Gemini key 生成反转指令
- 用 Path Builder 执行这些指令
- 用本地相似度实现对恢复路线打分

## 仓库结构

```text
.
├── 36kroutes/          # 已发布路线语料
├── configs/            # 公开评分配置
├── src/path_builder/   # Path Builder、生成、prompting、评分
├── scripts/            # 维护脚本与 smoke check
├── tests/              # 自包含公开测试集
├── README.md           # 英文 README
├── README.zh-CN.md     # 中文 README
├── CITATION.cff        # 引用信息
└── pyproject.toml      # 安装与 CLI 入口
```

## 快速开始

安装：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

生成新路线：

```bash
path-builder generate-routes \
  --city Toronto_Canada \
  --easy 20 \
  --medium 20 \
  --hard 20 \
  --output-root tmp/generated_routes \
  --ors-api-key "$ORS_API_KEY"
```

用你自己的 API key 生成反转指令：

```bash
path-builder generate-reverse \
  --provider openai \
  --city "Toronto, Canada" \
  --input-file 36kroutes/Toronto_Canada/easy/0/natural_instructions.txt \
  --raw-output tmp/reverse_raw.txt \
  --clean-output tmp/reverse_clean.txt
```

用 Path Builder 执行：

```bash
path-builder execute \
  --corpus 36kroutes \
  --root 36kroutes \
  --city Toronto_Canada \
  --difficulty easy \
  0 \
  --instructions tmp/reverse_clean.txt \
  --executor hybrid \
  --output tmp/recovered_route.geojson
```

对恢复路线打分：

```bash
path-builder score \
  tmp/recovered_route.geojson \
  36kroutes/Toronto_Canada/easy/0/route.geojson \
  --config configs/similarity.paper.json
```

## 数据概况

- 城市数：`13`
- 路线文件夹数：`40,752`
- 含实际 `route.geojson` 的文件夹数：`40,728`

仓库保持原始发布状态，不会为了表面一致性去改写原始目录。

## 仓库中包含什么

- 公开路线语料
- 公开的生成、prompting、执行、评分代码
- 公开配置文件
- 公开测试与 CI

## 仓库中不包含什么

- `data_set/`
- 未公开 audit manifest
- 私有 API 或内部服务
- 本地冻结图缓存

## 验证

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
./scripts/smoke_release.sh
```

## 引用

如果你使用了代码或数据，请引用 TurnBack 论文。引用元信息见 [CITATION.cff](CITATION.cff)。
