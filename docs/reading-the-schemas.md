# How to read the schemas

The schemas live under `wyred-contract/schemas/`: one
`<kind>.schema.json` per artifact kind, plus a shared `common.defs.json`
`$defs` library. Each is standard JSON Schema **draft 2020-12** — an external
consumer can validate it with `ajv` or python-`jsonschema` unchanged. In this
repo they are checked by the dependency-free
[`validate.py`](validate.md) instead, which implements the exact draft-2020-12
subset the schemas actually use and nothing more.

This page is a reading guide. The schema files and `EMIT_CONTRACT.md` are the
normative sources; nothing below restates them.

## Descriptive of the goldens (the precedence rule)

The schemas were **extracted from** the ga019 goldens, not written ahead of
them. The stated precedence — read it in any schema's top-level `description` —
is **goldens > harness/engine code > `EMIT_CONTRACT.md` prose**. Wherever those
three disagreed, the goldens won and the disagreement was recorded as a
numbered **finding** (`F1`…`F12`) rather than silently absorbed. The findings
are summarized in `EMIT_CONTRACT.md` (the changelog, and inline in Parts A–E)
and each one is also called out in the `description` of the schema it touches.

Practical consequence: when a schema looks tighter or looser than the prose
you remember, the schema (following the goldens) is right and the prose is the
stale tier. For example `l2.schema.json` types every net's `voltage` as
`number | null` and ground nets carry `0.0` — that is finding **F3**, and it
contradicts an "else `None`" sentence in the Part A field table on purpose.

## What each schema file looks like

Read a schema top-down and four things orient you before any field:

| position | what it tells you |
|---|---|
| `$schema` | `https://json-schema.org/draft/2020-12/schema` — it is standard draft 2020-12. |
| `$id` | `https://wyred.dev/contract/v0/<kind>.schema.json` — a stable namespace, **not** a URL that must resolve. The `/v0/` segment is the breaking-change axis. |
| `x-wyred-contract` | the version stamp: `{"contract": "v3-ga019", "schema_rev": 0}`. |
| `title` / `description` | the human title, and a `description` that records the extraction provenance — **which producer function emits this shape** (e.g. `schema.to_json`), the emit-only-when-set optionality, the open-vs-closed vocabularies, and the `Fn` findings that apply. |

Then the body is ordinary draft-2020-12: `type`, `required`, `properties`,
`additionalProperties` (almost always `false` — the one open shape is the
free-form `attrs` dict), and a `$defs` block of local sub-shapes.

Reveal the top-level shape of a schema without opening an editor:

<!-- cwd: wyred-contract -->
```console
$ python3 -c 'import json; s=json.load(open("schemas/l2.schema.json")); print("required:", s["required"]); print("defs:", sorted(s["$defs"]))'
required: ['components', 'nets', 'escalations', 'invariants']
defs: ['attrs', 'component', 'invariant', 'net', 'node', 'terminal']
# expect: required: ['components', 'nets', 'escalations', 'invariants']
```

## The shared `$defs` library and the two `$ref` styles

`common.defs.json` is a `$defs` container of sub-shapes reused across kinds
(the allocation-record family, the `stamp`, the connector-pinout row, and so
on). It is **never validated directly** against an instance — it is only ever
referenced. The schemas use exactly **two** `$ref` styles, and no others:

- **local** — `#/$defs/<name>`: a sub-shape defined in the same file (e.g.
  `l2.schema.json`'s `net` refs `#/$defs/node`).
- **relative-file** — `<file>.json#/$defs/<name>`: a sub-shape in a sibling
  file (e.g. `l1.schema.json` refs
  `common.defs.json#/$defs/allocation_record`).

Anything else — a remote URL, an absolute path, a `..` segment, a non-`$defs`
fragment — is rejected by `validate.py` at load time (fail-closed on `$ref`
style, so a schema can never quietly out-grow the validator). The full rule is
in the `validate.py` module docstring and its `SchemaSet.resolve_ref`.

## Optional keys: emit-only-when-set

Most artifacts omit a key rather than emit it at its default (`schema_l1`'s
`_put` helper, the l2 `_to_json` methods). A schema marks these by leaving them
out of `required` while still listing them under `properties`. So an instance
that validates may legitimately **lack** optional keys — their absence is the
default, not an error. Each schema's `description` names which keys are always
emitted and which are emit-only-when-set.

## Open vs closed vocabularies

Some string fields are closed enums (e.g. a terminal's `role`, a net's `kind`,
`chosen_by`); others are deliberately **open** strings. The largest open one is
finding **F2**: `Component.kind` is an open string (35 kinds observed across
the goldens vs 12 declared in engine code), so a consumer **must** accept kinds
outside any list. `l2.schema.json`'s `component.kind` description carries the
non-normative observed vocabulary for orientation. Interface names
(`iface`, `provides`) are open for the same reason.

Read the version stamp straight off a schema:

<!-- cwd: wyred-contract -->
```console
$ python3 -c 'import json; print(json.load(open("schemas/l1.schema.json"))["x-wyred-contract"])'
{'contract': 'v3-ga019', 'schema_rev': 0}
# expect: v3-ga019
```

`contract` names the `EMIT_CONTRACT.md` version the schema set was extracted
from, qualified by the golden corpus it describes; `schema_rev` increments on a
ratified assertion change that is not a contract bump; the `/v0/` in `$id` moves
only on a backward-incompatible break. The full convention is
`EMIT_CONTRACT.md` Part E, "Schema stamping & versioning convention" — its
mechanical enforcement (stamp present, consistent across siblings) is
`tests/run_schema_tests.py` plus the stamp check.

## Cross-reading a kind, end to end

To understand one artifact kind:

1. Open its schema, `wyred-contract/schemas/<kind>.schema.json`, and read the
   `description` (provenance + producer + findings).
2. Read the matching `EMIT_CONTRACT.md` Part (the [artifact-kind
   index](artifact-kinds.md) tells you which Part, and gives an example
   golden).
3. Open that golden under `wyred-contract/goldens/ga019/` and read it against
   the schema.
4. Validate it, to confirm your reading matches the checker (see
   [`validate.py` usage](validate.md)):

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py --file goldens/ga019/intent_01_sensor_node.l1.json
1/1 valid
# expect: 1/1 valid
```

## The schemas really do match the goldens

That the schemas are descriptive of the goldens is not a claim to take on
faith — it is an oracle. `tests/run_schema_tests.py` drives `validate.py` as a
subprocess to assert two things: the pristine golden tree validates
(`114/114 valid`, exit 0), and every committed mutation fixture under
`tests/fixtures/` is **rejected** at its expected JSON pointer and keyword. A
golden hand-edited to pass, or a schema loosened so a mutant slips through,
turns this run red.

<!-- cwd: wyred-contract -->
```console
$ python3 tests/run_schema_tests.py
PASS pristine: 114/114 valid, exit 0
SCHEMA TESTS: PASS (0 failure(s))
# expect: SCHEMA TESTS: PASS
```
