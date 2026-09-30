"""Shared pieces of the validator and the summariser.

The numbers here must agree with what `neoscad bench` prints at the end of
a run (bench_core's `BenchResult::summary` in neoscad/neoscad), or a
submitter would see one speedup in their terminal and another on
neoscad.org. So the rules are the same: a model counts for neoscad when its
last run exited 0 with a best time, and for the comparison only when
OpenSCAD's did too, both times above zero; the speedup is the geometric
mean of OpenSCAD's best over neoscad's over exactly those models.
"""

import json
import math
import re

# The timing methods this repository knows (bench_core::timing::METHOD_VERSION
# in neoscad/neoscad). A result timed another way is not comparable with the
# others, so an unknown method is refused rather than filed.
KNOWN_METHODS = {1}

# A release version as neoscad tags it (v<version>): the same shape the
# release workflow accepts. Anything else is refused before it is used in a
# URL, a `gh` argument or a path.
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?$")


def ok(measurement):
    """Whether a measurement finished: exit code 0 and a best time."""
    return (
        measurement is not None
        and measurement.get("rc") == 0
        and isinstance(measurement.get("best_s"), (int, float))
        and not isinstance(measurement.get("best_s"), bool)
    )


def summary(result):
    """Port of BenchResult::summary, plus neoscad's own geometric mean."""
    s = {
        "models": len(result["models"]),
        "neoscad_ok": 0,
        "neoscad_total_s": 0.0,
        "neoscad_geomean_s": None,
        "compared": 0,
        "geomean_speedup": None,
    }
    log_speedup = 0.0
    log_time = 0.0
    positive = 0
    for pair in result["models"].values():
        n = pair["neoscad"]
        if not ok(n):
            continue
        nb = n["best_s"]
        s["neoscad_ok"] += 1
        s["neoscad_total_s"] += nb
        if nb > 0:
            positive += 1
            log_time += math.log(nb)
        o = pair.get("openscad")
        if ok(o) and nb > 0 and o["best_s"] > 0:
            s["compared"] += 1
            log_speedup += math.log(o["best_s"] / nb)
    if positive:
        s["neoscad_geomean_s"] = math.exp(log_time / positive)
    if s["compared"]:
        s["geomean_speedup"] = math.exp(log_speedup / s["compared"])
    return s


def version_key(v):
    """Sort key for release versions, SemVer precedence (a prerelease sorts
    before its release)."""
    core, _, pre = v.partition("-")
    nums = tuple(int(x) for x in core.split("."))
    if not pre:
        return (nums, 1, ())
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (nums, 0, parts)


def canonical(obj):
    """The committed form of a result: pretty, keys sorted, newline-ended,
    so the same result always gives the same bytes (and duplicates can be
    found by comparing files)."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def rnd(x, places):
    return None if x is None else round(x, places)
