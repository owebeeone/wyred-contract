# EMIT_CONTRACT v3 — the structured documents the gen-4 builder emits

A gen-4 design is **one document with two ordered layers** (Gen4 §1). The
builder therefore emits up to **three JSON artifacts** per intent, all read by
the oracle stack through structured fields only:

| artifact | schema module | consumed by |
|---|---|---|
| **Layer-1 intent doc** (`"layer": 1`) | `schema_l1.IntentDoc` (`schema_l1.to_json/from_json`) | layer-1 oracle (§4.1: demand-satisfiability, rail-scope, pool sufficiency, address uniqueness, voltage compatibility, invariant well-formedness, escalation quality) |
| **Allocation record** (embedded in the L1 doc under `"allocation"`) | `schema_l1.AllocationRecord` | allocation checks (§4.2: legal bijection, provenance, deterministic re-solve, lock-violation detection) |
| **Layer-2 netlist** | `schema.CanonicalGraph` (`schema.to_json/from_json`) | the v2 hardened stack (ERC / invariants / equivalence / round-trip), unchanged |

> **The three artifacts above are the per-intent core.** The gen-4 data-path
> and lifecycle tooling additionally emits standalone JSON artifacts — the
> allocation wrapper plus BOM, pin-map, records, baseline, connector-lock,
> pin-map diff, and lifecycle — that this prose historically did not specify.
> **Part E** indexes them and points at their schemas; this gap and its closure
> are finding **F1** in the changelog.

Layer 1 is valid and scoreable **standalone**. A layer-2 refinement may only
**narrow** layer-1 semantics — binding a role to a part, adding constraints,
pinning allocations — never change them.

The v2 layer-2 contract below is **unchanged and still normative**; v3 adds
Part B (layer-1 shape), Part C (allocation record), the optional ground fields
on `Net`, and a worked example.

---

# Part A — Layer-2 netlist contract (v2, unchanged)

> **Schema:** [`schemas/l2.schema.json`](schemas/l2.schema.json) (shared
> sub-shapes in [`schemas/common.defs.json`](schemas/common.defs.json)) is the
> machine-checkable form of this part, descriptive of the ga019 goldens
> (contract v0). The prose below is the human spec it was extracted from; where
> the two diverge the goldens win — see the changelog findings **F2** (`kind`
> vocabulary), **F3** (ground `voltage`), **F7** (string escalations), **F9**
> (`[refdes, terminal]` node encoding).

The oracle stack (ERC, equivalence, invariants) reads **only structured fields**
on the neutral `CanonicalGraph`. It NEVER parses a `function` string. `function`
is a free-form human label; a candidate may leave it blank, wrong, or
off-label — verdicts are unaffected. All electrical meaning must be carried in
the structured fields below.

If your intent lives only in a `function` token (`"vin:3.3"`, `"i2c_sda"`,
`"require:uart"`), the oracle will NOT see it and your fault-free-looking
netlist will be scored as such.

## Terminal

```
Terminal(name, role, function="",
         req_v=None, prov_v=None, iface=None, iface_member=None)
```

| field          | type            | meaning |
|----------------|-----------------|---------|
| `name`         | str             | pin name, unique within its component (permutable; ignored by equivalence). |
| `role`         | str             | one of `power_in`, `power_out`, `ground`, `signal`, `passive`, `logic_in`, `logic_out`. |
| `function`     | str             | **HUMAN LABEL ONLY.** Nothing keys off it. |
| `req_v`        | float or None   | a `power_in` REQUIRES this rail voltage (volts). Drives **R3** and part of **R1**. |
| `prov_v`       | float or None   | a `power_out` PROVIDES this rail voltage (volts). Drives **R5** and satisfies a matching `req_v` in R1. |
| `iface`        | str or None     | interface this terminal participates in, e.g. `"i2c"`, `"oscillator"`, `"uart"`, `"bootstrap"`. |
| `iface_member` | str or None     | the terminal's role WITHIN the interface (see below). |

### `iface_member` conventions

- **Bus member** (e.g. I2C): `iface="i2c"`, `iface_member="sda"` or `"scl"`.
  The SDA member on a shared net + equal `attrs["i2c_addr"]` drives **R4
  ADDR_COLLISION**.
- **Requirement**: `iface="<name>"`, `iface_member="require"` — this terminal
  NEEDS the interface. Drives **R1**.
- **Provision**: `iface="<name>"`, `iface_member="provide"` — this terminal
  SUPPLIES the interface. Satisfies a matching `require` on the same net (R1).

