# Historical Struct.pdf baseline

Status: **NOT REPRODUCIBLE**.

The requested figures are 383/414 marks and 264 counted items. Those numbers were not found as an evaluation definition anywhere in this repository.

Searched:

- `backend/scripts/` for an evaluator that scores marks found against 414 expected marks.
- Docs and validation reports for `383/414`, `383 of 414`, and a counted-item total of 264 tied to a ground-truth file.
- `backend/tests/fixtures/schedule_answer_key/answer_key.json`. That file is a hand list of Furley schedule sections (C1–C6, L1–L4, and nulls for plates, lintels, piers, and footings). It is not a 414-mark set.

What does exist, and why it was not used as a substitute:

- `docs/DEPLOYMENT.md` says a live Struct.pdf analysis should match “1436 predictions, 62 quantity rows totalling 264.” That 264 is a quantity total under a different definition. There is no stored prediction file, expected-answer file, or command in the repo that reproduces 383/414. The prediction pipeline was not run, because a different metric would not be the historical comparison and because that run is outside this extraction fix.
- The current `schedule_mark_map` on `backend/uploads/Struct.pdf` has 12 sections. That count is not the 383/414 mark metric. It was unchanged by this task.

Missing, specifically:

1. The original evaluation script.
2. The expected-answer or historical-prediction file that defines the 414 marks and which 383 matched.
3. The methodology that defines “counted items” as 264, if that is not the deployment quantity total above.

No substitute ground truth was created.
