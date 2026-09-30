# Tests

`tests/run.sh` runs `test_scripts.py`: the validator and the summariser
against these fixtures, offline, with "now" fixed at 2026-10-01.

| Path | What |
|---|---|
| `fixtures/releases/v0.0.1-fixture/` | A fictional release standing in for GitHub: the real `bench/result.schema.json` (schema 1), an executable checksum list with made-up hashes for five targets, a two-file stand-in bench kit with its `.sha256`, and `release.json` (publish date) |
| `fixtures/releases/v0.1.1/` | The real 0.1.1 release as it is: published before community benchmarks, so no schema at its tag |
| `fixtures/issues/*.md` | Issue bodies in the layout `neoscad bench --submit` and the form write; `expected.json` gives each one's outcome and phrases its reasons must contain |
| `fixtures/results/0.0.1-fixture/` | Committed results for the summariser: a release baseline, a user run, and one timed with another method (excluded) |

The results inside are derived from two real `neoscad bench --quick` runs
on one Mac (one with OpenSCAD 2026.09.23, one without). Those runs used a
**local development build, not an official release** (`official_check:
unavailable`); `local-build-unofficial.md` is that run as it was, and is
rejected. The accepted fixtures had their version, executable hash and
kit fields rewritten to match the fictional release. The Linux run in
`results/0.0.1-fixture/7.json` and `8.json` is synthetic (the Mac run's
times scaled, with made-up machine facts).

The kit content digest (`validate.kit_content_sha256`) was checked against
neoscad's own (`bench_core::kit::content_sha256`) on the real 0.1.1 kit:
both gave `308299e8…cbf30` for the kit built from neoscad `5e1c61d`.
