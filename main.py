#!/usr/bin/env python3
"""Roblox Up-and-Coming top-10 forecaster (make.fun roblox-up-and-coming-forecast-01).

Stdlib only, no network, no model calls, fully deterministic.

Method: Monte-Carlo diffusion in latent-strength space.
  * Each game has a latent strength s = -ln(rank). The chart is the order of s.
  * From the history we estimate, per game, a drift mu (recent trend of s, exponentially
    weighted with a 24 h half-life, shrunk toward the drift of its rank bucket) and a
    global per-hour volatility sigma.
  * We simulate many 72-hour trajectories (hourly steps, seeded RNG): s moves by
    mu + sigma * N(0, 1); games age out of the chart 28 days after they were created
    (when `details.created` is known) or with a small hazard once long since first seen.
  * A game's forecast probability at a place is its simulated occupancy of that place,
    averaged over all paths and all 72 hours -- exactly the time-average the log score
    rewards, since one forecast is scored against every hourly read of the window.
  * Occupancies are calibrated (flattened, floored, capped) so no probability is ever
    0 or 1, and a share of every place is left unnamed: the unnamed share spreads over
    every game on a read's chart we did not name there, which automatically covers
    brand-new games that join the chart during the window.
"""
import json
import math
import os
import random
import sys
from datetime import datetime, timezone

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

