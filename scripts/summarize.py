#!/usr/bin/env python3
"""Rebuild summary.json from results/: what neoscad.org/community.html reads.

    summarize.py [--results results] [--out summary.json] [--check]

Output is deterministic (sorted keys, rounded numbers, no timestamps), so
rebuilding from the same files gives the same bytes and the workflow only
commits when a result changed. --check exits 1 if --out is not up to date.

Only like is compared with like: a version's runs are all timed with that
release's kit (the validator requires kit.version == neoscad.version) and
with one timing method; a result timed with another method is listed under
`excluded` instead of being mixed into the medians. Quick runs (7 models,
one run each) and full runs cover different models, and OpenSCAD's
Manifold and CGAL backends differ several-fold, so speedups are aggregated
per kind of run and per backend. Release baselines (source ci-baseline, committed by
NeoSCAD's release workflow) are listed per target under `baselines`, apart
from users' runs, and never enter the users' aggregates.
"""

import argparse
import collections
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchlib  # noqa: E402

FORMAT = 1
USER_FILE = re.compile(r"^([1-9][0-9]*)\.json$")
BASELINE_FILE = re.compile(r"^ci-baseline-([a-z0-9_]+(-[a-z0-9_]+){2,3})\.json$")


def best(m):
    return benchlib.rnd(m["best_s"], 4) if benchlib.ok(m) else None


def run_entry(r, run_id, path):
    s = benchlib.summary(r)
    m = r["machine"]
    models = {}
    for mid, pair in r["models"].items():
        n, o = pair["neoscad"], pair.get("openscad")
        sp = None
        if benchlib.ok(n) and benchlib.ok(o) and n["best_s"] > 0 and o["best_s"] > 0:
            sp = benchlib.rnd(o["best_s"] / n["best_s"], 3)
        models[mid] = {"neoscad_s": best(n), "openscad_s": best(o) if o else None, "speedup": sp}
    ref = r["openscad"]
    return {
        "id": run_id,
        "path": path,
        "source": r["source"],
        "started_at": r["started_at"],
        "target": r["neoscad"]["target"],
        "os": m["os"],
        "os_version": m["os_version"],
        "arch": m["arch"],
        "cpu": m["cpu"],
        "hardware_model": m["hardware_model"],
        "cores_logical": m["cores_logical"],
        "cores_performance": m["cores_performance"],
        "cores_efficiency": m["cores_efficiency"],
        "memory_bytes": m["memory_bytes"],
        "on_battery": m["on_battery"],
        "translated": m["translated"],
        "threads": r["threads"],
        "quick": r["method"]["quick"],
        "runs_per_model": r["method"]["runs"],
        "openscad": None if ref is None else {"version": ref["version"], "backend": ref["backend"]},
        "models_run": s["models"],
        "neoscad_ok": s["neoscad_ok"],
        "neoscad_total_s": benchlib.rnd(s["neoscad_total_s"], 4),
        "neoscad_geomean_s": benchlib.rnd(s["neoscad_geomean_s"], 4),
        "compared": s["compared"],
        "geomean_speedup": benchlib.rnd(s["geomean_speedup"], 3),
        "cold_start": {
            "neoscad_s": best(r["cold_start"]["neoscad"]),
            "openscad_s": best(r["cold_start"]["openscad"]) if r["cold_start"]["openscad"] else None,
        },
        "models": models,
        "skipped": sorted(r["skipped"]),
    }


def spread(values):
    v = sorted(values)
    return {
        "n": len(v),
        "median": round(statistics.median(v), 3),
        "min": v[0],
        "max": v[-1],
    }


def aggregate(runs):
    """Counts, and the speedup's median and range per kind of run and per
    OpenSCAD backend. Kept apart because they do not measure the same
    thing: quick runs time 7 of the models, and CGAL is several times
    slower than Manifold, so one median over both would describe neither."""
    with_ref = [x for x in runs if x["openscad"] is not None]
    groups = collections.defaultdict(list)
    for x in with_ref:
        if x["geomean_speedup"] is not None:
            groups[("quick" if x["quick"] else "full", x["openscad"]["backend"])].append(x["geomean_speedup"])
    return {
        "runs": len(runs),
        "with_openscad": len(with_ref),
        "without_openscad": len(runs) - len(with_ref),
        "speedup": [
            {"runs_kind": kind, "backend": backend, **spread(v)}
            for (kind, backend), v in sorted(groups.items())
        ],
    }


