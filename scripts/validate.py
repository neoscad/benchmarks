#!/usr/bin/env python3
"""Validate one benchmark submission (an issue) and, if it passes, file it.

    validate.py --event $GITHUB_EVENT_PATH --out decision.json [--write]
    validate.py --body-file body.md --issue 12 --release-dir tests/fixtures/releases ...

The issue body is the one neoscad's `bench --submit` and the issue form
both write (neoscad/neoscad crates/bench-core/src/submit.rs):

    ### Result JSON

    ```json
    { ... }
    ```

    ### Notes
    ...

Everything the client says is re-checked here, because a client can be
made to say anything: the result must match the JSON Schema published at
the release's tag, the executable's SHA-256 must be the one the release
lists for its target, and the kit must be the release's kit. The decision
(accepted, rejected with reasons, or ignored) goes to --out as JSON for the
workflow to act on; with --write an accepted result is also written to
results/<version>/<issue>.json.

Network access happens only through a Release object: GitHubRelease (gh
and raw.githubusercontent.com) in the workflow, LocalRelease (a fixture
directory) in the tests.
"""

import argparse
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchlib  # noqa: E402

UPSTREAM = "neoscad/neoscad"
REPO = "neoscad/benchmarks"
# GitHub allows 65536 characters in an issue body; a full run with
# OpenSCAD is about 15 KB. Anything much larger is not a submission, and
# parsing it would only cost Actions minutes.
MAX_BODY = 256 * 1024
MAX_MODELS = 500
MAX_STRING = 300
TARGET_RE = re.compile(r"^[a-z0-9_]+(-[a-z0-9_]+){2,3}$")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# Kit archives are about 1 MB; bench_core refuses more than this unpacked.
MAX_KIT_UNPACKED = 256 << 20
MAX_KIT_ENTRIES = 20_000