A requirement is satisfied (no R1 failure) when its net carries a matching
`provide` terminal, OR a generated companion (`authored=False`) part. If a
provider exists elsewhere in the graph but not on the pin's net, the situation
is an **ambiguity** (surface it on `graph.escalations`, do not resolve it) — R1
does not hard-fail. If no provider exists anywhere and no companion is on the
net, R1 emits **UNMET_REQUIRE**.

## Component

```
Component(refdes, kind, value, authored,
          terminals=[...], attrs={...}, logic_fn=None)
```

- `attrs["i2c_addr"]` : int — the device's I2C address (drives **R4**).
- `authored`          : `True` = first-class part; `False` = generated companion
  (decoupling cap, pull-up, bootstrap cap/diode, crystal load cap). **R7
  COMPANION_INCOMPLETE** fires if a companion is left partially unconnected.
- `logic_fn`          : one of `and/or/not/nand/nor/xor/buf` for
  `kind=="logic_gate"` (evaluated by the invariant checker).

### Provenance attrs — demand traceability (v3 hardening, MANDATORY)

Every L2 component **MUST carry provenance in `attrs`** tracing it back to
the layer-1 intent (composition law 7's oracle support — nothing lands in
the binding that the intent did not ask for):

- **authored parts** (`authored=true`): `attrs["l1_role"] = <L1 Role.id>` —
  the role this part binds.
- **generated/companion parts** (`authored=false`):
  `attrs["for_demand"] = <L1 Demand.id or Role.id>` — the demand (or role)
  whose declared companion produced it.

`spec_satisfaction` enforces this on every bound graph:

| code | fires when |
|---|---|
| `UNDEMANDED_COMPONENT` | a component carries NEITHER provenance key resolving to a real L1 role/demand — a fully wired rogue part that no demand asked for is a failure, not a freebie |
| `ORPHAN_GENERATED` | an `authored=false` part whose `for_demand` is present but resolves to nothing |

## Net

```
Net(name, kind, voltage, nodes=[(refdes, term_name), ...],
    ground_kind=None, ground_role=None, bond=None)      # v3 optional fields
```

- `name`    : cosmetic (ignored by equivalence).
- `kind`    : `power` / `ground` / `signal` / `open`. An `open` net is the
  explicit "declared but nothing drives it" hook; a mandatory `power_in`/`ground`
  pin on an `open` net (or on no net) triggers **R6 UNCONNECTED_MANDATORY**
  (NO SILENT DEFAULTS).
- `voltage` : rail voltage in volts for power nets (drives **R3** / **R5**), else
  `None`.

### v3 ground fields (optional; SOFT this generation)

Backward-compatible: all three default to `None`, are **emitted in JSON only
when set**, and nothing in the v2 oracle stack (ERC / equivalence /
invariants) keys off them. Ground-**role** checking is grader-noted, not
oracle-gated, this generation (Gen4 §2.1).

| field         | type          | meaning |
|---------------|---------------|---------|
| `ground_kind` | str or None   | for `kind=="ground"` nets: `"ground"` / `"chassis"` / `"earth"` (`schema.GROUND_KINDS`). Chassis and earth are DISTINCT kinds — never silently merged with the 0V return. |
| `ground_role` | str or None   | `"none"` / `"analog"` / `"digital"` / `"power"` / `"reference"` (`schema.GROUND_ROLES`) — one unified 0V return partitioned by role tags (GNDA/GNDD/PGND/GNDREF), **not** split nets. |
| `bond`        | str or None   | name of the AUTHORED bond (star point / net-tie) this ground net participates in. Two nets carrying the same `bond` name are joined at that single authored point; ground roles/kinds are only ever joined through a named bond. |

## Invariant (mutual exclusion — spec intent #8)

```
Invariant(kind="mutual_exclusion", a=(refdes, term), b=(refdes, term),
          inputs=[(refdes, term), ...])
```

`a` and `b` are the two gate-drive OUTPUT nodes that must NEVER both be
logic-high. `inputs` are the free command inputs the checker enumerates over
(2**len(inputs) assignments).

For a 3-phase bridge the MCU issues **two independent commands per bridge**
(`IN_H`, `IN_L`), so `inputs` has 2 entries. A correct hardware interlock
cross-inhibits, e.g.:

```
HS_gate = AND(IN_H, NOT(IN_L))
LS_gate = AND(IN_L, NOT(IN_H))
```

so even the `(IN_H=1, IN_L=1)` command yields never-both-high drives.

The invariant layer emits:

- **SHOOT_THROUGH** — some assignment drives both `a` and `b` high (e.g. a
  pass-through interlock with no cross-inhibit fails at `(1,1)`).
