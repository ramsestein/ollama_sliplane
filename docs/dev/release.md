# Release procedure — v0.2.0 (prepared, NOT executed)

This procedure is documented but **not run**. Run it only after the review is
complete and the open questions in `docs/dev/handoff.md` are resolved.

## 1. Pre-release checks

```bash
python -m pytest -q \
  --cov=src.secure --cov=src.proxy --cov-fail-under=85 --cov-report=term-missing
ruff check src tests eval
pip-audit -r requirements.txt
```

## 2. Tag and release

```bash
git checkout main
git tag -a v0.2.0 -m "Pukara v0.2.0"
git push origin v0.2.0
```

`pyproject.toml` reads the version from `src/__version__` (single source of
truth), currently `0.2.0`.

## 3. Zenodo

- The repository must be linked to a Zenodo record (GitHub ↔ Zenodo integration).
- `CITATION.cff` and `.zenodo.json` carry `TODO` markers for ORCIDs and the
  SoftwareX DOI; fill them before archiving.
- Draft a new version in Zenodo for tag `v0.2.0`, verify the metadata
  (authors, license MIT, version 0.2.0), and publish. The DOI is then added to
  the README metadata table (currently "Pending").

## 4. SoftwareX submission

- The DOI from step 3 goes into the SoftwareX manuscript metadata.
- `docs/dev/handoff.md` lists which claims in the future manuscript are backed
  by which `eval/results/*.json`.
