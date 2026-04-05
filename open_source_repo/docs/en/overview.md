---
layout: default
title: English Overview
---

# English Overview

## Project goal

TurnBack studies whether large language models can reverse route instructions in a map-grounded way. The public release package is organized so that outside users can run the visible pipeline without relying on internal tools.

## Public release scope

This package publishes:

- the raw `36kroutes/` directory
- the `Path Builder` implementation
- code to generate `easy`, `medium`, and `hard` pedestrian routes
- code to query external LLM APIs for reverse-route instructions
- local similarity scoring

This package does not foreground:

- unpublished benchmark manifests
- local cache folders
- internal similarity services
- the private `data_set/` split

## Main technical modules

- `generation.py`: route generation
- `prompting.py`: reverse-route prompts and provider adapters
- `execution.py`: Path Builder execution
- `similarity.py`: public local similarity scorer
- `cli.py`: user-facing entry point

## Intended public workflow

1. inspect or generate route folders
2. generate reverse instructions with an external model
3. execute them with Path Builder
4. score the recovered route locally

## Why the repository is split into README + docs

The root README is optimized for first contact.
The `/docs` site is optimized for GitHub Pages and longer repository explanations.

