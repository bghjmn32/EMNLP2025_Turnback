---
layout: default
title: English Module Map
---

# English Module Map

## Core release modules

### `execution.py`

Implements Path Builder, the graph-grounded executor that replays route instructions onto a street graph.

### `generation.py`

Implements city-graph preparation, route sampling, difficulty assignment, ORS integration, and output writing for `easy / medium / hard` routes.

### `prompting.py`

Implements reverse-route prompt construction, response cleaning, and API-provider adapters for OpenAI and Gemini.

### `similarity.py`

Implements the local route similarity scorer used in the public release.

### `cli.py`

Exposes the public command-line entry points:

- `generate-routes`
- `generate-reverse`
- `execute`
- `score`

## Secondary support modules

- `datasets.py`
- `instructions.py`
- `graphs.py`
- `evaluation.py`
- `paper.py`

These remain in the package because they support loading, parsing, caching, or compatibility paths, even when they are not the primary release story.

