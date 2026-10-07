# Methodology

**Frozen-study protocol:** It selects one valid primary attempt, permits documented infrastructure-invalidated
replacements, and reports valid-measurement success separately from full-suite
coverage and supplemental retries. Schema 2 records the attempts, incidents,
selection and cohort totals.

## System under evaluation

The model interprets the task and selects analytical actions. Terra provides the agent runtime and geospatial tools, durable jobs,
workflow execution, access control, artifact inspection and catalog/map delivery.
Deterministic processors perform the numerical and geometric calculations.

The claim under evaluation is end-to-end task fulfillment, including the required
answer, artifacts and delivery. Successful processor execution alone is not a pass.
This study does not isolate model capability from the surrounding system.

## Recorded configuration

The manifest records the application commit, benchmark revision, source editions/checksums,
model/deployment identity, reasoning effort, runtime version, instruction/tool
fingerprints, grader identity, attempt policy, caps, concurrency, and all human or
scripted assistance. Unavailable measurements remain null.

The protocol documents fixture preparation and adaptations to wording, reference
calculations, source inputs, missing-data policy, units, boundary predicates and
output requirements. Expected answers and reference outputs were withheld from
the agent.

## Outcomes and denominators

Report computational tasks and qualitative controls separately. For each selected
task, preserve all attempts and select the first valid primary measurement. Classify
it as pass, partial, fail or timeout. Unmeasured cases are setup-blocked or invalid
and remain in coverage, outside valid-measurement accuracy denominators. We never count
a missing observation as a successful refusal without testing the reference-defined
limitation behavior. Correct artifacts without a required timely final answer remain
incomplete.

## Verification

Use the frozen independent task graders, with documented tolerances and conventions.
As applicable, check selected feature identities, geometry, raster values and masks,
grid/CRS/units, coverage, aggregate statistics, map delivery and final-answer agreement.
The independent calculations are our evaluation code, not an external third-party
audit. Retain failures and identify any evaluator corrections with a new version.

The frozen outcomes include known unit-label and geography/coverage edge cases.
Qualitative controls use an explicit, unblinded AI-assisted operator review of the
complete accepted answer and recorded evidence against predeclared rubrics.

The publication utilities check IDs, required measurements, denominators, file hashes
and consistency. They do not substitute for the task graders. The included
generic artifact comparison utility also requires an independently produced reference.

## Efficiency

Use observed end-to-end duration, including queueing and timeouts. Report the coverage
of token and cost measurements; retain unknowns as null. Distinguish per-task model
cost, infrastructure cost and development-campaign spending. Concurrency makes summed
task durations different from elapsed campaign time.

## Comparison and limitations

GeoBenchX uses a ReAct agent with 23 tools, up to 25 iterations and LLM-judge scoring.
Terra has different tools, budgets, model settings and artifact-based grading. These
results are not directly comparable to the published model scores.
