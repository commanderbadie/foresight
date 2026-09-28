# Machine learning: formulation, pipeline, evaluation

## 1. Problem formulation

**Sprint spillover / task delay prediction (binary classification).**

> At snapshot time *T*, for an open task with a deadline, estimate **P(task is not finished by its deadline)**.

- **Training (TAWOS):** deadline = the planned end date of the sprint the issue was committed to.
  Snapshots at 0 %, 50 % and 75 % of each sprint, so the model sees tasks early *and* late in their window.
- **Live app:** deadline = the task's deadline; snapshot = now.
- Label: `1` if the issue's resolution date is missing or after the planned sprint end.

Why not regression (predict days late)? Most issues finish on time, so the target is zero-inflated and noisy;
a calibrated probability is easier to act on and to evaluate. Why not the originally proposed Kaggle datasets? They
are synthetic, off-domain, or lack timestamps (see `ANALYSIS.md`). Why not the Zenodo HRIS dataset? One company,
one year, 7.4 kB zipped — too small for a train/validation/test split, and already feature-engineered with
after-the-fact aggregates.

## 2. Features (all known at time T)

Defined once in `backend/app/core/features.py`, used by both training and serving.

| Feature | Meaning | App equivalent |
|---|---|---|
| story_points | estimate at T (reconstructed from change log) | story points |
| priority_rank | 1 low … 4 critical | priority |
| is_bug | issue type is Bug | task type |
| days_to_deadline | days left | same |
| window_days | sprint length / task window | start → deadline |
| elapsed_frac | share of window already used | same |
| assignee_open_points / _count | assignee's *other* open work at T | same |
| open_blockers | unfinished prerequisites (issue links) at T | dependencies |
| assignee_hist_late_rate | smoothed late rate from sprints **ended before** this one started | from finished tasks |
| project_hist_late_rate | same, whole project | same |
| age_days | days since creation | same |
| reassign_count | assignee changes before T | task_updates |
| desc_len_log | log(1+description length) | same |
| is_unassigned | no owner at T | same |

History rates use Bayesian smoothing `(late + 5·prior) / (n + 5)` so a person with 1 late task out of 1 is not "100 % late".

## 3. Leakage controls

| Risk | Control |
|---|---|
| `Issue.Sprint_ID` stores only the **last** sprint → spilled issues look on time | membership rebuilt from the `Sprint` change-log field |
| Final assignee / story points differ from values at T | reconstructed "as of T" from the change log |
| Issues added mid-sprint | included only in snapshots after they were added |
| Future outcomes in history features | only sprints that **ended before** the current sprint started |
| An overdue live task using its own outcome in its history rate | explicitly subtracted (`test_history_excludes_own_outcome`) |
| Random split mixes the same sprint into train and test | **chronological split by sprint** 70/15/15 |
| Resolution date, time spent, final status | used for the label only |
| Priority and type at final value | small residual risk — documented limitation |

The audit prints a red flag for any feature with |correlation with label| > 0.6.

## 4. Models and selection

Candidates: **heuristic baseline** (counts 5 warning signs a manager would check), logistic regression,
random forest, histogram gradient boosting. The winner is chosen on **validation PR-AUC** (the "late" class is what we
care about and is the minority), then **calibrated** on the validation set (sigmoid or isotonic), because the UI shows
probabilities. The test set is touched exactly once.

## 5. Metrics and thresholds

- PR-AUC (primary), ROC-AUC, Brier score (calibration), precision/recall/F1 at the HIGH threshold, confusion matrix,
  accuracy next to the majority-class baseline.
- **Thresholds are chosen on validation:** HIGH = lowest threshold with precision ≥ 0.60 (limits false alarms that
  would make managers ignore the tool); MEDIUM = highest threshold that still catches 80 % of late tasks.
  *Cost reasoning:* a missed delay (false negative) costs more than an unnecessary check-in (false positive), but a
  flood of false alarms destroys trust — hence two tiers.
- **Leave-one-project-out** results report generalisation to teams the model never saw.
- Calibration curve and global importance plots are written to `ml/reports/` and shown on the Model page.

## 6. Explainability

For each prediction we compute **reference-perturbation attributions**: replace one feature with its training median
and measure the change in predicted probability. This is model-agnostic (works through the calibration wrapper),
needs no extra dependency, is exact for the displayed model, and reads naturally:
*"if this task had a typical number of blockers, its risk would be 22 points lower."*
SHAP was considered; for 15 features and a calibrated ensemble it adds a dependency and is harder to explain to a
non-specialist without a clear gain, so it is left as an optional extension.

Tasks already past their deadline are labelled **overdue** and are *not* "predicted" (the outcome is known).

## 7. Decision gate and fallback

`audit_tawos.py` passes if the estimated number of snapshot rows ≥ 20 000 and the late rate is between 10 % and 70 %.
If it fails: (a) try the Montgomery *Public Jira Dataset* (MSR 2022) with the same pipeline, or (b) switch the target
to issues with explicit due dates, following Choetkiertikul et al. (ASE 2015 / EMSE 2017).

## 8. Reproducing
```bash
python ml/audit_tawos.py
python ml/build_tawos_snapshots.py
python ml/train.py
pytest ../ml/tests      # pipeline test on a fake TAWOS-shaped dataset
```

## References
- Tawosi, Moussa, Sarro. *A Versatile Dataset of Agile Open Source Software Projects.* MSR 2022.
- Montgomery et al. *An Alternative Issue Tracking Dataset of Public Jira Repositories.* MSR 2022.
- Choetkiertikul, Dam, Tran, Ghose. *Predicting delays in software projects using networked classification.* ASE 2015.
- Choetkiertikul et al. *Predicting the delay of issues with due dates in software projects.* EMSE 2017.
- Kurniawan, Aris Darmawan. HRIS Jira project dataset, Zenodo 16911234 (2025) — evaluated, not used for training.
