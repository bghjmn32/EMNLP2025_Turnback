## Summary

## Changes

## Validation

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
```

