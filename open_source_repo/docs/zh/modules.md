---
layout: default
title: 中文模块导览
---

# 中文模块导览

## 核心发布模块

### `execution.py`

实现 Path Builder，也就是把路线指令回放到街道图上的核心执行器。

### `generation.py`

实现城市图准备、路线采样、难度划分、ORS 接入以及 `easy / medium / hard` 三档路线输出。

### `prompting.py`

实现反转路线 prompt 构造、响应清洗，以及 OpenAI / Gemini 的 API 适配。

### `similarity.py`

实现公开版本使用的本地路线相似度评分器。

### `cli.py`

暴露公开命令行入口：

- `generate-routes`
- `generate-reverse`
- `execute`
- `score`

## 次级支撑模块

- `datasets.py`
- `instructions.py`
- `graphs.py`
- `evaluation.py`
- `paper.py`

这些模块仍保留在包中，用于数据加载、解析、缓存或兼容路径，即使它们不是本次发布叙事的中心。

