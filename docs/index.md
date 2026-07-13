# wyred-contract — reference

`wyred-contract` is the versioned **emit contract**: the JSON Schemas and the
golden artifacts that every other wyred member reads and writes against. It is
the product's real API — everything depends on it; it depends on nothing.

These pages explain **how to navigate** the contract. They are not themselves
normative. The sources of truth are:

- `wyred-contract/EMIT_CONTRACT.md` — the human specification (Parts A–E and
  the changelog);
- `wyred-contract/schemas/*.schema.json` — the machine-checkable form,
  descriptive of the ga019 goldens;
- `wyred-contract/goldens/ga019/` — the golden artifacts themselves. When
  prose, engine code, and the goldens disagree, **the goldens win** (and the
  disagreement is recorded as a finding, never silently widened).

A page here that contradicts any of those is a defect in the page — the fix is
to the page, never to the contract.

!!! note "A note on links"
    Files outside these `docs/` — the schemas, the goldens, `EMIT_CONTRACT.md` —
    are named by their **workspace-relative path** in `inline code` (e.g.
    `wyred-contract/schemas/l2.schema.json`), because only markdown is
    aggregated into the published site. Open them in a `wyred-contract`
    checkout. Links between these reference pages are ordinary links.

## The pages

- **[How to read the schemas](reading-the-schemas.md)** — the draft-2020-12
  subset the schemas use, the shared `$defs` library and the two `$ref` styles,
  the `x-wyred-contract` stamp and the `/v0/` versioning axis, and the
  descriptive-of-goldens discipline (the `Fn` findings).
- **[The artifact-kind index](artifact-kinds.md)** — the eleven JSON artifact
  kinds, each mapped to its file suffix, its schema, its `EMIT_CONTRACT.md`
  section, and a golden you can open and validate. (Plus the raw `.cir` deck,
  which carries no schema by design.)
- **[`validate.py` usage](validate.md)** — the dependency-free subset
  validator: every flag, the exit-code convention, and runnable examples.

## Quick check

Validate the whole golden corpus against the schemas:

<!-- cwd: wyred-contract -->
```console
$ python3 tools/validate.py
114/114 valid
# expect: 114/114 valid
```

The census size (114 here) is not a number to memorize — it is however many
`*.json` files the validator globs under `goldens/ga019/`. See the
[artifact-kind index](artifact-kinds.md) for how it is composed and the one
sanctioned event that grew it.
