---
layout: default
title: 中文总览
---

# 中文总览

## 项目目标

TurnBack 研究的是：大语言模型是否能够以真正“基于地图”的方式完成路线反转。这个公开发布包的组织目标，是让外部用户在不依赖内部工具的前提下，跑通可见的主流程。

## 公开发布范围

本包公开：

- 原始 `36kroutes/` 目录
- `Path Builder` 实现
- `easy / medium / hard` 三档步行路线生成代码
- 调用外部大模型 API 生成反转路线指令的代码
- 本地相似度评分实现

本包不把以下内容作为公开主线：

- 未公开 benchmark manifest
- 本地图缓存目录
- 内部相似度服务
- 私有 `data_set/`

## 主要技术模块

- `generation.py`：路线生成
- `prompting.py`：反转路线 prompt 与 provider 适配
- `execution.py`：Path Builder 执行
- `similarity.py`：公开本地相似度计算
- `cli.py`：面向用户的统一入口

## 面向公开用户的使用主线

1. 查看或生成路线目录
2. 使用外部模型生成反转指令
3. 用 Path Builder 执行
4. 在本地评分

## 为什么仓库拆成 README 和 docs

根目录 README 适合第一次打开仓库的读者。
`/docs` 站点适合 GitHub Pages 与更长篇的仓库说明。