# `neoscad bench` never reads a path, host name, address or account name,
# so none should be in a result. A result is public once filed, though, and
# a hand-edited one could carry anything; these patterns catch the common
# shapes of what should never be published. Each is (why, pattern).
IDENTIFYING = [
    ("a file path", re.compile(
        r"(^|[^A-Za-z0-9])/(Users|home|root|private|var|tmp|Volumes|mnt|media|opt|nix|run|srv|etc|usr)/",
        re.I)),
    ("a file path", re.compile(r"(^|[^A-Za-z0-9])[A-Za-z]:[\\/]")),
    ("a file path", re.compile(r"\\\\|(^|\s)~[/\\]")),
    ("an e-mail address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+")),
    ("a MAC address", re.compile(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    # Four dotted numbers up to 255 that are not part of a longer version
    # string (a WSL kernel is "5.15.167.4-microsoft-standard-WSL2").
    ("an IP address", re.compile(
        r"(?<![\w.])((25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.-])")),
    ("a host name", re.compile(r"\b[A-Za-z0-9-]+\.(local|lan|localdomain|home\.arpa|internal)\b", re.I)),
]


class Reject(Exception):
    pass


# ---------------------------------------------------------------- the body

def extract_json(body):
    """The text of the one result in the body's Result JSON section."""
    lines = body.replace("\r\n", "\n").split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "### Result JSON":
            start = i + 1
            break
    if start is None:
        raise Reject("The issue has no `### Result JSON` section. Submit with "
                     "`neoscad bench --submit` or the issue form.")
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("### "):
            end = i
            break
    section = lines[start:end]
    blocks, current, fence = [], None, None
    for line in section:
        s = line.strip()
        if current is None:
            m = re.match(r"^(`{3,}|~{3,})", s)
            if m:
                current, fence = [], m.group(1)
        elif s.startswith(fence) and s.strip(fence[0]) == "":
            blocks.append("\n".join(current))
            current = None
        else:
            current.append(line)
    if current is not None:
        raise Reject("The Result JSON's code fence is not closed.")
    if len(blocks) > 1:
        raise Reject("The Result JSON section holds more than one code block; "
                     "submit one result per issue.")
    text = blocks[0] if blocks else "\n".join(section)
    text = text.strip()
    if not text or text == "_No response_":
        raise Reject("The Result JSON section is empty.")
    return text


# ------------------------------------------------------------ the release

class Release:
    """What a published neoscad release says about itself."""

    def schema(self):  # dict, or None if the tag has none
        raise NotImplementedError

    def executable_sums(self):  # text, or None if not attached
        raise NotImplementedError

    def kit_sha256(self):  # text of the .sha256, or None
        raise NotImplementedError

    def kit_archive(self):  # bytes, or None
        raise NotImplementedError

    def published_at(self):  # datetime, or None
        raise NotImplementedError


class LocalRelease(Release):
    """A fixture directory standing in for a release: DIR/v<version>/ with
    result.schema.json, neoscad-executables.sha256sums,
    neoscad-bench-kit-<version>.tar.gz[.sha256] and release.json
    ({"publishedAt": ...}). A missing file is a missing asset."""

    def __init__(self, root, version):
        self.dir = os.path.join(root, "v" + version)
        self.version = version
        if not os.path.isdir(self.dir):
            raise Reject(f"neoscad {version} is not a published release of {UPSTREAM}.")

    def _read(self, name, binary=False):
        p = os.path.join(self.dir, name)
        if not os.path.isfile(p):
            return None
        with open(p, "rb" if binary else "r", encoding=None if binary else "utf-8") as f:
            return f.read()

    def schema(self):
        t = self._read("result.schema.json")
        return None if t is None else json.loads(t)

    def executable_sums(self):
        return self._read("neoscad-executables.sha256sums")

    def kit_sha256(self):
        return self._read(f"neoscad-bench-kit-{self.version}.tar.gz.sha256")

    def kit_archive(self):
        return self._read(f"neoscad-bench-kit-{self.version}.tar.gz", binary=True)

    def published_at(self):
        t = self._read("release.json")
        return None if t is None else parse_utc(json.loads(t)["publishedAt"])


class GitHubRelease(Release):
    """The release on GitHub, read with `gh` (the workflow's token) and the
    schema from raw.githubusercontent.com at the release's tag. Drafts are
    invisible to this repository's token, so only published releases (and
    prereleases) pass."""

    def __init__(self, version):
        self.version = version
        self.tag = "v" + version
        self.tmp = tempfile.mkdtemp(prefix="release-")
        p = subprocess.run(
            ["gh", "release", "view", self.tag, "-R", UPSTREAM, "--json", "isDraft,publishedAt,assets"],
            capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise Reject(f"neoscad {version} is not a published release of {UPSTREAM} "
                         f"(no release tagged `{self.tag}`).")
        info = json.loads(p.stdout)
        if info.get("isDraft"):
            raise Reject(f"neoscad {version} is not published yet.")
        self.info = info
        self.assets = {a["name"] for a in info.get("assets", [])}

    def _asset(self, name):
        if name not in self.assets:
            return None
        p = subprocess.run(
            ["gh", "release", "download", self.tag, "-R", UPSTREAM, "-p", name, "-D", self.tmp, "--clobber"],
            capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise RuntimeError(f"downloading {name}: {p.stderr.strip()}")
        with open(os.path.join(self.tmp, name), "rb") as f:
            return f.read()

    def schema(self):
        url = f"https://raw.githubusercontent.com/{UPSTREAM}/{self.tag}/bench/result.schema.json"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read(1 << 20))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def executable_sums(self):
        b = self._asset("neoscad-executables.sha256sums")
        return None if b is None else b.decode("utf-8", "replace")

    def kit_sha256(self):
        b = self._asset(f"neoscad-bench-kit-{self.version}.tar.gz.sha256")
        return None if b is None else b.decode("utf-8", "replace")

    def kit_archive(self):
        return self._asset(f"neoscad-bench-kit-{self.version}.tar.gz")

    def published_at(self):
        v = self.info.get("publishedAt")
        return parse_utc(v) if v else None


def kit_content_sha256(archive):
    """bench_core::kit::content_sha256 of the unpacked archive: SHA-256 of
    the sorted lines `<sha256 of file>  <path relative to the kit root>`,
    the root being the directory holding kit.json. Lets a result run from
    an unpacked kit (archive_sha256 null) be matched to its release."""
    files, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for n, member in enumerate(tar):
            if n >= MAX_KIT_ENTRIES:
                raise RuntimeError("kit archive has too many entries")
            if not member.isfile():
                continue
            total += member.size
            if total > MAX_KIT_UNPACKED:
                raise RuntimeError("kit archive unpacks too large")
            name = member.name
            while name.startswith("./"):
                name = name[2:]
            files[name] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
    roots = [n[: -len("kit.json")] for n in files if n == "kit.json" or n.endswith("/kit.json")]
    roots = [r for r in roots if r.count("/") <= 1]
    if len(roots) != 1:
        raise RuntimeError("kit archive has no single kit.json")
    root = roots[0]
    listing = "".join(
        f"{files[n]}  {n[len(root):]}\n" for n in sorted(n for n in files if n.startswith(root)))
    return hashlib.sha256(listing.encode()).hexdigest()


# ------------------------------------------------------------- the checks

def parse_utc(s):
    return dt.datetime.strptime(s.replace(".000Z", "Z"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def schema_errors(schema, result):
    from jsonschema import Draft202012Validator

    v = Draft202012Validator(schema)
    out = []
    for e in sorted(v.iter_errors(result), key=lambda e: list(map(str, e.absolute_path))):
        where = "/".join(str(p) for p in e.absolute_path) or "(top level)"
        msg = e.message if len(e.message) < 200 else e.message[:200] + "..."
        out.append(f"`{where}`: {msg}")
    return out


def walk_strings(obj, at=""):
    if isinstance(obj, str):
        yield at, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{at}/{k} (key)", k
            yield from walk_strings(v, f"{at}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{at}/{i}")


def sanity(result, now, published):
    """Checks the schema cannot express. Returns reasons."""
    reasons = []
    if not result["models"]:
        reasons.append("The result has no models.")
    if len(result["models"]) > MAX_MODELS:
        reasons.append(f"The result has more than {MAX_MODELS} models.")
    timeout = result["method"]["timeout_s"]
    has_ref = result["openscad"] is not None
    pairs = [("cold_start", result["cold_start"])] + [
        (f"models/{k}", v) for k, v in result["models"].items()]
    for k in list(result["models"]) + list(result["skipped"]):
        if not MODEL_ID_RE.match(k):
            reasons.append(f"Model id `{k[:60]}` is not a kit model id.")
    for where, pair in pairs:
        if (pair["openscad"] is not None) != has_ref:
            reasons.append(f"`{where}/openscad` disagrees with the top-level `openscad` "
                           "(a comparison must come from one OpenSCAD for every model).")
        for side in ("neoscad", "openscad"):
            m = pair[side]
            if m is None:
                continue
            best = m["best_s"]
            if best is not None and not (math.isfinite(best) and 0 < best <= timeout * 2):
                reasons.append(f"`{where}/{side}/best_s` is {best}; a time must be above 0 "
                               f"and within the timeout.")
            for t in m["runs_s"]:
                if t is not None and not (math.isfinite(t) and 0 < t <= timeout * 2):
                    reasons.append(f"`{where}/{side}/runs_s` has {t}; a time must be above 0.")
                    break
            done = [t for t in m["runs_s"] if t is not None]
            if best is not None and done and best > min(done) * 1.0001 + 1e-9:
                reasons.append(f"`{where}/{side}/best_s` is above its fastest run.")
            if any((not math.isfinite(c)) or c < 0 for c in m["cpu_s"]):
                reasons.append(f"`{where}/{side}/cpu_s` has a negative time.")
    started = parse_utc(result["started_at"])
    finished = parse_utc(result["finished_at"])
    if finished < started:
        reasons.append("`finished_at` is before `started_at`.")
    if finished - started > dt.timedelta(hours=48):
        reasons.append("The run took more than 48 hours by its timestamps.")
    if finished > now + dt.timedelta(hours=26):
        reasons.append("`finished_at` is in the future.")
    # The binary did not exist before its release was built; a day of
    # slack covers release assets built before the release was published.
    if published is not None and started < published - dt.timedelta(days=2):
        reasons.append(f"`started_at` ({result['started_at']}) is before the release was published.")
    for where, s in walk_strings(result):
        if len(s) > MAX_STRING:
            reasons.append(f"`{where}` is longer than {MAX_STRING} characters.")
            continue
        for why, pat in IDENTIFYING:
            if pat.search(s):
                reasons.append(f"`{where}` looks like it contains {why}; results are public, "
                               "and `neoscad bench` never records one.")
                break
    return reasons


def check(result, release_for, now, existing):
    """The reasons `result` cannot be accepted (empty: accept). Stops at the
    first failing stage when later stages depend on it (a schema error makes
    every later check meaningless)."""
    if not isinstance(result, dict):
        raise Reject("The Result JSON must be one JSON object (one result per issue).")
    if result.get("source") != "user":
        raise Reject("`source` must be `user`: release baselines are committed by NeoSCAD's "
                     "release workflow, never submitted as issues.")
    neo = result.get("neoscad")
    version = neo.get("version") if isinstance(neo, dict) else None
    target = neo.get("target") if isinstance(neo, dict) else None
    if not isinstance(version, str) or not benchlib.VERSION_RE.match(version):
        raise Reject("`neoscad.version` is missing or is not a release version.")
    if not isinstance(target, str) or not TARGET_RE.match(target):
        raise Reject("`neoscad.target` is missing or is not a Rust target triple.")

    release = release_for(version)
    schema = release.schema()
    if schema is None:
        raise Reject(f"neoscad {version} has no community benchmark schema "
                     f"(`bench/result.schema.json` at tag `v{version}`): it was released "
                     "before community benchmarks.")
    errs = schema_errors(schema, result)
    if errs:
        shown = errs[:10] + ([f"... and {len(errs) - 10} more"] if len(errs) > 10 else [])
        raise Reject("The result does not match the schema of neoscad "
                     f"{version}:\n" + "\n".join(f"  - {e}" for e in shown))

    reasons = []
    if not (neo["official"] and neo["official_check"] == "matched"):
        reasons.append(f"The binary says it is not an official release build "
                       f"(`official_check: {neo['official_check']}`). Only official release "
                       "binaries are accepted; see the README.")
    sums = release.executable_sums()
    if sums is None:
        reasons.append(f"Release v{version} has no `neoscad-executables.sha256sums`, "
                       "so no binary of it can be checked.")
    else:
        listed = {}
        for line in sums.splitlines():
            parts = line.split()
            if len(parts) == 2 and SHA_RE.match(parts[0]):
                listed[parts[1]] = parts[0]
        want = listed.get(f"{target}/neoscad") or listed.get(f"{target}/neoscad.exe")
        if want is None:
            reasons.append(f"Release v{version} has no executable for `{target}`.")
        elif want != neo["sha256"]:
            reasons.append(f"`neoscad.sha256` is not the SHA-256 of release v{version}'s "
                           f"executable for `{target}`: the binary was self-built or modified. "
                           "Only official release binaries are accepted.")
    kit = result["kit"]
    if kit["version"] != version:
        reasons.append(f"`kit.version` is {kit['version']}, not {version}: use the release's own kit "
                       "(`neoscad bench` downloads it by default).")
    else:
        sha_text = release.kit_sha256()
        if sha_text is None:
            reasons.append(f"Release v{version} has no bench kit.")
        elif kit["archive_sha256"] is not None:
            if kit["archive_sha256"] != sha_text.split()[0]:
                reasons.append(f"`kit.archive_sha256` is not release v{version}'s "
                               f"`neoscad-bench-kit-{version}.tar.gz`.")
        else:
            archive = release.kit_archive()
            if archive is None or hashlib.sha256(archive).hexdigest() != sha_text.split()[0]:
                reasons.append(f"Release v{version}'s kit archive could not be checked.")
            elif kit_content_sha256(archive) != kit["content_sha256"]:
                reasons.append(f"`kit.content_sha256` is not the content of release v{version}'s "
                               "bench kit (the kit was modified).")
    if result["method"]["version"] not in benchlib.KNOWN_METHODS:
        reasons.append(f"`method.version` {result['method']['version']} is not a known timing "
                       f"method (known: {sorted(benchlib.KNOWN_METHODS)}).")
    reasons += sanity(result, now, release.published_at())
    dup = existing.get(benchlib.canonical(result))
    if dup is not None:
        reasons.append(f"This exact result was already accepted as `{dup}`.")
    return reasons


# ---------------------------------------------------------------- output

def fmt_speedup(x):
    return f"{x:.2f}×"


def accepted_comment(result, path):
    s = benchlib.summary(result)
    m = result["machine"]
    lines = [
        "Thanks! This result passed validation and is filed as "
        f"[`{path}`](https://github.com/{REPO}/blob/main/{path}).",
        "",
        f"- neoscad {result['neoscad']['version']} (`{result['neoscad']['target']}`), "
        f"official release binary",
        f"- {m['os_version'] or m['os']}, {m['cpu'] or m['arch']}",
        f"- {s['neoscad_ok']} of {s['models']} models finished"
        + (" (quick run)" if result["method"]["quick"] else ""),
    ]
    ref = result["openscad"]
    if ref is None:
        lines.append("- No OpenSCAD comparison (a run with `--openscad` on the same machine "
                     "adds one, and is the most useful kind of result).")
    elif s["geomean_speedup"] is not None:
        lines.append(f"- {fmt_speedup(s['geomean_speedup'])} geometric-mean speedup over "
                     f"{ref['version']} ({ref['backend']}), over the {s['compared']} models "
                     "both finished")
    else:
        lines.append(f"- Compared with {ref['version']} ({ref['backend']}), but no model "
                     "finished in both, so there is no speedup.")
    lines += ["", "It appears in `summary.json` and on https://neoscad.org/community.html."]
    return "\n".join(lines)


def rejected_comment(reasons):
    body = ["This submission could not be accepted:", ""]
    for r in reasons:
        first, *rest = r.split("\n")
        body.append(f"- {first}")
        body += [f"  {x.strip()}" for x in rest]
    body += ["", "Edit the issue to fix it (an edit is checked again), or run "
             "`neoscad bench --submit` with an official release binary. "
             "The rules are in the [README](https://github.com/" + REPO + "#readme)."]
    return "\n".join(body)


def existing_results(results_dir):
    out = {}
    if not os.path.isdir(results_dir):
        return out
    for v in sorted(os.listdir(results_dir)):
        d = os.path.join(results_dir, v)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out.setdefault(fh.read(), f"results/{v}/{f}")
    return out


def decide(body, issue, release_for, now, results_dir):
    if len(body.encode("utf-8")) > MAX_BODY:
        return {"status": "ignored", "reasons": [f"body over {MAX_BODY} bytes"]}
    if "### Result JSON" not in body:
        return {"status": "ignored", "reasons": ["not a submission"]}
    try:
        text = extract_json(body)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            raise Reject(f"The Result JSON does not parse: {e.msg} at line {e.lineno}, column {e.colno}.")
        # An edit of an issue already filed must not count as its own duplicate.
        existing = {k: v for k, v in existing_results(results_dir).items()
                    if not v.endswith(f"/{issue}.json")}
        reasons = check(result, release_for, now, existing)
    except Reject as e:
        reasons = [str(e)]
    if reasons:
        return {"status": "rejected", "reasons": reasons, "comment": rejected_comment(reasons)}
    version = result["neoscad"]["version"]
    path = f"results/{version}/{issue}.json"
    return {
        "status": "accepted",
        "version": version,
        "path": path,
        "content": benchlib.canonical(result),
        "comment": accepted_comment(result, path),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--event", help="GitHub event payload (issues event)")
    ap.add_argument("--body-file", help="issue body (instead of --event)")
    ap.add_argument("--issue", type=int, help="issue number (with --body-file)")
    ap.add_argument("--release-dir", help="fixture releases instead of GitHub")
    ap.add_argument("--results", default="results", help="results directory (duplicates, --write)")
    ap.add_argument("--now", help="the current time, UTC (tests)")
    ap.add_argument("--out", required=True, help="decision JSON")
    ap.add_argument("--write", action="store_true", help="write an accepted result under --results")
    a = ap.parse_args()

    if a.event:
        with open(a.event, encoding="utf-8") as f:
            ev = json.load(f)
        issue = ev["issue"]["number"]
        body = ev["issue"].get("body") or ""
    else:
        with open(a.body_file, encoding="utf-8") as f:
            body = f.read()
        issue = a.issue
    if not isinstance(issue, int) or issue <= 0:
        sys.exit("an issue number is needed")
    now = parse_utc(a.now) if a.now else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if a.release_dir:
        release_for = lambda v: LocalRelease(a.release_dir, v)  # noqa: E731
    else:
        release_for = GitHubRelease
    d = decide(body, issue, release_for, now, a.results)
    d["issue"] = issue
    if d["status"] == "accepted" and a.write:
        target = os.path.join(a.results, d["version"], f"{issue}.json")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(d["content"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(f"issue #{issue}: {d['status']}")
    for r in d.get("reasons", []):
        print("  " + r.replace("\n", "\n  "))


if __name__ == "__main__":
    main()
