# NeoSCAD community benchmarks

Timings of official [NeoSCAD](https://github.com/neoscad/neoscad)
releases on people's own machines, most of them alongside OpenSCAD on the
same machine, collected per release. They are shown on
[neoscad.org/community.html](https://neoscad.org/community.html), and
the raw results are all here.

Every release also benchmarks itself on GitHub's runners (Linux x86_64 and
aarch64, macOS arm64, Windows x86_64): the *release baseline*, the same
four machine types for every version.

## Add your result

Install an official release (the archives, installers, Homebrew, Scoop,
the `.deb` and `.rpm` packages or the Docker image) and run:

```sh
neoscad bench --submit
```

It downloads the release's bench kit, finds OpenSCAD if it is installed
and asks whether to time it too, runs 14 models (a few minutes; `--quick`
runs 7), then shows you the exact JSON and asks before submitting it as an
issue here, through the GitHub CLI if it is logged in or a pre-filled form
in the browser otherwise.

**Include OpenSCAD if you can.** A result without it is accepted, but the
comparison with OpenSCAD on the same machine is what makes a result most
useful: absolute times say as much about the machine as about NeoSCAD.
`--openscad /path/to/openscad` picks a particular build; newer builds run
with `--backend=manifold`, older ones with CGAL, and the version and
backend are recorded.

Close other work first, and plug in a laptop: the load average and
battery state are recorded, and a busy machine is a slow one.

Full details (flags, the kit, how a model is timed):
[docs/community-bench.md](https://github.com/neoscad/neoscad/blob/main/docs/community-bench.md).

## Rules

- **Official release binaries only.** A self-built binary may use other
  flags, another toolchain or local patches, and its times would be filed
  under a release they do not describe. Every release publishes
  `neoscad-executables.sha256sums`, the SHA-256 of the executable in each
  target's archive; the result's `neoscad.sha256` must be on its target's
  line. (The macOS app's bundled CLI is a separate build and not on the
  list: use Homebrew or the archive.)
- **The release's own bench kit**, unmodified.
- **One result per issue**, unedited. Notes go in the form's Notes field.
- `source` is `user`. Release baselines are committed by NeoSCAD's
  release workflow, never through issues.

## What is collected

The JSON `neoscad bench` writes (schema 1,
[`bench/result.schema.json`](https://github.com/neoscad/neoscad/blob/main/bench/result.schema.json)):
NeoSCAD's version, target and executable hash; the kit's version and
hashes; the timing method; the machine's OS and version, architecture, CPU
name, a Mac's model identifier, core counts, memory, whether it was on
battery, the load average before and after, and whether it ran under
Rosetta; the OpenSCAD version and backend; and each model's times.

No host name, user name, file path, IP address, serial number or MAC
address is read, so none can be in a result, and the OpenSCAD path is
used to run it and never recorded. Everything submitted is public, along
with your GitHub account as the issue's author, and stays in this
repository's history; `--submit` prints the JSON before asking. See
[What is collected](https://github.com/neoscad/neoscad/blob/main/docs/community-bench.md#what-is-collected).

## How results are checked

[`validate.yml`](.github/workflows/validate.yml) runs
[`scripts/validate.py`](scripts/validate.py) on every issue opened or
edited whose body has a `### Result JSON` section (the label is not
needed: a `gh` submission cannot set it). It re-checks everything, since a
client can be made to say anything:

1. The section holds one fenced JSON object that parses; bodies over
   256 KB are ignored.
2. `source` is `user`.
3. `neoscad.version` is a published release of neoscad/neoscad, and the
   result matches `bench/result.schema.json` at its tag (JSON Schema
   2020-12, with a pinned `jsonschema`). Releases before community
   benchmarks have no schema and are refused.
4. `neoscad.official` is true and `neoscad.sha256` is the release's
   executable for `neoscad.target`, from the release's
   `neoscad-executables.sha256sums`.
5. `kit.version` is the release's, and `kit.archive_sha256` is the
   release's `neoscad-bench-kit-<version>.tar.gz.sha256` (for a result run
   from an unpacked kit, `kit.content_sha256` is compared with the
   release kit's contents instead).
6. `method.version` is a known timing method (currently 1).
7. Plausibility: every time above zero and within the timeout, each
   best time no slower than its runs, OpenSCAD present for every model or
   for none, timestamps in order and not before the release or in the
   future, and no string that looks like a path, host name, e-mail, IP or
   MAC address.
8. Not an exact copy of a result already accepted.

A result that passes is committed as `results/<version>/<issue>.json`,
`summary.json` is rebuilt in the same commit, and the issue gets a comment
with the result's summary, the `accepted` label, and is closed. One that
fails gets a comment listing every reason and the `rejected` label, and
stays open: edit it and it is checked again.

## Layout

```
results/<version>/<issue>.json               accepted submissions
results/<version>/ci-baseline-<target>.json  the release baseline
summary.json                                 what neoscad.org shows (rebuilt by scripts/summarize.py)
scripts/                                     validate.py, summarize.py, benchlib.py
tests/                                       fixtures and tests (tests/run.sh)
```

Results are stored as submitted, with sorted keys. `summary.json` groups
them by version, then platform (OS and architecture), then CPU, with each
run's per-model best times, its geometric mean, and (with OpenSCAD) the
geometric-mean speedup over the models both finished, computed as
`neoscad bench` prints it. Per version and platform it gives the number of
runs with and without OpenSCAD and the median and range of the speedup,
separately for quick and full runs (they time different models) and for
OpenSCAD's Manifold and CGAL backends (which differ several-fold). Only
results with the release's own kit and one timing method are compared;
baselines are listed apart and never mixed into users' figures.

To run the checks locally:

```sh
python3 -m pip install --no-deps -r scripts/requirements.txt
tests/run.sh
python3 scripts/summarize.py --check
```

## Licence

The results and `summary.json` are dedicated to the public domain under
[CC0 1.0](LICENSE): use them for anything, no attribution needed
(though a link back is welcome). By submitting a result you agree to that
dedication. The scripts are under CC0 1.0 too.
