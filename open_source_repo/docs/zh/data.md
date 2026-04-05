---
layout: default
title: 中文数据说明
---

# 中文数据说明

## `36kroutes/` 包含什么

公开发布包直接把原始路线语料放在仓库中。

当前快照：

- 城市数：`13`
- 路线文件夹总数：`40,752`
- 含 `route.geojson` 的已填充路线文件夹：`40,728`
- 含 `instructions.txt` 的已填充路线文件夹：`40,728`

## 为什么计数不同

本次发布明确保留原始语料布局。少量路线文件夹存在但并未完整填充路线文件。我们选择把这个状态公开说明，而不是在打包时静默修改语料。

## 城市列表

- Auckland_New_Zealand
- Cairo_Egypt
- Cape_Town_South_Africa
- Denver_Colorado_USA
- London_UK
- Mexico_City_Mexico
- Munich_Germany
- Paris_France
- Rio_de_Janeiro_Brazil
- Singapore_Singapore
- Sydney_Australia
- Tokyo_23_wards
- Toronto_Canada

## 路线目录结构

```text
36kroutes/<city>/<difficulty>/<route_id>/
├── route.geojson
├── instructions.txt
├── natural_instructions.txt
└── instructions_parse.txt
```

