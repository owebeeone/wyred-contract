# `validate.py` usage

`wyred-contract/tools/validate.py` is a dependency-free JSON-Schema validator
for the emit contract. It is pure standard library (no `jsonschema`, no
third-party imports) and purpose-built for the exact draft-2020-12 **subset**
the contract schemas use — see [how to read the schemas](reading-the-schemas.md)
and the tool's own module docstring for the fail-closed design (an unknown
keyword or an ill-styled `$ref` aborts at load time rather than being silently
ignored). The schema documents stay fully standard, so external consumers can
still validate them with `ajv` or python-`jsonschema` unchanged.

This page documents the CLI. The validator's behaviour is the specification for
what a valid artifact is *mechanically*; the shapes themselves are the schemas.

## Synopsis

```text
python3 tools/validate.py [--schemas DIR] [--tree DIR | --file PATH] [--canonical]
```

Run it from the `wyred-contract` repo root (so the default `schemas/` and
`goldens/ga019/` paths resolve).

## Flags

| flag | effect | default |
|---|---|---|
| `--schemas DIR` | directory of `*.schema.json` files to validate against | `<repo>/schemas` |
| `--tree DIR` | validate every `*.json` in this directory | `<repo>/goldens/ga019` |
| `--file PATH` | validate a single artifact file (overrides `--tree`) | — |
| `--canonical` | additionally byte-compare each file against its canonical serialization | off |

There are no other flags. Each is greppable in `tools/validate.py` (the
`argparse` block in `main`).

### How the schema is chosen

You never name a schema per file. The artifact **kind** is the
second-from-last dotted segment of the filename — `foo.l2.json` → kind `l2` →
`l2.schema.json` (the tool's `_kind_of`). A filename that is not
`<name>.<kind>.json`, or a kind with no matching schema, is a setup error (see
below). This is the same mapping the [artifact-kind index](artifact-kinds.md)
tabulates.

### The `--canonical` convention

The goldens are serialized canonically as
`json.dumps(obj, indent=2, sort_keys=True)` followed by a single trailing
newline. That is a **serialization convention, kept out of the schemas** (it is
not a shape a JSON Schema can express). `--canonical` byte-checks it in
addition to schema validation, so a semantically-valid but
differently-formatted file is still flagged. The convention is spelled out in
the `validate.py` module docstring and its `_canonical_ok`.

## Exit codes

Mirroring wyred-audit's convention:

| exit | meaning |
|---|---|
| `0` | every file valid (and, with `--canonical`, every file canonical) |
| `1` | at least one validation or canonical **failure** |
| `2` | a **setup error** — bad/missing schemas dir, an unresolvable `$ref`, a non-whitelisted schema keyword, a filename with no derivable kind, missing input |

## Output format

One line per failure:

```text
FAIL <file>  <json-pointer>  [<keyword>]  <message>
```

then a summary `N/TOTAL valid` (and `N/TOTAL canonical` under `--canonical`).
The JSON pointer locates the offending value; the keyword names which assertion
failed. Setup errors print `SETUP ERROR: <message>` to stderr.

## Examples

Validate the default golden tree against the default schemas:

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py
114/114 valid
# expect: 114/114 valid
```

Also enforce the canonical serialization:

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py --canonical
114/114 valid
114/114 canonical
# expect: 114/114 canonical
```

Validate one file (kind inferred from the name):

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py --file goldens/ga019/intent_01_sensor_node.l2.json
1/1 valid
# expect: 1/1 valid
```

Point `--tree` and `--schemas` explicitly (here at their defaults, to show the
flags):

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py --schemas schemas --tree goldens/ga019
114/114 valid
# expect: 114/114 valid
```

### A validation failure (exit 1)

The committed mutation fixtures under `tests/fixtures/` are artifacts the
emitter would never produce. Each is rejected at a specific pointer and
keyword — here an out-of-vocabulary terminal `role`:

<!-- cwd: wyred-contract -->
<!-- expect-fail: an out-of-vocabulary enum value is rejected; exit 1 -->
```console
$ python3 tools/validate.py --file tests/fixtures/mut_l2_bad_enum.l2.json
FAIL mut_l2_bad_enum.l2.json  /components/0/terminals/0/role  [enum]  'gpio' is not one of ['power_in', 'power_out', 'ground', 'signal', 'passive', 'logic_in', 'logic_out']
0/1 valid
```

(The block above is asserted to **fail**: `validate.py` exits `1`, which is the
correct behaviour and what the doc-test runner checks.)

### A setup error (exit 2)

A problem with the invocation or the schema set itself — distinct from a
mundane validation failure — exits `2`:

<!-- cwd: wyred-contract -->
<!-- expect-fail: a missing schemas dir is a setup error; exit 2 -->
```console
$ python3 tools/validate.py --schemas /no/such/dir
SETUP ERROR: schemas dir not found: /no/such/dir
```

## As a consumer would call it

`validate.py` is invoked **as a subprocess** by `tests/run_schema_tests.py` —
the way a downstream consumer (or the future Rust rewrite) would drive it — to
assert the pristine goldens pass and every mutant fails at its expected
location. That test is the acceptance oracle for the schemas; see
[how to read the schemas](reading-the-schemas.md#the-schemas-really-do-match-the-goldens).
