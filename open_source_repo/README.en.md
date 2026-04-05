# TurnBack Release Guide

## 1. What this repository is

This repository is a focused public release for the **TurnBack** project:

- a raw route collection named `36kroutes/`
- the `Path Builder` execution engine
- the public route-generation pipeline
- the reverse-instruction prompting pipeline for external LLM APIs

The release is intentionally narrower than the internal research workspace. It is designed for public readers who want to:

- inspect the raw route folders
- generate new routes at three difficulty levels
- call their own LLM APIs to reverse the route instructions
- execute the resulting instructions with Path Builder
- compute local similarity scores

## 2. What is intentionally not shipped

The release package does not require or foreground:

- the private `data_set/` benchmark split
- unpublished audit manifests
- internal similarity services
- local cache folders such as frozen OSM graph stores

If you only want the public release path, you do not need any of those artifacts.

## 3. Main user workflows

### A. Inspect released routes

Each route folder under `36kroutes/<city>/<difficulty>/<route_id>/` contains the route geometry and instruction files needed for public inspection and execution.

### B. Generate new routes

Use `path-builder generate-routes` with an OpenRouteService key. The generator can sample city graphs, propose candidate paths, classify them into `easy`, `medium`, and `hard`, and write a `36kroutes`-style directory tree.

### C. Generate reverse instructions

Use `path-builder generate-reverse` with an OpenAI or Gemini key. The repository only provides the prompt-building and provider-calling code; users bring their own models and keys.

### D. Execute reverse instructions

Use `path-builder execute` to replay reverse instructions onto an OSM graph using Path Builder.

### E. Score the result

Use `path-builder score` with `configs/similarity.paper.json` to compute local route similarity.

## 4. Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

If you only need the non-LLM stack:

```bash
pip install -e .[dev]
```

Environment variables:

- `ORS_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

An example file is provided as [.env.example](.env.example).

## 5. Release-oriented repository map

- `src/path_builder/cli.py`: public CLI entry point
- `src/path_builder/execution.py`: Path Builder core executor
- `src/path_builder/generation.py`: route-generation pipeline
- `src/path_builder/prompting.py`: reverse-route prompt and API-provider adapters
- `src/path_builder/similarity.py`: local similarity scorer
- `configs/`: public similarity and reproduction configs
- `docs/`: GitHub Pages content

Data note:

- `36kroutes/` contains `13` cities and `40,752` route folders.
- `40,728` of those folders currently contain populated `route.geojson` and instruction files.
- The release preserves that raw state explicitly.

## 6. Why this layout looks like a conference-code repository

The release package is organized around conventions that make public research repositories easier to navigate:

- a short root README
- longer language-specific guides
- a separate docs site for GitHub Pages
- a citation file
- contribution and issue templates
- a small CI pipeline that protects the public entry points

## 7. GitHub Pages

The documentation site is under `/docs`. After pushing this folder as a standalone repository, enable GitHub Pages from the `main` branch and `/docs`.

Prepared entry points:

- [Landing page](docs/index.md)
- [English overview](docs/en/overview.md)
- [English quick start](docs/en/quickstart.md)
- [English repository guide](docs/en/repository.md)
- [English data note](docs/en/data.md)
- [English module map](docs/en/modules.md)
- [English release policy](docs/en/release.md)
- [English FAQ](docs/en/faq.md)

## 8. Testing and CI

The release package ships with a self-contained test subset and a dedicated GitHub Actions workflow.

Run locally:

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
```

## 9. Citation and notice

- Citation metadata: [CITATION.cff](CITATION.cff)
- Third-party notice: [NOTICE.md](NOTICE.md)
- Publishing checklist: [PUBLISHING.md](PUBLISHING.md)
