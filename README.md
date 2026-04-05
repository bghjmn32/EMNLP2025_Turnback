# TurnBack

English | [简体中文](README.zh-CN.md)

Public release for **TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models through Reverse Route**.

This repository is intentionally narrow. It gives you exactly four practical pieces:

1. `36kroutes/`: the released raw route corpus
2. `path-builder execute`: the public Path Builder executor
3. `path-builder generate-routes`: the easy / medium / hard route generator
4. `path-builder generate-reverse`: the reverse-instruction generator for external LLM APIs

## Paper Overview

TurnBack studies **route reversal** as a concrete probe of geospatial cognition in large language models. A model receives forward navigation instructions and must produce a reverse route back to the start. We then use Path Builder to convert the predicted reverse instructions into geometry and compare that recovered route against the reference reverse route.

The paper contributes three pieces:

- a large-scale route-reversal benchmark introduced in the paper as `36,000` pedestrian routes over `12` metropolitan areas
- Path Builder, a language-to-route execution engine that turns navigation text back into street-level geometry
- a route-level evaluation protocol based on recovered geometry instead of only surface-form text overlap

![TurnBack pipeline](assets/route_generation.png)

## Quick Start

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

Generate new routes in three difficulty levels:

```bash
path-builder generate-routes \
  --city Toronto_Canada \
  --easy <NUM_EASY> \
  --medium <NUM_MEDIUM> \
  --hard <NUM_HARD> \
  --output-root tmp/generated_routes \
  --ors-api-key "$ORS_API_KEY"
```

Generate reverse instructions with your own LLM API key:

```bash
path-builder generate-reverse \
  --provider openai \
  --city "Toronto, Canada" \
  --input-file 36kroutes/Toronto_Canada/easy/<ROUTE_ID>/natural_instructions.txt \
  --raw-output tmp/reverse_raw.txt \
  --clean-output tmp/reverse_clean.txt
```

Execute the reversed instructions with Path Builder:

```bash
path-builder execute \
  --root 36kroutes \
  --city Toronto_Canada \
  --difficulty easy \
  <ROUTE_ID> \
  --instructions tmp/reverse_clean.txt \
  --executor hybrid \
  --output tmp/recovered_route.geojson
```

Score the recovered route against the reference route:

```bash
path-builder score \
  tmp/recovered_route.geojson \
  36kroutes/Toronto_Canada/easy/<ROUTE_ID>/route.geojson \
  --config configs/similarity.paper.json
```

## Main Findings

![Main benchmark results](assets/main_results.png)

- The paper introduces a `36,000`-route benchmark over `12` metropolitan areas and three difficulty levels.
- The paper reports that Path Builder reaches `96%` success in Toronto, `90%` in Tokyo, and `94%` in Munich.
- On a representative easy reversal example, no model returned exactly to the start; Gemini reached `73.4` similarity while Llama reached `22.6`.
- On `200` easy Toronto routes with GPT-4o, adding a vector map at inference time raised return rate from `6.4%` to `43.7%` and similarity from `41.06` to `73.08`.

## Why Is The Folder Still Named `36kroutes`?

`36kroutes` is the historical release name used in the paper. The directory currently published in this repository is a later raw release snapshot kept under the same name for continuity.

The paper-reported `36,000` routes refer to the benchmark definition in the paper. The repository keeps the historical `36kroutes` folder name for continuity across released data and code. Directory-level details are documented in [36kroutes/README.md](36kroutes/README.md).

## Repository Layout

```text
.
├── 36kroutes/                # released raw route corpus
├── assets/                   # figures reused from the paper
├── configs/similarity.paper.json
├── src/path_builder/         # Path Builder, route generation, prompting, scoring
├── scripts/quick_check.sh    # local smoke test
├── tests/                    # public test suite
├── README.md                 # English README
├── README.zh-CN.md           # Chinese README
├── CITATION.cff
└── pyproject.toml
```

## Quick Check

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
./scripts/quick_check.sh
```

## Citation

If you use the code or data, please cite the TurnBack paper. Citation metadata is provided in [CITATION.cff](CITATION.cff).
