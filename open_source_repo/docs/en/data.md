---
layout: default
title: English Data Note
---

# English Data Note

## What `36kroutes/` contains

The public release ships the raw route corpus directly in the repository.

Snapshot:

- cities: `13`
- route folders: `40,752`
- populated route folders with `route.geojson`: `40,728`
- populated route folders with `instructions.txt`: `40,728`

## Why the counts differ

The release preserves the raw corpus layout exactly as prepared for public release. A small number of route folders exist without fully populated route files. We keep that state explicit instead of silently mutating the corpus during packaging.

## City list

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

## Route-folder schema

```text
36kroutes/<city>/<difficulty>/<route_id>/
├── route.geojson
├── instructions.txt
├── natural_instructions.txt
└── instructions_parse.txt
```

