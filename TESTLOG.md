# Roblox Up-and-Coming forecaster — build & test log (2026-11-11)

Bounty: make.fun "Predict Roblox's Up-and-Coming top 10"
(roblox-up-and-coming-forecast-01). Deadline: Fri 2026-11-13 06:00 UTC.
Reward: $500 total, 20 places ($100 1st, $70 2nd, $50 3rd, $20 4th-10th,
$14 11th-20th). A place needs a log score strictly above the best house
entry (baseline -43.5 practice, house model -37.2 practice).

## What was built

- `repo/main.py` — Monte-Carlo diffusion forecaster, Python 3.13, stdlib
  only, no model calls, no network, $0 spend. See repo/README.md.
- `repo/` — submission files: main.py, LICENSE (MIT), README.md, TESTLOG.md.

## Local scoring (practice window, reconstructed answer)

Local scorer re-implements the rules exactly (per-place probability, floor
0.0001, unnamed share, mean over reads). Validated against the house
baseline: local score -43.512039 / 6.4 hits / 53.5 agreement, matching the
rules doc to 6 decimals. Practice answer = the public MIT archive's 10 reads
in 2026-11-07T23:00Z..2026-11-10T23:00Z, extracted from
github.com/Kenny-Dhub/roblox-snapshots commit history.

| Forecast | Log score | Typical p | Hits | Agreement |
|---|---|---|---|---|
| House baseline (kit starter) | -43.512 | 0.0129 | 6.4 | 53.5 |
| This entry (tuned) | -34.752 | 0.0310 | 7.3 | 60.1 |

Tuning: grid over SIGMA (0.04-0.16), GAMMA (0.6-1.0), UNNAMED (0.15-0.35),
FLOOR, MAX_PER_PLACE, HALF_LIFE (12/24h), SHRINK, MU_CAP, scored on 5
backtest windows (cutoffs 11-03..11-07). Chosen: SIGMA 0.13, GAMMA 0.85,
UNNAMED 0.25, FLOOR 0.004, MAX_PER_PLACE 22, HALF_LIFE 12h, SHRINK 2,
MU_CAP 0.03. Drift matters (MU_CAP 0: ~2.2 nats worse on mean).

## Backtests (this entry vs persistence baseline)

| Cutoff | This entry | Baseline |
|---|---|---|
| 2026-11-03 | -40.33 | -50.88 |
| 2026-11-04 | -38.03 | -48.63 |
| 2026-11-05 | -42.87 | -55.84 |
| 2026-11-06 | -39.50 | -52.45 |
| 2026-11-07 | -34.75 | -43.51 |

## Determinism & format

- Two runs on the kit input: byte-identical forecast.json.
- Runtime ~10 s on the 34-read practice history (limit 300 s).
- forecast.json: exactly 2 keys, 220 probability rows, each place sums to
  0.75 (0.25 unnamed), 10 distinct top10 ids, 12,705 bytes (limit 1 MiB).

## Kit pre-submit check

`node cli/makefun.mjs check --kit <kit> --repo repo --worktree`
(2026-11-11 ~09:39 UTC): 4 passed, 1 failed, 11 skipped, 5 checked at
submission. Passed: competition_open, snapshot (5 files, 18,546 bytes),
license_osi (MIT), entrypoint (main.py -> python3.13). Failed:
transcripts_present only — the transcript bundle is created at submit time
by the top-level agent (`makefun bundle --repo ...`), not by this build.
At submission: repo_public, repo_owner, repo_created_after_open,
commit_in_repo, duplicate_snapshot (need the public GitHub repo + push).
`grade-local` is not available for this competition: scorer/reference are
not in the kit, grading is server-only.

## Robustness edge cases (2026-11-11)

- Single-read history: runs, writes a valid forecast (no drift data -> pure
  diffusion from the last chart).
- History with `details` (created dates) + `top_trending` present, as the
  final's recorder reads will carry: runs, same practice score -34.752
  (test games ~6 days old, no ageing effect yet).
- Git: drand-anchored repo, root 3093bf85 (round 33862193), LICENSE commit,
  then the entry commit f96dab1.
