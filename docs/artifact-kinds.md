# The artifact-kind index

The builder emits a family of JSON artifacts per intent. Each **kind** has a
file suffix `*.<kind>.json`, a schema `wyred-contract/schemas/<kind>.schema.json`,
and one or more golden examples under `wyred-contract/goldens/ga019/`. This
page is the map into them.

It is a **navigation aid, not a specification**. Each kind is normatively
defined by its schema file; the one-sentence purpose and the emitting producer
of each are in `EMIT_CONTRACT.md` Part E (and Parts A–C for the core three).
This table points at those sources — it does not restate them.

## The eleven kinds

| kind | file suffix | schema | specified in | example golden |
|---|---|---|---|---|
| `l1` | `*.l1.json` | `schemas/l1.schema.json` | Part B (+ embedded Part C) | `goldens/ga019/intent_01_sensor_node.l1.json` |
| `l2` | `*.l2.json` | `schemas/l2.schema.json` | Part A | `goldens/ga019/intent_01_sensor_node.l2.json` |
| `alloc` | `*.alloc.json` | `schemas/alloc.schema.json` | Part C intro + Part E | `goldens/ga019/intent_01_sensor_node.alloc.json` |
| `bom` | `*.bom.json` | `schemas/bom.schema.json` | Part E | `goldens/ga019/intent_01_sensor_node.bom.json` |
| `pinmap` | `*.pinmap.json` | `schemas/pinmap.schema.json` | Part E | `goldens/ga019/intent_01_sensor_node.pinmap.json` |
| `records` | `*.records.json` | `schemas/records.schema.json` | Part E | `goldens/ga019/intent_01_sensor_node.records.json` |
| `baseline` | `*.baseline.json` | `schemas/baseline.schema.json` | Part E | `goldens/ga019/intent_05a_pinned.baseline.json` |
| `connlock` | `*.connlock.json` | `schemas/connlock.schema.json` | Part E | `goldens/ga019/mppt_2420_hc_reva.connlock.json` |
| `pinmapdiff` | `*.pinmapdiff.json` | `schemas/pinmapdiff.schema.json` | Part E | `goldens/ga019/watchy_v1_draft_btn3.pinmapdiff.json` |
| `lifecycle` | `*.lifecycle.json` | `schemas/lifecycle.schema.json` | Part E | `goldens/ga019/watchy_v1_revb.lifecycle.json` |
| `cir` | `*.cir.json` | `schemas/cir.schema.json` | Part E | `goldens/ga019/intent_10_spice_divider.cir.json` |

The list of kinds is not hand-maintained truth — it is whatever
`schemas/*.schema.json` exists. Enumerate it straight from the directory:

<!-- cwd: wyred-contract -->
```console
$ ls schemas/*.schema.json | sed 's#.*/##; s#\.schema\.json##'
alloc
baseline
bom
cir
connlock
l1
l2
lifecycle
pinmap
pinmapdiff
records
# expect: pinmapdiff
```

`common.defs.json` is **not** in that list on purpose: it is the shared `$defs`
library (see [how to read the schemas](reading-the-schemas.md)), referenced by
the per-kind schemas, never a kind of its own.

## Core three vs standalone

- **The per-intent core three** are the L1 intent doc (`l1`, Part B), the L2
  netlist (`l2`, Part A), and the **allocation record embedded inside the L1
  doc** under `"allocation"` (Part C). The embedded record is the
  `allocation_record` `$def` in `common.defs.json`.
- **Everything else is a standalone data-path / lifecycle artifact** indexed by
  `EMIT_CONTRACT.md` Part E — the prose historically covered only the core
  three (finding **F1**), and Part E closes that gap.

!!! warning "Embedded record ≠ standalone `alloc` wrapper"
    Do not conflate the allocation **record** embedded in the `l1` doc
    (`common.defs.json#/$defs/allocation_record`) with the standalone
    `*.alloc.json` **wrapper** artifact (`schemas/alloc.schema.json`), which is
    a wider object *around* that record. `EMIT_CONTRACT.md` Part C spells out
    the distinction.

## The `.cir` deck is deliberately outside the JSON contract

The SPICE data path emits a `*.cir.json` confession sidecar (the `cir` kind
above, schema-checked) **and**, alongside it, a raw `*.cir` **deck** —
ngspice-dialect text, not JSON. The deck carries **no schema by design**: the
validator globs only `*.json`, so the deck is never validated, and no
`cir-deck` schema exists. Its trust comes from the `XCIR_*` structural
differential (`paths.crosscheck_cir`, run by `python3 -m wyred.crosscheck`)
proving it denotes the same circuit as the L2 — not from JSON-schema
validation. See `EMIT_CONTRACT.md` Part E.

## Using the index

A file's kind is the second-from-last dotted segment of its name:
`watchy_v1_revb.lifecycle.json` → kind `lifecycle` → schema
`lifecycle.schema.json`. `validate.py` applies exactly that mapping (its
`_kind_of`), so you never pass a schema explicitly — point it at the file:

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py --file goldens/ga019/watchy_v1_revb.lifecycle.json
1/1 valid
# expect: 1/1 valid
```

Every kind has at least one golden that validates against its schema — which is
also the coverage check that keeps this index honest:

<!-- cwd: wyred-contract -->
```console
$ for k in l1 l2 alloc bom pinmap records baseline connlock pinmapdiff lifecycle cir; do python3 tools/validate.py --file "$(ls goldens/ga019/*.$k.json | head -1)" >/dev/null && echo "$k ok"; done
l1 ok
l2 ok
alloc ok
bom ok
pinmap ok
records ok
baseline ok
connlock ok
pinmapdiff ok
lifecycle ok
cir ok
# expect: cir ok
```
