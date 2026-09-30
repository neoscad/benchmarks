### Result JSON

```json
{
  "schema": 1,
  "source": "user",
  "neoscad": {
    "version": "0.0.1-fixture",
    "target": "aarch64-apple-darwin",
    "sha256": "d2731a88a9893184279dda21b06dd90a5816d5d2bf2b508aca4a2848d9b83225",
    "official": true,
    "official_check": "matched"
  },
  "kit": {
    "version": "0.0.1-fixture",
    "archive_sha256": "8eec8c60ac6c997de5a419792741ac06a0bace1d3fc11f65b8fdc28984d938fa",
    "content_sha256": "ae65871e6d7e2b83b03c15a016e1bab5e7e174129df17b9da34dbbe2e4246445",
    "neoscad_commit": "7c4ebc0660b8a5206fabb55dd2d20c4031319272",
    "bosl2_commit": "9948313433166f58701a41f6e03cf19d6a70f42a",
    "openscad_commit": "28fe66bcaf3e89239153cd16c34499c541d2841e"
  },
  "method": {
    "version": 1,
    "runs": 1,
    "cold_start_runs": 5,
    "single_run_over_s": 60.0,
    "timeout_s": 300.0,
    "quick": true
  },
  "machine": {
    "os": "macos",
    "os_version": "macOS 27.0 (26A428)",
    "arch": "aarch64",
    "cpu": "Apple M4 Pro",
    "hardware_model": "Mac16,7",
    "cores_logical": 14,
    "cores_physical": 14,
    "cores_performance": 10,
    "cores_efficiency": 4,
    "memory_bytes": 51539607552,
    "on_battery": false,
    "load_before": [
      8.95,
      7.44,
      7.4
    ],
    "load_after": [
      8.39,
      7.35,
      7.36
    ],
    "translated": false
  },
  "threads": 14,
  "openscad": {
    "version": "OpenSCAD version 2026.09.23",
    "backend": "manifold",
    "args": [
      "--backend=manifold"
    ]
  },
  "cold_start": {
    "neoscad": {
      "rc": 0,
      "timed_out": false,
      "runs_s": [
        0.0053,
        0.003,
        0.0031,
        0.003,
        0.0029
      ],
      "best_s": 0.0029,
      "cpu_s": [
        0.007,
        0.003,
        0.004,
        0.003,
        0.003
      ]
    },
    "openscad": {
      "rc": 0,
      "timed_out": false,
      "runs_s": [
        0.0482,
        0.0467,
        0.0466,
        0.0476,
        0.0465
      ],
      "best_s": 0.0465,
      "cpu_s": [
        0.049,
        0.047,
        0.047,
        0.048,
        0.047
      ]
    }
  },
  "models": {
    "bosl_gears__003": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0498
        ],
        "best_s": 0.0,
        "cpu_s": [
          0.053
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.219
        ],
        "best_s": 0.219,
        "cpu_s": [
          0.217
        ]
      }
    },
    "bosl_screws__001": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.1723
        ],
        "best_s": 0.1723,
        "cpu_s": [
          0.346
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.6621
        ],
        "best_s": 0.6621,
        "cpu_s": [
          1.168
        ]
      }
    },
    "csg_deep_union": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0432
        ],
        "best_s": 0.0432,
        "cpu_s": [
          0.198
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.1343
        ],
        "best_s": 0.1343,
        "cpu_s": [
          0.291
        ]
      }
    },
    "ex_csg_basic": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0078
        ],
        "best_s": 0.0078,
        "cpu_s": [
          0.015
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0629
        ],
        "best_s": 0.0629,
        "cpu_s": [
          0.12
        ]
      }
    },
    "extrude_twist": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0378
        ],
        "best_s": 0.0378,
        "cpu_s": [
          0.039
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.2174
        ],
        "best_s": 0.2174,
        "cpu_s": [
          0.217
        ]
      }
    },
    "mink_convex": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0241
        ],
        "best_s": 0.0241,
        "cpu_s": [
          0.029
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.0702
        ],
        "best_s": 0.0702,
        "cpu_s": [
          0.079
        ]
      }
    },
    "text_30lines": {
      "neoscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.1214
        ],
        "best_s": 0.1214,
        "cpu_s": [
          0.202
        ]
      },
      "openscad": {
        "rc": 0,
        "timed_out": false,
        "runs_s": [
          0.68
        ],
        "best_s": 0.68,
        "cpu_s": [
          0.662
        ]
      }
    }
  },
  "skipped": {},
  "started_at": "2026-09-30T16:05:42Z",
  "finished_at": "2026-09-30T16:05:45Z"
}
```

### Notes

_No response_
