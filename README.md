# Terra: geospatial workflows, with inspectable evidence

For an introduction and a worked example, read [Introducing Terra](https://blog.exialabs.com/p/introducing-terra).

The evaluation began on 2026-10-07 UTC and measured one frozen version of Terra.
The measurement policy selects the first valid
primary attempt, with documented replacements for infrastructure interruptions.

| Frozen primary results | Passed | Rate |
| --- | ---: | ---: |
| Computational tasks | 115 / 133 | **86.5%** |
| Qualitative controls | 67 / 68 | **98.5%** |

**201/202 questions were measured.** One lacked required source data.
Verified infrastructure interruptions received replacements. A separate timeout
retry passed, but does not change the primary scores.

All 229
physical attempts are retained: two repair trials, 201 initial primaries,
25 incident-authorized replacements and one supplemental attempt.

Terra is a geospatial agent being developed by Exia Labs to turn analytical
questions into processor workflows and publish the resulting datasets into
catalogs. We design and tune its tools, instructions, context and orchestration
for investigation, computation, inspection, correction and reusable delivery.
This is harness engineering, not model fine-tuning.

This repo contains bounded, sanitized study evidence and the frozen evaluation code

## Check the included evidence

Requires Node.js 22 or later; there are no npm dependencies.

```sh
npm test
npm run validate
```

These commands check evidence hashes, task identities, attempt selection and reported totals.

## What this measurement means

We report **the first valid primary attempt per selected task on one
frozen application version**. A verified infrastructure interruption can have a
documented replacement. Every physical attempt remains in the manifest, including
repairs and supplemental timeout retries; neither enters the primary score.

Computational tasks and qualitative controls have separate valid-measurement
denominators. Genuine partial results, failures and timeouts stay in those
denominators. Setup-blocked and infrastructure-unmeasured cases stay prominently
visible in full-suite coverage, not mislabeled analytical failures.
Missing measurements are `null`, not zero.

This is not an official GeoBenchX submission, a controlled model comparison or an
external audit. Review the original benchmark and the differences described in
the methodology before interpreting the score.

## Evidence and reproducibility

- `releases/<release-id>/release.json`: frozen configuration and per-task results.
- `releases/<release-id>/evidence/<task-id>.json`: public question, final answer,
  observable activity, workflow and preview metadata.
- `releases/<release-id>/assets/`: only small, redistributable raster previews.
- `scripts/release.mjs`: identity, coverage and file-integrity checks.
- `scripts/verify_artifacts.py`: independent generic vector/raster comparisons.
- `verification/`: the standalone subset of frozen task-specific graders,
  reference calculations, tests, dependency pins and input prerequisites.
- [Offline report](releases/terra-geobenchx-v1/report.html),
  [summary PNG](releases/terra-geobenchx-v1/assets/study-summary.png), and
  [operational accounting](releases/terra-geobenchx-v1/assets/operations.png).

Full GIS regrading requires source and output files not included in this package.
The [input inventory](verification/required-inputs.json) records the required
source identities. Checksums alone do not recreate files.

See [NOTICE](NOTICE.md) for attribution and [METHODOLOGY](METHODOLOGY.md) for the
study limitations. Terra's application source and service integrations are not
included.