- **VACUOUS_INVARIANT** — a guarded output can NEVER be driven high under any
  assignment (anchored on undriven / unreachable nodes). Declaring an interlock
  on nodes the logic does not drive is caught here, not rewarded — the
  never-both-high guarantee would otherwise hold vacuously.

## ERC rule → structured-field summary

| rule | code                    | reads (structured only) |
|------|-------------------------|--------------------------|
| R1   | `UNMET_REQUIRE`         | `iface`+`iface_member`(`require`/`provide`), `req_v`/`prov_v`, `authored`, `graph.escalations` |
| R3   | `VOLTAGE_MISMATCH`      | `power_in.req_v` vs `net.voltage` |
| R4   | `ADDR_COLLISION`        | `iface="i2c"`+`iface_member="sda"` on a shared net, `attrs["i2c_addr"]` |
| R5   | `SINGLE_DRIVER`         | `power_out.prov_v` (>=2 differing on one net) |
| R6   | `UNCONNECTED_MANDATORY` | `role` in {`power_in`,`ground`} on an `open`/absent net |
| R7   | `COMPANION_INCOMPLETE`  | `authored=False` with a dangling/open terminal |

---

# Part B — Layer-1 (intent) JSON shape (v3, NEW)

> **Schema:** [`schemas/l1.schema.json`](schemas/l1.schema.json) (shared
> sub-shapes in [`schemas/common.defs.json`](schemas/common.defs.json)) is the
> machine-checkable form of this part — including the embedded Part-C
> allocation record — descriptive of the ga019 goldens (contract v0). See the
> changelog findings **F4** (`forked_from` object here vs string in lifecycle)
> and **F5** (`snapshot: null | []`).

Module: `schema_l1` (`IntentDoc`, `to_json`, `from_json`). Top-level dict:

```
{
  "layer": 1,
  "series": "A",                      // document series (board-spin identity)
  "scopes": [...],                    // optional; nested scopes only
  "roles": [...],
  "rails": [...],
  "grounds": [...],
  "bonds": [...],                     // optional
  "buses": [...],                     // optional
  "pools": [...],                     // optional
  "invariants": [...],                // optional
  "escalations": [...],               // optional
  "allocation": {...},                // Part C
  "attrs": {...}                      // optional
}
```

Optional list/dict keys are **emitted only when non-empty** (and per-object
optional fields only when non-default); `from_json` tolerates every omission.
Identity rules: all ids are author-chosen strings, unique per kind within the
document. **No refdes, no part numbers, no pin names exist at layer 1** —
refdes are minted by the substrate at layer 2 (composition law 8).

### Role — an abstract part/module

```
{"id": "mcu", "kind": "mcu", "scope": "",           // scope "" = document root
 "capabilities": [ {"iface": "i2c_master",
                    "volts": null|float,            // power capability voltage
                    "rail": null|"<rail name>",     // the rail this DRIVES (rail sources)
                    "attrs": {}} ],
 "demands":      [ {"id": "mcu.pwr",                // unique; allocation refs it
                    "iface": "power",               // "power"/"uart"/"i2c"/"nand"/"oscillator"/...
                    "volts": 3.3,                   // power demands: required rail voltage
                    "bus": null|"<bus name>",       // bus attachment (addr uniqueness per bus)
                    "qty": 1,                       // units demanded (pool sufficiency)
                    "default": null|"<satisfier>",  // DECLARED default (rail/role/pool name)
                    "attrs": {"i2c_addr": 72}} ],
 "attrs": {}}
```

Demands are **symbolic**: "a UART", "a NAND" — never a unit name ("UART1",
"gate S2"). Multiplicity of provision is a Pool, never a repeated capability.
A power demand with no matching in-scope rail and no declared `default` is a
layer-1 **load error** (resolution ladder rung 2).

**Typed defaults (v3 hardening).** A `default` must name a satisfier
**compatible with the demand**: a power demand's default must be a declared
**rail** at a compatible voltage (a wrong-voltage rail default fires
`VOLTAGE_MISMATCH`; a non-rail default never satisfies power); a non-power
demand's default must be a **provider of that iface** — a pool providing it,
a role with a matching capability, or a bus of that iface. A default naming
a known entity of the wrong type fires `DEFAULT_INCOMPATIBLE`
(`default="GND"` on a uart demand is an error, not a policy).

**Vacuous intent (v3 hardening).** A document declaring **zero demands**
fires `VACUOUS_INTENT`: an intent that asks for nothing is not scoreable as
clean, and `spec_satisfaction` refuses `PASS` on it.

### Scope

```
{"id": "motor_island", "parent": ""}
```

