# 36kroutes

English | 中文

## English

`36kroutes` is the historical corpus name used in the TurnBack paper. The directory currently published in this repository keeps that name for continuity, but the raw on-disk snapshot is larger than the original paper subset.

Current snapshot:

- city folders: `13`
- route folders: `40,752`
- populated route folders with `route.geojson`: `40,728`
- populated route folders with `instructions.txt`: `40,728`

Current city folders:

- `Auckland_New_Zealand`
- `Cairo_Egypt`
- `Cape_Town_South_Africa`
- `Denver_Colorado_USA`
- `London_UK`
- `Mexico_City_Mexico`
- `Munich_Germany`
- `Paris_France`
- `Rio_de_Janeiro_Brazil`
- `Singapore_Singapore`
- `Sydney_Australia`
- `Tokyo_23_wards`
- `Toronto_Canada`

The paper-reported benchmark refers to `36,000` routes across `12` cities. This release preserves the later raw corpus layout under the same historical folder name instead of renaming the directory after subsequent additions.

Compared with the exact paper benchmark description, the current raw release includes `Paris_France` and `Rio_de_Janeiro_Brazil`, while the paper text lists `São Paulo` and the current directory tree does not contain a `Sao_Paulo` folder.

Each populated route folder contains:

- `route.geojson`
- `instructions.txt`
- `natural_instructions.txt`
- `instructions_parse.txt`

The public route-generation code that writes this directory format lives under `path_builder.generation` and `path_builder.directions`.

## 中文

`36kroutes` 是 TurnBack 论文时期沿用下来的语料名称。当前仓库公开的这个目录保留了这个历史名字，但磁盘上的原始快照已经大于论文里的原始 36k 子集。

当前快照：

- 城市目录数：`13`
- 路线文件夹总数：`40,752`
- 含 `route.geojson` 的有效路线文件夹：`40,728`
- 含 `instructions.txt` 的有效路线文件夹：`40,728`

当前城市目录：

- `Auckland_New_Zealand`
- `Cairo_Egypt`
- `Cape_Town_South_Africa`
- `Denver_Colorado_USA`
- `London_UK`
- `Mexico_City_Mexico`
- `Munich_Germany`
- `Paris_France`
- `Rio_de_Janeiro_Brazil`
- `Singapore_Singapore`
- `Sydney_Australia`
- `Tokyo_23_wards`
- `Toronto_Canada`

论文中写的 benchmark 是 `12` 个城市、`36,000` 条路线。当前公开目录为了保持历史连续性，沿用了 `36kroutes` 这个名字，而不是在后续增补后重新命名。

和论文中精确定义的 benchmark 城市集合相比，当前原始发布目录包含 `Paris_France` 与 `Rio_de_Janeiro_Brazil`，而论文正文列出的 `São Paulo` 在当前目录树中并没有对应的 `Sao_Paulo` 文件夹。

每个有效路线目录包含：

- `route.geojson`
- `instructions.txt`
- `natural_instructions.txt`
- `instructions_parse.txt`

生成这种目录结构的公开代码位于 `path_builder.generation` 和 `path_builder.directions`。
