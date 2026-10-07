# Frozen verification code

This directory contains the standalone subset of the evaluator used for the
Terra GeoBenchX study: task definitions, reference calculations, artifact graders
and synthetic tests. The 53 Python modules in `src/terra_bench/` retain their
frozen contents. `checksums.json` identifies the included files.

The product runner, service integration, provisioning and internal publishing
code are not part of this package. There is no command here to run Terra.

`required-inputs.json` records the source identities needed for full analytical
regrading; those bulk inputs and complete agent-produced outputs are not included.