Root scope is the implicit `""` — declare `Scope` entries only for nested
scopes. A device's power demand auto-satisfies from the **nearest in-scope
compatible rail** (the cascade); nested scopes override.

### Rail — scoped, functionally named

```
{"name": "+3V3", "volts": 3.3, "scope": "", "attrs": {}}
```

Rail names are **design vocabulary** (KiCad style, no dots): `+3V3`, `+5V`,
`VBUS`, `VBAT`, `VSYS`, `VIN`. `VDD`/`VCC`/`AVDD`/`VSS` are part-definition
**pin** vocabulary and must never appear as rail names.

### Ground / Bond

```
{"name": "PGND", "kind": "ground",       // "ground" | "chassis" | "earth"
 "role": "power",                        // "none"|"analog"|"digital"|"power"|"reference"
 "scope": "", "attrs": {}}

{"name": "star1", "joins": ["GND", "PGND"], "attrs": {}}   // Bond
```

One unified 0V return partitioned by **role tags**, not split nets. A `Bond`
is a first-class **authored** star point / net-tie joining grounds; grounds
are never merged implicitly. (Ground-role ERC is soft this generation.)

### Bus

```
{"name": "I2C0", "iface": "i2c", "scope": "", "attrs": {}}
```

Roles attach via demands/capabilities carrying `"bus": "I2C0"`. Layer-1
address uniqueness is checked per `(bus, attrs["i2c_addr"])`.

### Pool — declared swap group

```
{"name": "mcu.uarts", "role": "mcu", "provides": "uart",
 "unit_count": 3, "port_signature": ["tx:out", "rx:in"], "attrs": {}}
```

- Equivalence is **declared, never inferred**. Units are identified by integer
  index `0 .. unit_count-1` (canonical stable order — "author pins UART2"
  means unit `2`).
- `port_signature` is the **typed port set of ONE unit** (`"name:type"`
  strings). A legal unit swap is a bijection between equal signatures; bundles
  swap whole (a diff-pair never splits).
- Uncommitted units remain **visible spare capacity** — never silently
  deleted (intent #9: the spare NAND stays a symbolic resource).
- Layer-1 **pool sufficiency**: sum of matching demand `qty` ≤ `unit_count`.

### InvariantDecl — layer-1 declaration (intent-level references)

```
{"kind": "mutual_exclusion",
 "subjects": ["bridge1.hs_gate", "bridge1.ls_gate"],   // exactly 2 for this kind
 "inputs":   ["mcu.in_h1", "mcu.in_l1"],
 "attrs": {}}
```

References are `"<role_id>.<signal>"` (role-local abstract signal labels) or a
bare `"<role_id>"` — **not** pins. Well-formed = known `kind`, correct subject
arity, every referenced role id exists. Layer 2 lowers this to a concrete
`schema.Invariant` over `(refdes, pin)` nodes for model checking.

### Escalation — ladder rung 4, WITH explanation

```
{"code": "AMBIGUOUS_NONEQUIV",
 "msg": "peripheral needs a serial link; hardware UART vs bit-banged GPIO, no policy",
 "subjects": ["periph.uart"],
 "conflict": ["periph.uart demands 'uart'",
              "candidate providers 'mcu.uarts' and 'gpio_bitbang' are not declared equivalent"],
 "relaxation": "declare a selection policy, or pin one provider"}
```

Only **non-equivalent** ambiguity (or no-policy) escalates. Ambiguity among
declared-equivalent pool units is an **ALLOCATION** (Part C), not an
escalation. An escalation without `conflict` + `relaxation` content is
low-quality (UNSAT-core-style explanations are required by §2.4 rung 4).

---

# Part C — Allocation record schema (v3, NEW)

> **Schema:** the **embedded** allocation record described here is the
> `allocation_record` `$def` in
> [`schemas/common.defs.json`](schemas/common.defs.json), referenced from
> [`schemas/l1.schema.json`](schemas/l1.schema.json). Do **not** conflate it
> with the **standalone** `*.alloc.json` artifact, which is a wider eight-key
> *wrapper* around this record (`allocation`, `bindings`, `bound_parts`,
> `connector_pinout`, `series`, `solver_version`, `stamp`, `wiring`) described
> by its own [`schemas/alloc.schema.json`](schemas/alloc.schema.json) — see
> Part E and finding **F1**.

Embedded in the layer-1 doc under `"allocation"` (module:
`schema_l1.AllocationRecord`):

```
{"entries": [
   {"pool": "mcu.uarts",        // Pool.name
    "unit": 0,                  // integer unit index within the pool
    "demand": "periph.uart",    // Demand.id served
    "chosen_by": "solver",      // "solver" | "author"  (author pins outrank the solver)
    "state": "sticky",          // "free" | "sticky" | "pinned"  (the ladder)
    "locked_by": null}          // "<group>@<version>" once a sync point promoted it
 ],
 "lock_groups": [
   {"name": "firmware-facing",
    "covers": ["pool_allocation", "pin_map"],   // simple decision-class list
    "version": 0,                               // 0 == never locked
    "snapshot": null,                           // frozen entry dicts at last lock
    "owner": "fw-team",                         // optional
    "sync_point": "firmware-freeze"}            // optional
 ],
 "solver_version": "trivial-1"}
```

Semantics the oracle enforces (§4.2):

- **Legality**: every entry names a real pool, a real unit
  (`0 <= unit < unit_count`), and a real demand whose `iface` matches the
  pool's `provides`; the map demand→unit is a **legal bijection per pool** (no
  unit double-booked, no demand double-served).
