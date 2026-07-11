# wyred-contract — boundary rules

- **Single-writer.** Changes land only via an accepted proposal in wyred-wz/dev-docs/ (see DecisionLog). Never edit the contract as a side effect of feature work in another repo.
- Every change bumps the contract version and is recorded in this repo's changelog section of EMIT_CONTRACT.md.
- goldens/ are normative fixtures: downstream repos test against them. Regenerating goldens is a contract event, not a routine act.
- No code lives here beyond schema validation helpers. First task: extract JSON Schemas from EMIT_CONTRACT.md prose.
