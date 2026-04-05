# 36kroutes

English | 中文

## English

`36kroutes` is the historical corpus name used in the TurnBack paper. The directory currently published in this repository keeps that name for continuity, but the raw on-disk snapshot is larger than the original paper subset.

The paper-reported benchmark refers to `36,000` routes across `12` cities. This repository keeps the historical `36kroutes` name so the released code and data remain aligned with the paper terminology.

Each populated route folder contains:

- `route.geojson`
- `instructions.txt`
- `natural_instructions.txt`
- `instructions_parse.txt`

The public route-generation code that writes this directory format lives under `path_builder.generation` and `path_builder.directions`.

## 中文

`36kroutes` 是 TurnBack 论文时期沿用下来的语料名称。当前仓库公开的这个目录保留了这个历史名字，但磁盘上的原始快照已经大于论文里的原始 36k 子集。

论文中写的 benchmark 是 `12` 个城市、`36,000` 条路线。仓库继续使用 `36kroutes` 这个历史名称，是为了让已发布的数据和代码与论文术语保持一致。

每个有效路线目录包含：

- `route.geojson`
- `instructions.txt`
- `natural_instructions.txt`
- `instructions_parse.txt`

生成这种目录结构的公开代码位于 `path_builder.generation` 和 `path_builder.directions`。
