#!/usr/bin/env python3
"""Regenerate the schema-validation mutant fixtures under tests/fixtures/.

Each fixture is a byte-clean COPY of one ga019 golden with exactly ONE targeted
mutation that violates exactly one draft-2020-12 assertion in that kind's schema,
so `tools/validate.py --file <fixture>` fails at a single nameable JSON pointer.
The goldens themselves are read-only (invariant 1): a mutation is applied to an
in-memory `json.load` and written to tests/fixtures/, never back to goldens/.

The fixtures are committed (checked-in) artifacts — this script only exists to
make them reproducible/auditable and to document what each one proves. It mirrors
wyred-audit/tests/make_fixtures.py. run_schema_tests.py holds the independent
EXPECT map (fixture -> pointer, keyword) and is the actual test.

Coverage: the five-mutant spot check from plan Steps 1.1a-c (drop-required,
wrong-enum, extra-top-level-key, string-for-number, 3-element net node) plus a
mutant per extraction finding F10 (bom `derived` biconditional, both directions),
F11 (pinmap l1_role XOR for_demand; alloc wiring net non-null) and F12 (connlock /
lifecycle closed gate-code vocabularies).

    python3 tests/make_fixtures.py        # (re)write tests/fixtures/*.json

Run from the wyred-contract repo root.
"""
from __future__ import annotations

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GOLDENS = os.path.join(REPO, "goldens", "ga019")
FIXTURES = os.path.join(HERE, "fixtures")


def _load(golden):
    with open(os.path.join(GOLDENS, golden), encoding="utf-8") as f:
        return json.load(f)


# --- mutators: each takes a fresh golden dict and returns the mutated dict ---

def _l1_drop_layer(d):            # required key removed
    del d["layer"]
    return d


def _l1_layer_const(d):           # const layer:1 -> 2
    d["layer"] = 2
    return d


def _l2_bad_terminal_role(d):     # closed TERMINAL_ROLES enum violated
    d["components"][0]["terminals"][0]["role"] = "gpio"
    return d


def _l2_extra_top_key(d):         # additionalProperties:false at top
    d["surprise"] = 1
    return d


def _l2_three_element_node(d):    # net node 2-tuple -> 3-tuple (maxItems)
    net = next(n for n in d["nets"] if n["nodes"])
    net["nodes"][0] = list(net["nodes"][0]) + ["EXTRA"]
    return d


def _bom_component_total_string(d):   # integer field carries a string (type)
    d["component_total"] = str(d["component_total"])
    return d


def _bom_authored_with_derived(d):    # F10: authored:true carrying `derived`
    li = next(x for x in d["line_items"] if x["authored"] is True)
    li["derived"] = {li["refdes"][0]: "hand-injected derivation"}
    return d


def _bom_generated_without_derived(d):  # F10: authored:false missing `derived`
    li = next(x for x in d["line_items"]
              if x["authored"] is False and "derived" in x)
    del li["derived"]
    return d


def _pinmap_both_provenance(d):    # F11: l1_role AND for_demand (XOR broken)
    c = next(x for x in d["components"]
             if ("for_demand" in x) != ("l1_role" in x))
    if "l1_role" in c:
        c["for_demand"] = "d_injected"
    else:
        c["l1_role"] = "role_injected"
    return d


def _alloc_wiring_net_null(d):     # F11: wiring row net is non-null string
    d["wiring"][0]["net"] = None
    return d


def _connlock_third_code(d):       # F12: closed connector-lock vocabulary
    d["tamper_net_codes"] = list(d["tamper_net_codes"]) + ["SPURIOUS_CODE"]
    return d


def _lifecycle_sentinel_code(d):   # F12: emit.py sentinel excluded from vocab
    d["tamper_locked_edit_codes"] = (
        list(d["tamper_locked_edit_codes"]) + ["(no locked entry to tamper)"])
    return d


# fixture filename -> (source golden, mutator). The `.<kind>.json` suffix is
# load-bearing: validate.py derives the kind (and thus the schema) from it.
SPEC = {
    "mut_l1_drop_required.l1.json":
        ("intent_01_sensor_node.l1.json", _l1_drop_layer),
    "mut_l1_layer_const.l1.json":
        ("intent_01_sensor_node.l1.json", _l1_layer_const),
    "mut_l2_bad_enum.l2.json":
        ("intent_01_sensor_node.l2.json", _l2_bad_terminal_role),
    "mut_l2_extra_key.l2.json":
        ("intent_01_sensor_node.l2.json", _l2_extra_top_key),
    "mut_l2_three_element_node.l2.json":
        ("intent_01_sensor_node.l2.json", _l2_three_element_node),
    "mut_bom_type.bom.json":
        ("intent_01_sensor_node.bom.json", _bom_component_total_string),
    "mut_bom_f10_authored_derived.bom.json":
        ("intent_01_sensor_node.bom.json", _bom_authored_with_derived),
    "mut_bom_f10_generated_no_derived.bom.json":
        ("intent_01_sensor_node.bom.json", _bom_generated_without_derived),
    "mut_pinmap_f11_both_provenance.pinmap.json":
        ("intent_01_sensor_node.pinmap.json", _pinmap_both_provenance),
    "mut_alloc_f11_wiring_net_null.alloc.json":
        ("intent_05a_pinned.alloc.json", _alloc_wiring_net_null),
    "mut_connlock_f12_third_code.connlock.json":
        ("watchy_v1_reva.connlock.json", _connlock_third_code),
    "mut_lifecycle_f12_sentinel.lifecycle.json":
        ("watchy_v1_revb.lifecycle.json", _lifecycle_sentinel_code),
}


def main():
    os.makedirs(FIXTURES, exist_ok=True)
    for name, (golden, mutate) in sorted(SPEC.items()):
        obj = mutate(copy.deepcopy(_load(golden)))
        out = os.path.join(FIXTURES, name)
        with open(out, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")
        print(f"wrote {name}  (from {golden})")
    print(f"{len(SPEC)} fixtures written under {FIXTURES}")


if __name__ == "__main__":
    main()
