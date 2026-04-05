# 36kroutes

English | 中文

## English

This directory contains the released raw route corpus.

Structure:

- one directory per city
- each city contains `easy/`, `medium/`, and `hard/`
- each difficulty bucket contains indexed route folders

Current snapshot:

- cities: `13`
- route folders: `40,752`
- folders with `route.geojson`: `40,728`
- folders with `instructions.txt`: `40,728`

That difference is preserved intentionally so the public release reflects the raw corpus layout exactly as shipped.

Main files per populated route folder:

- `route.geojson`
- `instructions.txt`
- `natural_instructions.txt`
- `instructions_parse.txt`

The public route-generation code that produces this style of directory lives in:

- `path_builder.generation`
- `path_builder.directions`

## 中文

该目录包含公开发布的原始路线语料。

结构：

- 每个城市一个目录
- 每个城市下包含 `easy/`、`medium/`、`hard/`
- 每个难度目录下包含按编号组织的路线文件夹

当前快照：

- 城市数：`13`
- 路线文件夹总数：`40,752`
- 含 `route.geojson` 的文件夹：`40,728`
- 含 `instructions.txt` 的文件夹：`40,728`

这里保留了原始发布状态，不会在发布准备阶段静默重写语料来“修整”统计数字。

每个已填充路线目录的主要文件：

- `route.geojson`
- `instructions.txt`
- `natural_instructions.txt`
- `instructions_parse.txt`

生成这种目录结构的公开代码位于：

- `path_builder.generation`
- `path_builder.directions`
