---
layout: default
title: English Repository Guide
---

# English Repository Guide

## Top-level structure

```text
36kroutes/            raw released route folders
configs/              public configs
docs/                 GitHub Pages documentation
src/path_builder/     installable package
tests/                self-contained release tests
.github/              CI + issue templates
```

## Route-folder schema

Typical route folder:

```text
36kroutes/<city>/<difficulty>/<route_id>/
├── route.geojson
├── instructions.txt
├── natural_instructions.txt
└── instructions_parse.txt
```

## What each command family does

- `generate-routes`: build new route folders
- `generate-reverse`: call external LLM APIs
- `execute`: replay instructions on a street graph
- `score`: compute local route similarity

## Release engineering files

- `PUBLISHING.md`: push + Pages checklist
- `NOTICE.md`: third-party notice
- `CITATION.cff`: citation metadata
- `.github/workflows/ci.yml`: public CI

