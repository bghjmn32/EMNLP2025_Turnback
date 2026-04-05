# Publishing Checklist

## 1. Turn this folder into a standalone repository

```bash
cd open_source_repo
git init
git add .
git commit -m "Initial public release"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## 2. Enable GitHub Pages

1. open the repository on GitHub
2. go to `Settings -> Pages`
3. choose `Deploy from a branch`
4. select branch `main`
5. select folder `/docs`

The site entry point is [docs/index.md](docs/index.md).

## 3. What this release package already includes

- public README pages in English and Chinese
- GitHub Pages docs
- CI workflow
- issue templates
- citation and notice files
- source code, configs, release tests, and `36kroutes/`

## 4. Recommended pre-push checks

```bash
ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
```

## 5. Notes

- `36kroutes/` is large. The local preparation folder may use hard-linked files to avoid duplicate disk usage before publishing.
- This release package intentionally excludes `data_set/`, local graph caches, and unpublished audit artifacts.
