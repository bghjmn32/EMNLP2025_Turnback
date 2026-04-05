---
layout: default
title: English Quick Start
---

# English Quick Start

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

## Generate routes

```bash
path-builder generate-routes \
  --city Toronto_Canada \
  --easy 10 \
  --medium 10 \
  --hard 10 \
  --output-root tmp/generated_routes \
  --ors-api-key "$ORS_API_KEY"
```

## Generate reverse instructions

```bash
path-builder generate-reverse \
  --provider openai \
  --city "Toronto, Canada" \
  --input-file 36kroutes/Toronto_Canada/easy/0/natural_instructions.txt \
  --raw-output tmp/reverse_raw.txt \
  --clean-output tmp/reverse_clean.txt
```

## Execute with Path Builder

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

## Score locally

```bash
path-builder score \
  tmp/recovered_route.geojson \
  36kroutes/Toronto_Canada/easy/0/route.geojson \
  --config configs/similarity.paper.json
```

