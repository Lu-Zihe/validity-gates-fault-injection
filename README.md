# Validity Gates for Fault-Injection Protocols in Robot Learning Simulations

Companion artifacts for the manuscript *"Auditing Fault-Injection Validity in Simulation-Based Robot Learning: A Three-Gate Verification Protocol and Its Effect on Conclusions"* (submitted to *Simulation Modelling Practice and Theory*).

This repository holds everything needed to re-run, or to check by hand, every number reported in the paper.

---

## What is here

| Directory | Contents | Paper section |
|---|---|---|
| `checker/` | The 66 executable assertions (60 basic + 6 meta) and their unit tests. CPU only, no GPU. | §4.5, Table 1 |
| `gates/` | Formal definition of the three gates, the defect-to-gate matrix, and `gate_check.py` which evaluates the gates on stored data. | §4.2–4.6, Table 2 |
| `mutation/` | The 21 semantic mutants, the runner, and per-mutant results. | §4.5, Fig. 4 |
| `audit/` | Repository audit: candidate list, pinned commit hashes, per-repository judgments, raw tool output. | §3.1–3.2, Figs. 3, S2 |
| `coding/` | Codebook and both coding tables for the two-coder agreement study, plus the agreement statistics. | §3.1, Fig. S1 |
| `data/` | Stored training and evaluation data used by `gate_check.py`. | §4.3–4.4, Fig. 6 |
| `experiment/` | Scripts and evaluation summaries for the controlled experiment (three seeds, five training budgets). | §5, Figs. 5, 7, 8 |
| `verify_numbers.py` | Recomputes the headline numbers from the files here and prints them next to the values reported in the paper. | §5, §6 |

A Chinese-language overview of the same material is kept in `README.zh.md`.

## Headline numbers and where they come from

| Number | Value | Reproduce with |
|---|---|---|
| Claimed vs measured injection rate | 10% vs 0.13%, a factor of 76.9 | `gates/gate_check.py --p1` |
| Post-fix injection rate | 8.94% | `experiment/data/` |
| Mutation score | 90.5% (19/21); 19/19 excluding 2 equivalent mutants | `mutation/mutation_results.csv` |
| Repository audit | 6 of 10 in the legged_gym lineage misroute the seed | `audit/audit_21repos.csv` |
| Two-coder agreement | 71% first round, 96% after the rules were written | `coding/` |
| Controlled experiment, seeds 42 / 7 / 2026 | +14.8 / +20.0 / +5.6 pp (mean 13.5) | `experiment/data/*.json` |
| Training-budget sweep | 100, 300, 500, 600, 800 iterations | `experiment/data/sens_iter.json` |

## Quick start

```bash
python -m pip install -r requirements.txt     # pandas only

# gates 2 and 3 run directly on the stored data (no GPU)
python gates/gate_check.py --p2               # -> PASS, window deltas -11.30 / -11.73 / -14.17
python gates/gate_check.py --p3               # -> FAIL, by design: this is the paper's own negative result

# gate 1 needs the training stack (legged_gym + Isaac Gym), which is NOT redistributed here;
# gate_check reports it as SKIP rather than FAIL in that case
python gates/gate_check.py --p1

# recompute the reported numbers
python verify_numbers.py
```

Expected output of `--p2`: `clip_mass_mean = 2.978`, `additivity_violations = 12` (0.2%),
window deltas of -11.30, -11.73 and -14.17 percent, matching §4.3 of the paper.

Expected output of `--p3`: all three arms fail the plateau test, matching §4.4 and Fig. 6.
The gate is reported as FAIL on purpose; the paper draws no conclusion from a comparison
that fails it.

## Reproducing the controlled experiment

```bash
cd experiment
bash scripts/one_arm.sh          # one arm, 500 resumed iterations
bash scripts/rr_seed.sh 7        # same design, a different seed
bash scripts/sensitivity.sh      # the 100 / 300 / 600 / 800 budget sweep
bash scripts/eval_sens.sh        # evaluates every budget point
```

Training needs Isaac Gym and a GPU. Evaluating a stored result takes about five minutes on a single card. Checkpoints are not included (several hundred MB); they are available from the authors on request.

## Scope and honesty notes

- The audit sample is **not** a random sample of the field. It was assembled by following code links from papers, so the 6/10 figure is a proportion **within the legged_gym lineage**, not an estimate for the field. See §3.1–3.2 of the paper.
- The two-coder agreement study used an independent session of the same underlying model as the second coder, not a human rater. It measures the *operability of the codebook*, not inter-human reliability.
- The controlled experiment covers one platform, one fault mode and three seeds. No claim of a general effect is made.
- The 66 checks and the mutation runner execute against the authors' training stack (`legged_gym` + Isaac Gym), which is not redistributed. Gate 1 therefore reports SKIP when that stack is absent. Gates 2 and 3, the audit and all reported numbers run without it.
- Several working notes under `mutation/` and `coding/` are written in Chinese. The code, the CSV schemas and the top-level documentation are in English; the numbers are language-neutral.

## License

Code is released under the MIT license (see `LICENSE`). Data under `data/`, `audit/`, `mutation/`, `coding/` and `experiment/` are released under CC BY 4.0.

## Citation

A `CITATION.cff` is provided. Please cite the paper rather than this repository once it is published.

## Review-time anonymity

This repository is served through an anonymized mirror during review. Author names, affiliation and contact details are withheld until acceptance.
