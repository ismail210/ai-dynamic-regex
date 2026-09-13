# Human Review — A2 + A7

**Status:** Workflow ready · **no human judgments entered yet**

## How to review

```bash
cd backend
./venv/bin/python scripts/serve_human_review.py
# open http://127.0.0.1:8765/
```

- A2 tab: 70 unverified extract/group/op rows  
- A7 tab: 100 association links  
- Save progress anytime (writes only the review JSON files)  
- Resume by restarting the server (loads saved JSON)

## Datasets (do not overwrite originals)

| File | Role |
|---|---|
| `training/eval_cache_backups/accuracy_gold/june_16page_extract_group_gold.json` | A2 source gold (87) — **immutable for this workflow** |
| `training/eval_cache_backups/accuracy_gold/a2_human_review_70.json` | A2 review workspace (70) |
| `training/eval_cache_backups/accuracy_gold/june_association_gold.json` | A7 source gold (100) — **immutable** |
| `training/eval_cache_backups/accuracy_gold/a7_human_review_100.json` | A7 review workspace (100) |

## Finalize metrics

```bash
./venv/bin/python scripts/finalize_a2_human_review.py
./venv/bin/python scripts/finalize_a7_human_review.py
```

## Safety for reviewers

- Do **not** invent `L4X4`→thickness from the AISC catalog or Excel.
- Incomplete angles without drawing thickness → abstain.
- A7: judge **intended structural member**, not nearest line.

Production inference is unchanged by this tool.
