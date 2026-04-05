---
layout: default
title: English FAQ
---

# English FAQ

## Does this repository include model outputs?

No. It includes the route corpus, generation code, prompting adapters, Path Builder, and local scoring. Users call their own model APIs.

## Does this repository include `data_set/`?

No. The public release directory is intentionally scoped around `36kroutes/` and the code stack needed to work with it.

## Why are some route folders not fully populated?

The release preserves the raw corpus state instead of silently rewriting it during packaging.

## Do I need OpenRouteService for every workflow?

No. ORS is only needed when you generate new routes. It is not needed to inspect existing routes, call LLM APIs, execute instructions, or score routes.

## Do I need OpenAI or Gemini for every workflow?

No. External LLM APIs are only needed when you want to generate reverse instructions from the prompt adapters.

