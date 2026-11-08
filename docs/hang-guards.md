# Focused check hang guards and machine profile

These limits identify UNKNOWN (hang-guard trip), never a resource or performance
assertion. A subprocess timeout remains an error, never a successful estimate.

| Class | Wall limit | Measured command and baseline | Machine / date |
| --- | --- | --- | --- |
| short | 30 seconds | seven focused CLI tests: 2.44 s wall, 2.45 s CPU; `cargo build --offline --locked -j 4`: 0.35 s wall, 0.43 s CPU | Spiral, 2026-11-08 UTC |
| short | 30 seconds | fifteen `python3 -I -B -m unittest discover -s tests -p test_recompute.py -v` tests: 0.52 s wall, 0.53 s CPU | Spiral, 2026-11-08 UTC |
| moderate | 300 seconds | `test_estimate.py -k CommandLine`: twelve CLI/certificate/differential tests, 19.31 s wall, 19.34 s CPU | Spiral, 2026-11-08 UTC |
| moderate | 300 seconds | all thirteen `cargo test --offline --locked -j4 --test recompute_witness -- --test-threads=1 --nocapture` tests, including the exhaustive family: 10.22 s wall, 10.11 s CPU | Spiral, 2026-11-08 UTC |
| long | 900 seconds | focused `scripts/check` (existing suites, witnesses/family, formatting, Clippy and shell syntax): 57.60 s wall, 122.45 s CPU | Spiral, 2026-11-08 UTC |

Machine factor is 1 on Spiral (64 logical CPUs, approximately 58 GiB available
at measurement). Each limit exceeds its measured wall baseline by over 10x.
Use build width at most 4 and one focused CLI test process; leave at least 16 CPUs and
16 GiB available for concurrent jobs. Other hosts must derive a factor from
their measurements and available resources. This table covers these focused
checks only; it does not set an allowance for a full gate or large-object run.

`tests/test_cli_report.py` uses the named short-class constant. Record wall and
CPU seconds in the job receipt with `/usr/bin/time -p`. For shell commands use
`timeout` with this class's limit; exit 124 is UNKNOWN. Do not interpret it as
a test failure or silently retry with a changed limit.
