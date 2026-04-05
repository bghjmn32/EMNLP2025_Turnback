# TurnBack

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![Conference](https://img.shields.io/badge/EMNLP-2025-8A2BE2)
![Component](https://img.shields.io/badge/Core-Path%20Builder-1f883d)
![Release](https://img.shields.io/badge/Release-36kroutes%20%2B%20code-0A7EA4)

English | [简体中文](README.zh-CN.md)

This repository is the clean public release package for **TurnBack**, centered on four deliverables:

1. the released raw `36kroutes/` route collection
2. `Path Builder` for executing route instructions back onto a street graph
3. code for generating `easy / medium / hard` pedestrian routes
4. code for calling external LLM APIs to generate reverse instructions

The release deliberately keeps the scope narrow. It does **not** depend on internal similarity services, hidden graph caches, or unpublished audit artifacts.

中文简介：

本仓库是 **TurnBack** 的独立开源发布包，核心只保留四部分：

1. 已发布的原始 `36kroutes/` 路线集合
2. 用于把路线指令执行回街道图的 `Path Builder`
3. 生成 `easy / medium / hard` 三档步行路线的代码
4. 调用外部大模型 API 生成反转路线指令的代码

本次发布刻意收窄范围，不依赖内部相似度服务、隐藏图缓存或未公开的审计工件。

## Quick Links

- [English repository guide](README.en.md)
- [中文仓库说明](README.zh-CN.md)
- [GitHub Pages landing page](docs/index.md)
- [36kroutes data note](36kroutes/README.md)
- [Config note](configs/README.md)
- [Publishing checklist](PUBLISHING.md)
- [Contribution guide](CONTRIBUTING.md)
- [Third-party notice](NOTICE.md)

## Release Scope

Included:

- `36kroutes/`: released raw routes in city / difficulty / route-folder layout
- `src/path_builder/`: route generation, prompting, execution, graph handling, and scoring
- `configs/`: public similarity configs and related settings
- `tests/`: self-contained release test suite
- `docs/`: bilingual GitHub Pages documentation

Not included:

- `data_set/`
- private or internal similarity APIs
- cached OSM graphs
- unpublished audit manifests or private experiment outputs

## Data Snapshot

- cities: `13`
- route folders: `40,752`
- populated route folders with `route.geojson`: `40,728`

The release preserves the raw directory state rather than rewriting the corpus to force cosmetic consistency.

## Minimal Workflow

Install:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

Generate routes:

```bash
path-builder generate-routes \
  --city Toronto_Canada \
  --easy 20 \
  --medium 20 \
  --hard 20 \
  --output-root tmp/generated_routes \
  --ors-api-key "$ORS_API_KEY"
```

Generate reverse instructions with an external API:

```bash
path-builder generate-reverse \
  --provider openai \
  --city "Toronto, Canada" \
  --input-file 36kroutes/Toronto_Canada/easy/0/natural_instructions.txt \
  --raw-output tmp/reverse_raw.txt \
  --clean-output tmp/reverse_clean.txt
```

Execute reverse instructions with Path Builder:

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

Score the recovered route:

```bash
path-builder score \
  tmp/recovered_route.geojson \
  36kroutes/Toronto_Canada/easy/0/route.geojson \
  --config configs/similarity.paper.json
```

## Repository Layout

```text
open_source_repo/
├── 36kroutes/              # released raw route folders
├── configs/                # public configs
├── docs/                   # bilingual GitHub Pages
├── src/path_builder/       # main package
├── tests/                  # self-contained tests for the release package
├── .github/                # CI and issue templates
├── README.md               # bilingual landing page
├── README.en.md            # English long-form guide
├── README.zh-CN.md         # Chinese long-form guide
└── PUBLISHING.md           # git + GitHub Pages checklist
```

## GitHub Pages

This release includes a `/docs` site and a Jekyll config. After pushing this folder as a standalone repository:

1. open repository settings on GitHub
2. enable **Pages**
3. choose **Deploy from a branch**
4. select the `main` branch and `/docs`

The landing page is already prepared at [docs/index.md](docs/index.md).

## Citation

If you use the code or data, cite the TurnBack paper. A machine-readable citation file is provided in [CITATION.cff](CITATION.cff).

## Acknowledgement

This release presentation follows common patterns used by strong research-code repositories: a concise root README, separate documentation pages, self-contained CI, and explicit citation / notice files.
