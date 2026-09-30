"""Tests of scripts/validate.py and scripts/summarize.py on the fixtures.

Everything is offline: releases come from tests/fixtures/releases (a
LocalRelease), and "now" is fixed, so the tests give the same answer on
any day.
"""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import benchlib  # noqa: E402
import summarize  # noqa: E402
import validate  # noqa: E402

NOW = "2026-10-01T00:00:00Z"
RELEASES = os.path.join(FIX, "releases")
VERSION = "0.0.1-fixture"


def release_for(v):
    return validate.LocalRelease(RELEASES, v)


def body(name):
    with open(os.path.join(FIX, "issues", name + ".md"), encoding="utf-8") as f:
        return f.read()


def decide(text, issue=100, results="/nonexistent"):
    return validate.decide(text, issue, release_for, validate.parse_utc(NOW), results)


class Validate(unittest.TestCase):
    def test_fixtures(self):
        with open(os.path.join(FIX, "issues", "expected.json"), encoding="utf-8") as f:
            expected = json.load(f)
        for name, want in sorted(expected.items()):
            with self.subTest(name):
                d = decide(body(name))
                self.assertEqual(d["status"], want["status"], d.get("reasons"))
                text = "\n".join(d.get("reasons", []))
                for s in want["reasons_contain"]:
                    self.assertIn(s, text)

    def test_every_fixture_is_listed(self):
        with open(os.path.join(FIX, "issues", "expected.json"), encoding="utf-8") as f:
            expected = json.load(f)
        names = {f[:-3] for f in os.listdir(os.path.join(FIX, "issues")) if f.endswith(".md")}
        self.assertEqual(names, set(expected))

    def test_oversized_body_is_ignored(self):
        d = decide(body("valid-with-openscad") + " " * (256 * 1024))
        self.assertEqual(d["status"], "ignored")

    def test_accepted_output(self):
        d = decide(body("valid-with-openscad"), issue=12)
        self.assertEqual(d["path"], f"results/{VERSION}/12.json")
        result = json.loads(d["content"])
        self.assertEqual(d["content"], benchlib.canonical(result))
        self.assertIn("speedup over OpenSCAD version 2026.09.23 (manifold)", d["comment"])
        d = decide(body("valid-no-openscad-unpacked-kit"), issue=13)
        self.assertIn("No OpenSCAD comparison", d["comment"])

    def test_the_gh_body_parses_like_the_form(self):
        # neoscad's submit::issue_body writes exactly this layout; a CRLF
        # body (a browser edit) and a trailing Notes section must not matter.
        text = body("valid-with-openscad").replace("\n", "\r\n")
        self.assertEqual(decide(text)["status"], "accepted")

    def test_duplicates_and_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "results")
            d = decide(body("valid-with-openscad"), issue=20, results=results)
            os.makedirs(os.path.join(results, VERSION))
            with open(os.path.join(results, VERSION, "20.json"), "w", encoding="utf-8") as f:
                f.write(d["content"])
            again = decide(body("valid-with-openscad"), issue=21, results=results)
            self.assertEqual(again["status"], "rejected")
            self.assertIn(f"already accepted as `results/{VERSION}/20.json`", again["reasons"][0])
            # Re-checking issue 20 itself (an edit, or a rerun) is not a duplicate.
            self.assertEqual(decide(body("valid-with-openscad"), issue=20, results=results)["status"], "accepted")

    def test_identifying_patterns_spare_real_values(self):
        now = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
        with open(os.path.join(FIX, "results", VERSION, "7.json"), encoding="utf-8") as f:
            r = json.load(f)
        for os_version in ["Microsoft Windows [Version 10.0.26100.4061]",
                           "Ubuntu 22.04.5 LTS (kernel 5.15.167.4-microsoft-standard-WSL2)",
                           "macOS 15.6 (24G84)", "Fedora Linux 41 (Workstation Edition) (kernel 6.11.4-301.fc41.x86_64)"]:
            r["machine"]["os_version"] = os_version
            r["machine"]["cpu"] = "Intel(R) Core(TM) i7-8700 CPU @ 3.20GHz"
            self.assertEqual(validate.sanity(r, now, None), [], os_version)
        for bad in ["C:\\Users\\alice", "/home/alice/x", "alice@example.com", "192.168.1.20",
                    "a4:83:e7:12:34:56", "studio.local"]:
            r["machine"]["os_version"] = bad
            self.assertTrue(validate.sanity(r, now, None), bad)

    def test_kit_content_digest(self):
        # The fixture kit's digest, as bench_core::kit::content_sha256
        # computes it (checked against neoscad on the real 0.1.1 kit when
        # this was written; see tests/README.md).
        with open(os.path.join(RELEASES, "v" + VERSION, f"neoscad-bench-kit-{VERSION}.tar.gz"), "rb") as f:
            self.assertEqual(validate.kit_content_sha256(f.read()),
                             "d04a87a6babf3f20b12ac51ccdefa438f31ed2445a41d92b1f53c47be8ccefb2")

    def test_cli_writes_the_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf = os.path.join(tmp, "body.md")
            with open(bf, "w", encoding="utf-8") as f:
                f.write(body("valid-no-openscad-unpacked-kit"))
            out = os.path.join(tmp, "decision.json")
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate.py"),
                            "--body-file", bf, "--issue", "5", "--release-dir", RELEASES,
                            "--results", os.path.join(tmp, "results"), "--now", NOW,
                            "--out", out, "--write"], check=True, capture_output=True)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertEqual(d["status"], "accepted")
            with open(os.path.join(tmp, "results", VERSION, "5.json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), d["content"])


class Summarize(unittest.TestCase):
    def build(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "results")
            shutil.copytree(os.path.join(FIX, "results"), results)
            d = decide(body("valid-with-openscad"), issue=12)
            with open(os.path.join(results, VERSION, "12.json"), "w", encoding="utf-8") as f:
                f.write(d["content"])
            return summarize.build(results)

    def test_shape(self):
        s = self.build()
        self.assertEqual(s["latest"], VERSION)
        v = s["versions"][VERSION]
        self.assertEqual(v["method_version"], 1)
        self.assertEqual(v["runs"], 2)
        self.assertEqual(v["with_openscad"], 2)
        self.assertEqual(sorted(v["platforms"]), ["linux-x86_64", "macos-aarch64"])
        self.assertEqual(sorted(v["baselines"]), ["aarch64-apple-darwin"])
        self.assertEqual(v["baselines"]["aarch64-apple-darwin"]["source"], "ci-baseline")
        # 8.json was timed with another method: listed, never compared.
        self.assertEqual([e["path"] for e in v["excluded"]], [f"results/{VERSION}/8.json"])
        mac = v["platforms"]["macos-aarch64"]
        run = mac["machines"]["Apple M4 Pro"][0]
        self.assertEqual(run["id"], 12)
        self.assertEqual(mac["speedup"]["quick"]["n"], 1)
        self.assertIsNone(mac["speedup"]["full"])

    def test_speedup_matches_neoscad(self):
        # BenchResult::summary's rule: geometric mean over models both
        # finished. Recomputed here by hand from the per-model speedups.
        s = self.build()
        run = s["versions"][VERSION]["platforms"]["linux-x86_64"]["machines"][
            "AMD Ryzen 7 7840U w/ Radeon 780M Graphics"][0]
        import math
        sp = [m["speedup"] for m in run["models"].values() if m["speedup"] is not None]
        self.assertEqual(len(sp), run["compared"])
        self.assertAlmostEqual(math.exp(sum(map(math.log, sp)) / len(sp)), run["geomean_speedup"], places=2)

    def test_deterministic(self):
        a = json.dumps(self.build(), sort_keys=True)
        b = json.dumps(self.build(), sort_keys=True)
        self.assertEqual(a, b)

    def test_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = summarize.build(os.path.join(tmp, "results"))
        self.assertEqual(s, {"format": 1, "latest": None, "version_order": [], "versions": {},
                             "skipped_files": []})

    def test_misfiled_results_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "results")
            shutil.copytree(os.path.join(FIX, "results"), results)
            shutil.copy(os.path.join(results, VERSION, "7.json"), os.path.join(results, VERSION, "ci-baseline-x86_64-unknown-linux-gnu.json"))
            s = summarize.build(results)
        self.assertEqual(s["skipped_files"][0]["path"], f"results/{VERSION}/ci-baseline-x86_64-unknown-linux-gnu.json")

    def test_version_order(self):
        vs = ["0.1.1", "0.2.0-rc.1", "0.10.0", "0.2.0", "0.2.0-rc.2"]
        self.assertEqual(sorted(vs, key=benchlib.version_key),
                         ["0.1.1", "0.2.0-rc.1", "0.2.0-rc.2", "0.2.0", "0.10.0"])


if __name__ == "__main__":
    unittest.main()
