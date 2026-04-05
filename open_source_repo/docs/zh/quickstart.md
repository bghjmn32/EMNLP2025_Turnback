---
layout: default
title: 中文快速开始
---

# 中文快速开始

## 安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,llm]
```

## 生成路线

```bash
path-builder generate-routes \
  --city Toronto_Canada \
  --easy 10 \
  --medium 10 \
  --hard 10 \
  --output-root tmp/generated_routes \
  --ors-api-key "$ORS_API_KEY"
```

## 生成反转指令

```bash
path-builder generate-reverse \
  --provider openai \
  --city "Toronto, Canada" \
  --input-file 36kroutes/Toronto_Canada/easy/0/natural_instructions.txt \
  --raw-output tmp/reverse_raw.txt \
  --clean-output tmp/reverse_clean.txt
```

## 用 Path Builder 执行

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

## 本地打分

```bash
path-builder score \
  tmp/recovered_route.geojson \
  36kroutes/Toronto_Canada/easy/0/route.geojson \
  --config configs/similarity.paper.json
```

