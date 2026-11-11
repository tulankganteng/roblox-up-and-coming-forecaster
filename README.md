# Up-and-Coming Monte-Carlo Forecaster — make.fun `roblox-up-and-coming-forecast-01`

A no-model, deterministic forecaster for Roblox's Up-and-Coming top 10.
Python 3.13, standard library only. No API key, no model calls, no network,
no money spent. Reads `/input/history.ndjson` + `/input/task.json`, writes
`/output/forecast.json` (or `$MAKEFUN_INPUT_DIR` / `$MAKEFUN_OUTPUT_DIR`).

## Method

Monte-Carlo diffusion in latent-strength space:

- Each game has a latent strength `s = -ln(rank)`; the chart is the order of `s`.
  This makes rank volatility naturally larger at the top (adjacent ranks are
  far apart in `s` there), matching the archive.
- Per game, a drift `mu` is estimated from its recent rank trajectory:
  exponentially weighted (12 h half-life) mean of `d(-ln rank)/hour`, shrunk
  toward its rank bucket's mean drift (top games decay fastest). Playing
  counts were checked and do **not** predict rank moves (corr -0.01), so they
  are not used as a signal.
- 2,500 seeded trajectories are simulated hour by hour for the 72-hour
  window: `s += mu + 0.13 * N(0,1)`. Games age out 28 days after creation
  (from `details.created` when the history carries it).
- A game's probability at a place is its simulated occupancy of that place,
  averaged over all paths and all 72 hours — the time-average the log score
  rewards, since one forecast is scored against every hourly read.
- Occupancies are calibrated: raised to 0.85, floored at 0.004 per named game,
  capped, top 22 games per place, and 25% of every place left unnamed. The
  unnamed share spreads over every game on a read's chart not named there,
  which automatically covers brand-new games joining the chart mid-window.

## Local results

Scored with a local re-implementation of the rules (verified byte-exact
against the house baseline: -43.512039, 6.4 hits, 53.5 agreement on the
practice window). Practice answer reconstructed from the public MIT archive
`github.com/Kenny-Dhub/roblox-snapshots` (10 reads, 2026-11-08 → 2026-11-10).

| Forecast | Practice log score | Typical p | Top-10 hits | Agreement |
|---|---|---|---|---|
| House baseline (starter) | -43.512 | 0.0129 | 6.4 | 53.5 |
| House model (superbot) | -37.2 | — | — | — |
| Best other entry (visible) | -34.8 | — | — | — |
| **This entry** | **-34.752** | **0.0310** | **7.3** | **60.1** |

Backtests (same code, history truncated at earlier cutoffs, scored on the
following 72 h of archive reads) — this entry vs the persistence baseline:

| Cutoff | This entry | Baseline |
|---|---|---|
| 2026-11-03 | -40.33 | -50.88 |
| 2026-11-04 | -38.03 | -48.63 |
| 2026-11-05 | -42.87 | -55.84 |
| 2026-11-06 | -39.50 | -52.45 |
| 2026-11-07 (practice) | -34.75 | -43.51 |

Two runs on the same history produce byte-identical output; runtime ~10 s
on the practice history (limit 300 s).

## Files

- `main.py` — the whole entry (stdlib only)
- `README.md` — this file
- `LICENSE` — MIT
