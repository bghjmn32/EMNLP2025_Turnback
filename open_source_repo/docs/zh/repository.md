---
layout: default
title: 中文仓库导览
---

# 中文仓库导览

## 顶层结构

```text
36kroutes/            原始公开路线目录
configs/              公开配置
docs/                 GitHub Pages 文档
src/path_builder/     可安装包
tests/                自包含的发布测试
.github/              CI 与 issue 模板
```

## 路线目录结构

典型路线目录：

```text
36kroutes/<city>/<difficulty>/<route_id>/
├── route.geojson
├── instructions.txt
├── natural_instructions.txt
└── instructions_parse.txt
```

## 每类命令的作用

- `generate-routes`：生成新的路线目录
- `generate-reverse`：调用外部大模型 API
- `execute`：在街道图上回放指令
- `score`：计算本地路线相似度

## 发布工程相关文件

- `PUBLISHING.md`：推送与 Pages 开启清单
- `NOTICE.md`：第三方说明
- `CITATION.cff`：引用元信息
- `.github/workflows/ci.yml`：公开 CI

