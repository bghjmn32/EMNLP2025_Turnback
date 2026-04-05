# TurnBack

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![Conference](https://img.shields.io/badge/EMNLP-2025-8A2BE2)
![Dataset](https://img.shields.io/badge/Data-36kroutes-0A7EA4)
![Core](https://img.shields.io/badge/Core-Path%20Builder-1f883d)

English | [简体中文](README.zh-CN.md)

This repository is the public code and data release for **TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models through Reverse Route**.

The release is intentionally narrow and centered on four items:

1. `36kroutes/`: the released raw route collection
2. `Path Builder`: the route execution engine
3. route generation code for `easy / medium / hard`
4. reverse-instruction generation code for external LLM APIs

This repository does **not** depend on private benchmark splits, hidden graph caches, unpublished audit artifacts, or internal similarity services.

## What You Can Do

- inspect and reuse the released `36kroutes` corpus
- generate new pedestrian routes in three difficulty levels
- call your own OpenAI or Gemini API to create reverse instructions
- execute those instructions with Path Builder
- score recovered routes with the local similarity implementation

## Repository Layout

```text
.
├── 36kroutes/          # released route corpus
├── configs/            # public scoring configs
├── src/path_builder/   # Path Builder, generation, prompting, scoring
├── scripts/            # small maintenance and smoke-check scripts
├── tests/              # self-contained public test suite
├── README.md           # English README
├── README.zh-CN.md     # Chinese README
├── CITATION.cff        # citation metadata
└── pyproject.toml      # install + CLI entry points
```

## Quick Start

Install:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

Generate new routes:

```bash
path-builder generate-routes \
  --city Toronto_Canada \
  --easy 20 \
  --medium 20 \
  --hard 20 \
  --output-root tmp/generated_routes \
  --ors-api-key "$ORS_API_KEY"
```

Generate reverse instructions with your own API key:

```bash
path-builder generate-reverse \
  --provider openai \
  --city "Toronto, Canada" \
  --input-file 36kroutes/Toronto_Canada/easy/0/natural_instructions.txt \
  --raw-output tmp/reverse_raw.txt \
  --clean-output tmp/reverse_clean.txt
```

Execute with Path Builder:

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

## Data Snapshot

- cities: `13`
- route folders: `40,752`
- folders with populated `route.geojson`: `40,728`

The raw directory state is preserved as released rather than cosmetically rewritten.

## Included

- public route corpus
- public code for generation, prompting, execution, and scoring
- public configuration files
- public tests and CI

## Not Included

- `data_set/`
- unpublished audit manifests
- private APIs or internal services
- local frozen graph caches

## Validation

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
./scripts/smoke_release.sh
```

## Citation

If you use the code or data, please cite the TurnBack paper. Citation metadata is provided in [CITATION.cff](CITATION.cff).