def _envf(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default

SEED = 20261113
N_PATHS = int(os.environ.get("TUNE_N_PATHS", "2500"))  # Monte-Carlo trajectories
HOURS = 72              # scored window length (from task.json when present)
TOP_GAMES = 50          # games simulated explicitly (by last rank + recent top 10)
HALF_LIFE_H = _envf("TUNE_HALF_LIFE", 12.0)   # drift memory
SHRINK_N = _envf("TUNE_SHRINK", 2.0)         # shrinkage weight toward bucket drift
MU_CAP = _envf("TUNE_MU_CAP", 0.03)          # max |drift| per hour
SIGMA = _envf("TUNE_SIGMA", 0.13)           # latent-strength volatility per hour
UNNAMED = _envf("TUNE_UNNAMED", 0.25)        # share of each place left unnamed
FLOOR_P = _envf("TUNE_FLOOR", 0.004)         # minimum probability for a named game
MAX_PER_PLACE = int(os.environ.get("TUNE_MAX_PER_PLACE", "22"))
GAMMA = _envf("TUNE_GAMMA", 0.85)            # occupancy power (< 1 flattens)
AGE_OUT_DAYS = 28.0     # games leave the chart this long after creation


def parse_time(s):
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_history(input_dir):
    """Return (reads, task): reads = [(time, [(rank, uid, name, playing), ...]), ...]."""
    task = {}
    task_path = os.path.join(input_dir, "task.json")
    if os.path.exists(task_path):
        with open(task_path) as f:
            task = json.load(f)
    hist_path = os.path.join(input_dir, "history.ndjson")
    reads = []
    with open(hist_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            at = parse_time(d.get("at"))
            rows = d.get("up_and_coming") or []
            chart = []
            for g in rows:
                chart.append((int(g["rank"]), int(g["universe_id"]),
                              g.get("name"), g.get("playing")))
            chart.sort()
            if at is not None and chart:
                reads.append((at, chart))
    reads.sort(key=lambda r: r[0])
    return reads, task


def main():
    reads, task = load_history(INPUT_DIR)
    places = int(task.get("places", 10))
    hours = int(task.get("window", {}).get("slots", HOURS))
    hours = max(1, min(hours, 24 * 14))
    out_name = task.get("output", "forecast.json")

    if not reads:
        raise SystemExit("no history reads found")
    last_at, last_chart = reads[-1]
    last_rank = {uid: rank for rank, uid, _n, _p in last_chart}

    # ---- per-game series: list of (time, rank) --------------------------------
    series = {}
    created = {}   # uid -> created datetime, when the history carries details
    for at, chart in reads:
        for rank, uid, _n, _p in chart:
            series.setdefault(uid, []).append((at, rank))
    # details live on the read dict; re-scan raw file for created dates
    hist_path = os.path.join(INPUT_DIR, "history.ndjson")
    try:
        with open(hist_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                det = d.get("details")
                if isinstance(det, list):
                    for item in det:
                        if isinstance(item, dict):
                            uid = item.get("universe_id")
                            c = parse_time(item.get("created")) if item.get("created") else None
                            if uid is not None and c is not None:
                                created[int(uid)] = c
                elif isinstance(det, dict):
                    for k, item in det.items():
                        if isinstance(item, dict):
                            c = parse_time(item.get("created")) if item.get("created") else None
                            if c is not None:
                                try:
                                    created[int(k)] = c
                                except (TypeError, ValueError):
                                    pass
    except OSError:
        pass

    # ---- drift estimation -------------------------------------------------------
    # Per-game weighted mean of d(-ln rank)/hour, shrunk toward its rank bucket mean.
    bucket_d = {}   # bucket -> [weighted sum, weight]
    game_d = {}     # uid -> [weighted sum, weight]

    def bucket(rank):
        if rank <= 3:
            return "1-3"
        if rank <= 10:
            return "4-10"
        if rank <= 30:
            return "11-30"
        return "31+"

    for uid, pts in series.items():
        for (t1, r1), (t2, r2) in zip(pts, pts[1:]):
            dt = (t2 - t1).total_seconds() / 3600.0
            if dt <= 0:
                continue
            d = (-math.log(r2) + math.log(r1)) / dt
            # weight by recency of the interval's end, half-life HALF_LIFE_H
            age_h = (last_at - t2).total_seconds() / 3600.0
            w = 0.5 ** (age_h / HALF_LIFE_H)
            b = bucket(r1)
            bs, bw = bucket_d.get(b, (0.0, 0.0))
            bucket_d[b] = (bs + w * d, bw + w)
            gs, gw = game_d.get(uid, (0.0, 0.0))
            game_d[uid] = (gs + w * d, gw + w)
    bucket_mean = {b: (s / w if w > 0 else 0.0) for b, (s, w) in bucket_d.items()}

    # ---- candidate games --------------------------------------------------------
    recent_top = set()
    for at, chart in reads:
        if (last_at - at).total_seconds() <= 48 * 3600:
            for rank, uid, _n, _p in chart:
                if rank <= 10:
                    recent_top.add(uid)
    cands = sorted(last_chart, key=lambda r: r[0])
    cand_uids = [uid for _r, uid, _n, _p in cands[:TOP_GAMES]]
    for uid in recent_top:
        if uid not in cand_uids:
            cand_uids.append(uid)
    cand_uids = cand_uids[:TOP_GAMES + 10]

    mu = {}
    for uid in cand_uids:
        gs, gw = game_d.get(uid, (0.0, 0.0))
        bmean = bucket_mean.get(bucket(last_rank.get(uid, 99)), 0.0)
        m = (gs + SHRINK_N * bmean) / (gw + SHRINK_N) if (gw + SHRINK_N) > 0 else bmean
        mu[uid] = max(-MU_CAP, min(MU_CAP, m))

    # Ageing: hours from `created` (or first seen) until the game leaves the chart.
    first_seen = {uid: pts[0][0] for uid, pts in series.items()}
    exit_at_h = {}  # uid -> hours after last_at when it ages out (inf if unknown/young)
    for uid in cand_uids:
        base = created.get(uid)
        if base is not None:
            age_h = (last_at - base).total_seconds() / 3600.0
            exit_at_h[uid] = max(0.0, AGE_OUT_DAYS * 24.0 - age_h)
        else:
            fs = first_seen.get(uid)
            if fs is not None:
                age_h = (last_at - fs).total_seconds() / 3600.0
                # first seen is a lower bound on age; only hazard once very old
                exit_at_h[uid] = max(0.0, AGE_OUT_DAYS * 24.0 - age_h) if age_h > 20 * 24 else float("inf")
            else:
                exit_at_h[uid] = float("inf")

    s0 = {uid: -math.log(last_rank[uid]) for uid in cand_uids if uid in last_rank}
    # games in recent top 10 but not in the last chart: start just below the chart
    for uid in cand_uids:
        if uid not in s0:
            s0[uid] = -math.log(len(last_chart) + 5)
    uids = list(s0.keys())
    n = len(uids)
    idx = {u: i for i, u in enumerate(uids)}
    mu_list = [mu.get(u, 0.0) for u in uids]
    exit_list = [exit_at_h.get(u, float("inf")) for u in uids]
    s_init = [s0[u] for u in uids]

    # ---- Monte Carlo ------------------------------------------------------------
    rng = random.Random(SEED)
    # occupancy[place][game-index] counts
    occ = [[0] * n for _ in range(places)]
    order = list(range(n))
    for _path in range(N_PATHS):
        s = list(s_init)
        alive = [True] * n
        for h in range(1, hours + 1):
            for i in range(n):
                if not alive[i]:
                    continue
                if h > exit_list[i]:
                    alive[i] = False
                    continue
                s[i] += mu_list[i] + SIGMA * rng.gauss(0.0, 1.0)
            # rank the alive games by strength; ties broken by index (deterministic)
            order.sort(key=lambda i: (-s[i] if alive[i] else float("inf"), i))
            for place in range(places):
                gi = order[place]
                if alive[gi]:
                    occ[place][gi] += 1
    denom = float(N_PATHS * hours)

    # ---- convert occupancy to calibrated probabilities --------------------------
    probabilities = []
    expected_rank = [0.0] * n
    for place in range(places):
        row = occ[place]
        for gi in range(n):
            expected_rank[gi] += (place + 1) * row[gi]
    # mean rank over the window for the top10 guess (games never in top 10 get a
    # large rank); use occupancy-weighted rank.
    top_score = []
    for gi in range(n):
        tot = sum(occ[p][gi] for p in range(places))
        top_score.append((tot, expected_rank[gi] / tot if tot else 1e9, uids[gi]))
    top_score.sort(key=lambda t: (-t[0], t[1]))
    top10 = [u for _t, _r, u in top_score[:places]]

    for place in range(places):
        row = occ[place]
        scored = sorted(range(n), key=lambda gi: -row[gi])[:MAX_PER_PLACE]
        weights = [(row[gi] / denom) ** GAMMA if row[gi] > 0 else 0.0 for gi in scored]
        wsum = sum(weights)
        if wsum <= 0:
            continue
        budget = 1.0 - UNNAMED
        floor_total = FLOOR_P * len(scored)
        for gi, w in zip(scored, weights):
            p = FLOOR_P + (budget - floor_total) * (w / wsum)
            p = min(p, 0.85)
            if p > 0.001:
                probabilities.append({"universe_id": int(uids[gi]),
                                      "place": place + 1, "p": round(p, 6)})
    # Renormalise each place to sum <= 1 - UNNAMED (rounding can only shrink it).
    forecast = {"probabilities": probabilities, "top10": [int(u) for u in top10]}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, out_name), "w") as f:
        f.write(json.dumps(forecast) + "\n")


if __name__ == "__main__":
    main()