def load(results_dir):
    """(version, file name, parsed result) for every result file, and the
    files skipped with why."""
    found, skipped = [], []
    if not os.path.isdir(results_dir):
        return found, skipped
    for v in sorted(os.listdir(results_dir)):
        d = os.path.join(results_dir, v)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            path = f"results/{v}/{f}"
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    r = json.load(fh)
                why = None
                if not benchlib.VERSION_RE.match(v):
                    why = "directory is not a version"
                elif r.get("schema") != 1:
                    why = "not schema 1"
                elif r["neoscad"]["version"] != v:
                    why = "neoscad.version is not the directory's version"
                elif r["kit"]["version"] != v:
                    why = "kit.version is not the release's"
                elif USER_FILE.match(f):
                    if r["source"] != "user":
                        why = "an issue's file must be source user"
                elif BASELINE_FILE.match(f):
                    if r["source"] != "ci-baseline" or BASELINE_FILE.match(f).group(1) != r["neoscad"]["target"]:
                        why = "a baseline file must be source ci-baseline for its target"
                else:
                    why = "file name is neither <issue>.json nor ci-baseline-<target>.json"
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                why = f"unreadable: {type(e).__name__}"
            if why:
                skipped.append({"path": path, "why": why})
            else:
                found.append((v, f, r))
    return found, skipped


def build(results_dir):
    found, skipped = load(results_dir)
    by_version = collections.defaultdict(list)
    for v, f, r in found:
        by_version[v].append((f, r))
    versions = {}
    for v, items in by_version.items():
        # One timing method per version: the baselines' (the release's own
        # binary), else the most common, ties to the lowest.
        base_methods = {r["method"]["version"] for f, r in items if r["source"] == "ci-baseline"}
        counts = collections.Counter(r["method"]["version"] for f, r in items)
        method = min(base_methods) if base_methods else min(counts, key=lambda k: (-counts[k], k))
        platforms = collections.defaultdict(lambda: collections.defaultdict(list))
        baselines = {}
        excluded = []
        users = []
        for f, r in items:
            path = f"results/{v}/{f}"
            if r["method"]["version"] != method:
                excluded.append({"path": path, "why": f"timing method {r['method']['version']}, "
                                                       f"not this version's {method}"})
                continue
            if r["source"] == "ci-baseline":
                e = run_entry(r, f[: -len(".json")], path)
                baselines[e["target"]] = e
                continue
            e = run_entry(r, int(f[: -len(".json")]), path)
            users.append(e)
            cpu = e["cpu"] or f"unknown {e['arch']} CPU"
            platforms[f"{e['os']}-{e['arch']}"][cpu].append(e)
        plat_out = {}
        for p, machines in platforms.items():
            runs = [x for ms in machines.values() for x in ms]
            os_, arch = p.split("-", 1)
            plat_out[p] = {
                "os": os_,
                "arch": arch,
                **aggregate(runs),
                "machines": {cpu: sorted(ms, key=lambda x: (x["started_at"], x["id"]))
                             for cpu, ms in machines.items()},
            }
        kits = sorted({r["kit"]["archive_sha256"] or "" for f, r in items} - {""})
        versions[v] = {
            "version": v,
            "kit_version": v,
            "kit_archive_sha256": kits[0] if len(kits) == 1 else None,
            "method_version": method,
            **aggregate(users),
            "platforms": plat_out,
            "baselines": baselines,
            "excluded": sorted(excluded, key=lambda x: x["path"]),
        }
    order = sorted(versions, key=benchlib.version_key, reverse=True)
    releases = [v for v in order if "-" not in v]
    return {
        "format": FORMAT,
        "latest": (releases or order or [None])[0],
        "version_order": order,
        "versions": versions,
        "skipped_files": skipped,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="summary.json")
    ap.add_argument("--check", action="store_true", help="fail if --out is out of date")
    a = ap.parse_args()
    text = json.dumps(build(a.results), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if a.check:
        try:
            with open(a.out, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = None
        if current != text:
            sys.exit(f"{a.out} is out of date; run scripts/summarize.py")
        return
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
