---
layout: default
title: English Release Policy
---

# English Release Policy

## What this package is optimized for

This package is optimized for a clear public route workflow:

1. raw route folders
2. route generation
3. reverse-instruction API calls
4. Path Builder execution
5. local scoring

## What it is not optimized for

This package is not presented as a full dump of every internal experiment artifact. That is deliberate.

We keep the public surface small so that:

- users can understand the repository quickly
- the code path is reproducible without hidden services
- the repository can be maintained as a real public codebase

## Why some legacy-compatible files remain

Some configs and modules remain to preserve CLI compatibility and avoid breaking already-refactored code paths. Their presence does not mean they are the primary public story.