- **Provenance**: `chosen_by` present on every entry; `"author"` entries are
  pins the solver must honor.
- **The ladder**: `free → sticky → pinned`. Re-solves are deterministic given
  `(document, solver_version)`, canonically tie-broken (stable order, never
  hash order), minimal-disturbance (prefer incumbents; every changed binding
  is charged).
- **Canonical emit**: `schema_l1.to_json` sorts `entries` by
  `(pool, unit, demand)` and `lock_groups` by `name` — **two deterministic
  re-solves must produce byte-identical allocation records**.
- **Decision classes** (`covers` members): `pool_allocation`, `part_binding`,
  `pin_map`, `footprint`, `connector_pinout`, `design_rule`
  (`schema_l1.DECISION_CLASSES`).
- **Locking** = batch promotion: when a group's sync point fires, every
  covered entry becomes `state="pinned"`, `locked_by="<group>@<version>"`, the
  group's `version` increments, and `snapshot` freezes the covered entries'
  JSON forms. **Lock-violation detection** is a mechanical diff of current
  covered entries against `snapshot`, per group: a covered decision that
  changed **without a `series` bump** must be flagged (Tier-A). Editing a
  locked decision legally requires an explicit `break_lock` that forks a new
  `series`. Every emitted artifact is stamped with
  `(series, {group: version})`.
- **The external baseline IS the protocol (v3 hardening).** The grader
  retains `allocation.snapshot_locks(doc)` output **externally** at every
  lock/emit point and passes it back as `baseline=` to
  `check_allocations` / `check_lock_violations`. The **embedded** per-group
  `snapshot` is *informational only*: it travels with the document, so a
  tamperer who edits a locked entry can rewrite it to match. When locked
  groups exist (`version >= 1`) and NO external baseline is supplied,
  `check_allocations` emits the warning-violation `LOCK_UNVERIFIED` instead
  of silently passing — an unverifiable lock is never reported as verified.
- **Series fork record (v3 hardening).** A legal series fork records itself
  in the L1 doc's top-level `forked_from: {"series": <parent>, "reason": ...}`
  (`break_lock` writes it automatically). Against an external baseline, a
  `series` that differs **without** a `forked_from` naming the baseline
  series fires `SERIES_UNJUSTIFIED`: locked edits are never legalized by
  hand-editing the series string — only `break_lock` (which records the
  fork) permits them.

---

# Part D — Worked minimal example (L1 → allocation → L2)

Intent (corpus #5a shape): *an MCU role providing a pool of 3 equivalent
UARTs; one peripheral demanding a UART; a `+3V3` rail in scope; one ground.*

### D.1 Layer-1 intent doc (emit #1)

```json
{
  "layer": 1,
  "series": "A",
  "roles": [
    {"id": "supply", "kind": "supply",
     "capabilities": [{"iface": "power", "volts": 3.3, "rail": "+3V3"}]},
    {"id": "mcu", "kind": "mcu",
     "demands": [{"id": "mcu.pwr", "iface": "power", "volts": 3.3}]},
    {"id": "periph", "kind": "uart_device",
     "demands": [{"id": "periph.pwr", "iface": "power", "volts": 3.3},
                 {"id": "periph.uart", "iface": "uart"}]}
  ],
  "rails": [{"name": "+3V3", "volts": 3.3}],
  "grounds": [{"name": "GND"}],
  "pools": [
    {"name": "mcu.uarts", "role": "mcu", "provides": "uart",
     "unit_count": 3, "port_signature": ["tx:out", "rx:in"]}
  ],
  "allocation": {
    "entries": [
      {"pool": "mcu.uarts", "unit": 0, "demand": "periph.uart",
       "chosen_by": "solver", "state": "sticky", "locked_by": null}
    ],
    "lock_groups": [
      {"name": "firmware-facing", "covers": ["pool_allocation", "pin_map"],
       "version": 0, "snapshot": null}
    ],
    "solver_version": "trivial-1"
  }
}
```

Layer-1 oracle reading: both power demands satisfy from the in-scope `+3V3`
rail (compatible voltage); `periph.uart` is ambiguous among 3
**declared-equivalent** units → ladder rung 3, an ALLOCATION, not an
escalation — the trivial-deterministic solver picks the canonically-first free
unit (`unit 0`), records provenance, state `sticky`. Pool sufficiency: 1
demand ≤ 3 units; units 1–2 remain visible spare capacity. No escalations. If
the author later pins UART2, the entry becomes
`{"unit": 2, "chosen_by": "author", "state": "pinned", ...}` and the solver
must honor it on every re-solve.

### D.2 Layer-2 refinement (conceptual — bindings, not L1 edits)

```
refine:
  bind supply -> source part (refdes minted: PS1, attrs.l1_role="supply")
  bind mcu    -> part "MCU-3UART"   (refdes minted: U1, attrs.l1_role="mcu";
                                     pool units map to U0_TX/U0_RX,
                                     U1_TX/U1_RX, U2_TX/U2_RX)
  bind periph -> part "uart-peripheral"  (refdes minted: U2,
                                          attrs.l1_role="periph")
  ground "GND" (kind=ground, role=none)
```

A refinement **touches zero layer-1 lines** (grader floor: two-layer
authoring). The elaborator applies the allocation record — unit 0 of
`mcu.uarts` binds `periph.uart` to U1's `U0_TX`/`U0_RX` port pair via the
pool's typed port signature (a legal unit-swap bijection).

### D.3 Elaborated layer-2 netlist (emit #2 — v2 `CanonicalGraph` JSON)

```json
{
  "components": [
    {"refdes": "PS1", "kind": "source", "value": "3.3V", "authored": true,
     "terminals": [
       {"name": "VOUT", "role": "power_out", "function": "", "req_v": null,
        "prov_v": 3.3, "iface": null, "iface_member": null},
       {"name": "GND", "role": "ground", "function": "", "req_v": null,
        "prov_v": null, "iface": null, "iface_member": null}],
     "attrs": {"voltage": 3.3, "l1_role": "supply"}, "logic_fn": null},
    {"refdes": "U1", "kind": "mcu", "value": "MCU-3UART", "authored": true,
     "terminals": [
       {"name": "VDD", "role": "power_in", "function": "", "req_v": 3.3,
        "prov_v": null, "iface": null, "iface_member": null},
       {"name": "GND", "role": "ground", "function": "", "req_v": null,
        "prov_v": null, "iface": null, "iface_member": null},
       {"name": "U0_TX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "provide"},
       {"name": "U0_RX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "provide"},
       {"name": "U1_TX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "provide"},
       {"name": "U1_RX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "provide"},
       {"name": "U2_TX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "provide"},
       {"name": "U2_RX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "provide"}],
     "attrs": {"uart_ports": 3, "l1_role": "mcu"}, "logic_fn": null},
    {"refdes": "U2", "kind": "uart_device", "value": "uart-peripheral",
     "authored": true,
     "terminals": [
       {"name": "VDD", "role": "power_in", "function": "", "req_v": 3.3,
        "prov_v": null, "iface": null, "iface_member": null},
       {"name": "GND", "role": "ground", "function": "", "req_v": null,
        "prov_v": null, "iface": null, "iface_member": null},
       {"name": "TX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "require"},
       {"name": "RX", "role": "signal", "function": "", "req_v": null,
        "prov_v": null, "iface": "uart", "iface_member": "require"}],
     "attrs": {"l1_role": "periph"}, "logic_fn": null}
  ],
  "nets": [
    {"name": "+3V3", "kind": "power", "voltage": 3.3,
     "nodes": [["PS1", "VOUT"], ["U1", "VDD"], ["U2", "VDD"]]},
    {"name": "GND", "kind": "ground", "voltage": 0.0,
     "nodes": [["PS1", "GND"], ["U1", "GND"], ["U2", "GND"]],
     "ground_kind": "ground", "ground_role": "none"},
    {"name": "UART0_TX", "kind": "signal", "voltage": null,
     "nodes": [["U1", "U0_TX"], ["U2", "RX"]]},
    {"name": "UART0_RX", "kind": "signal", "voltage": null,
     "nodes": [["U1", "U0_RX"], ["U2", "TX"]]}
  ],
  "escalations": [],
  "invariants": []
}
```

Notes on D.3:

- The UART edges land on **unit 0's** ports because the allocation record says
  so — the L1 source never named `U0_TX`. Units 1–2's ports are legitimately
  unwired *provide* terminals (spare capacity), which is exactly why R1 treats
  a require with an off-net provider as escalation-at-most, and a *satisfied*
  require (provider on-net, as here) as clean.
- `ground_kind`/`ground_role` appear on the GND net because this v3 emit sets
  them; a v2 document omits them and round-trips unchanged.
- Emitting the same document twice must reproduce D.1's `"allocation"` block
  **byte-for-byte** (canonical entry order + deterministic solver). The
  emitted pin-map artifact (not shown; a v3 data path) is stamped
  `(series="A", firmware-facing@0)`.

### D.4 Contrast: what would NOT be an allocation

If the peripheral could be served by a hardware UART **or** a bit-banged GPIO
pair (non-equivalent alternatives — no pool declares them interchangeable) and
no policy exists, the L1 doc must instead carry an escalation (Part B shape,
`code="AMBIGUOUS_NONEQUIV"` with `conflict` + `relaxation`) and **no**
allocation entry for that demand (corpus #5b).

---

# Part E — Emitted data-path & lifecycle artifacts (schema-specified)

Parts A–C specify three documents: the L2 netlist, the L1 intent doc, and the
allocation record embedded in it. The gen-4 data-path and lifecycle tooling
(`wyred/paths.py`, `wyred/emit.py`) emits **standalone** artifacts beyond those
three, which the prose above historically did not describe (finding **F1**).
This part is their index. Each is **normatively defined by its schema file**,
not by the one-sentence gloss here: `*.<kind>.json` validates against
`schemas/<kind>.schema.json`, and the schemas are descriptive of the ga019
goldens (contract v0). The gloss is orientation only.

The standalone allocation wrapper `*.alloc.json`
([`schemas/alloc.schema.json`](schemas/alloc.schema.json)) is already
introduced in Part C. The seven further prose-less kinds:

| kind | file suffix | schema | one-sentence purpose |
|---|---|---|---|
| **bom** | `*.bom.json` | [`bom.schema.json`](schemas/bom.schema.json) | Bill of materials: authored/generated/component line-item roll-up; every generated (`authored:false`) line carries a `derived` provenance map and no authored line does (**F10**). Producer `paths.build_bom`. |
| **pinmap** | `*.pinmap.json` | [`pinmap.schema.json`](schemas/pinmap.schema.json) | Firmware-facing pin map: components with strict `l1_role` **xor** `for_demand` provenance and allocation rows binding demands to dotted `"REFDES.PIN"` nodes (**F9**/**F11**); a spare terminal's `net` may be `null`. Producer `paths.build_pinmap` (the "v3 data path" mentioned in D.3). |
| **records** | `*.records.json` | [`records.schema.json`](schemas/records.schema.json) | Standalone allocation/lock/escalation record: bindings plus **rich** escalation objects (**F7**), `pool_spares`, `resolutions`, and an optional `forked_from` object (**F4**). Producer `paths.build_records`. |
| **baseline** | `*.baseline.json` | [`baseline.schema.json`](schemas/baseline.schema.json) | Retained external lock baseline: `snapshot_locks` output (`series`, `solver_version`, `groups`) plus the engine-added `connector_pinout` rows (**F6**); emitted only for locked artifacts. Producer `harness.allocation.snapshot_locks` + `emit.py`. |
| **connlock** | `*.connlock.json` | [`connlock.schema.json`](schemas/connlock.schema.json) | Connector-pinout lock-gate record: gate verdict plus tamper-probe code arrays closed to the two-code gate vocabulary `CONNECTOR_LOCK_VIOLATION`/`CONNECTOR_SERIES_UNJUSTIFIED` (**F12**); forks additionally carry `fork_vs_parent_codes`. Producer `paths.check_connector_locks`. |
| **pinmapdiff** | `*.pinmapdiff.json` | [`pinmapdiff.schema.json`](schemas/pinmapdiff.schema.json) | ECO pin-map diff between two stamps: added/changed/removed allocation deltas, per-terminal `a`/`b` sides (each nullable), and minimal-disturbance violations. Producer `paths.diff_pinmaps`. |
| **lifecycle** | `*.lifecycle.json` | [`lifecycle.schema.json`](schemas/lifecycle.schema.json) | Series-fork lifecycle record: parent/child stamps, a **string** `forked_from` naming the parent artifact (**F4**), and lock-tamper code arrays closed to `LOCK_VIOLATION`/`SERIES_UNJUSTIFIED` (**F12**). Producer `emit.py` fork path. |

### Schema stamping & versioning convention

Every file under `schemas/` (the ten `<kind>.schema.json` plus the shared
`common.defs.json`) is standard JSON Schema **draft 2020-12** and carries a
top-level stamp:

```json
"x-wyred-contract": {"contract": "v3-ga019", "schema_rev": 0}
```

- **`contract`** names the EMIT_CONTRACT prose version the schema set was
  extracted from, qualified by the golden corpus it is descriptive of — here
  EMIT_CONTRACT **v3** against the **ga019** goldens, hence `"v3-ga019"`. A
  future EMIT_CONTRACT version bump rewrites the `contract` field of **every**
  schema in the same proposal, so the stamp and this document never drift apart.
- **`schema_rev`** (integer, starts at `0`) increments on any ratified change
  to a schema's assertions that is not itself a `contract` bump (e.g. a widening
  recorded as a contract event).
- **`$id`** is `https://wyred.dev/contract/v0/<kind>.schema.json` — a stable
  namespace, not a URL that must resolve. The `/v0/` segment is the
  **breaking-change** axis: it moves to `/v1/` only when a schema change is not
  backward-compatible for existing consumers. `contract` and `schema_rev` move
  within a `/v0/` line; `/vN/` moves only on a break.
- Stamp presence and cross-schema consistency are asserted mechanically by
  `tests/run_schema_tests.py`: a schema missing the stamp, or one whose
  `contract`/`schema_rev` disagrees with its siblings, fails the run.

---

# Changelog

Per `wyred-contract/CLAUDE.md`, every change to the emit contract is recorded
here (newest first). The schema set (`schemas/`), its dependency-free validator
(`tools/`), and its tests (`tests/`) are ratified together with the
EMIT_CONTRACT version they stamp.

## v3-ga019 — schema extraction (proposed; awaiting ratification)

First machine-checkable form of the contract: ten
`schemas/<kind>.schema.json` draft-2020-12 files plus
`schemas/common.defs.json`, a dependency-free subset validator
(`tools/validate.py`), and a test harness (`tests/`). All **107** ga019
goldens validate (schema + canonical serialization). The schemas are
**descriptive of the ga019 goldens** (contract v0): wherever prose,
harness/engine code, and the goldens disagreed, the goldens won and the
disagreement was recorded as a finding rather than a silent widening (invariant
1). Cross-reference pointers were added to Parts A/B/C and Part E was added to
index the prose-less artifacts. **No golden was edited** — the corpus is
byte-for-byte the emitted ga019 set.

Ratified prose-vs-artifact clarifications (full detail in
`dev-docs/WyredPlanContractSchemas.md` § Findings):

- **F1** — the prose covered only 3 of 10 artifact kinds; the standalone
  `alloc` wrapper and `bom`/`pinmap`/`records`/`baseline`/`connlock`/
  `pinmapdiff`/`lifecycle` were schema-extracted from the goldens + producer
  code. Closed by **Part E**.
- **F2** — `Component.kind` is an open string (12 declared vs 35 used); the
  observed vocabulary is listed non-normatively in `l2.schema.json`.
- **F3** — ground nets carry `voltage: 0.0`, not `null`; every net's `voltage`
  is typed `number | null`.
- **F4** — `forked_from` is an object `{series, reason}` in `l1`/`records` but
  a parent-naming **string** in `lifecycle`; each schema defines it
  independently.
- **F5** — a locked group may carry `snapshot: []` (or `null`); both are legal
  at any `version`.
- **F6** — the `baseline` artifact is `snapshot_locks` output plus an
  engine-added `connector_pinout` key (four keys); the harness docstring is the
  stale tier.
- **F7** — L2 `escalations` are strings; L1/records escalations are rich
  objects; encoded per-kind.
- **F8** — EMIT_CONTRACT.md had no changelog section. This section is that
  closure.
- **F9** — nodes are `[refdes, terminal]` pairs in L2 but dotted
  `"REFDES.PIN"` strings in alloc `wiring` / pinmap; documented per-kind.
- **F10** — `bom` `derived` is a golden-observed **biconditional** (present iff
  `authored:false`), tighter than the producer; encoded via a two-branch
  `oneOf`.
- **F11** — landed net/node fields are pinned to their golden-narrow non-null
  shape; pin-map component provenance is a strict `l1_role` **xor**
  `for_demand`.
- **F12** — `connlock` and `lifecycle` gate-code arrays are closed to their
  producer's two-code vocabulary; emit-side sentinel strings (absent from every
  golden) are excluded.
