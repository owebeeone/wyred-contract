#!/usr/bin/env python3
"""Dependency-free JSON-Schema validator for the wyred emit contract (v0).

Purpose-built for the *exact* draft-2020-12 SUBSET the ten contract schemas
(schemas/<kind>.schema.json + schemas/common.defs.json) actually use — no more.
It is deliberately NOT a general validator: it is coupled to the schema-author
vocabulary by a hard **fail-closed** rule. On loading a schema it walks every
schema-position object and, if it finds any keyword outside the whitelist below,
it aborts with exit 2 naming the keyword rather than silently ignoring it (the
classic silent-pass failure mode of subset validators). The same load-time walk
also eagerly resolves EVERY $ref value — checking its style (a bare relative
filename before '#'; a '#/$defs/...' fragment) AND that it resolves — so a
rotten/remote $ref buried in a schema branch that no golden instance happens to
exercise still aborts with exit 2 at load time, instead of lurking latent until
(if ever) validation reaches it. This means the schemas can never quietly
out-grow the validator: a new keyword OR a bad $ref forces a validator change.
The schema documents remain fully standard draft-2020-12, so external consumers
can still validate them with ajv or python-jsonschema unchanged.

Keyword whitelist (fixed by what schemas/*.json actually use — Step 1.2 of
dev-docs/WyredPlanContractSchemas.md; enumerated mechanically, not guessed):

  assertions : type enum const required properties additionalProperties
               items prefixItems minItems maxItems minimum pattern oneOf
  reference  : $ref  ($defs container)   -- $ref supports ONLY the two styles
               the schemas use: local  "#/$defs/<name>"  and relative-file
               "<file>.json#/$defs/<name>".
  annotations: $schema $id title description $comment x-wyred-contract  (no-ops)

Anything else -> exit 2 (setup error). Notably absent (and therefore rejected
if a schema ever introduces them): patternProperties, anyOf, allOf, not,
if/then/else, maximum, multipleOf, uniqueItems, dependentSchemas, ...

CLI:
  python3 tools/validate.py [--schemas DIR] --tree DIR      (default tree: goldens/ga019)
  python3 tools/validate.py [--schemas DIR] --file PATH
  ...add --canonical to also byte-compare each file against
     json.dumps(json.load(f), indent=2, sort_keys=True) + "\\n"  (the goldens'
     serialization convention, kept out of the schemas themselves).

  *.<kind>.json  is mapped to  <kind>.schema.json.  One line per failure
  (file, JSON-pointer, keyword, message); summary "N/TOTAL valid"; exit 0 iff
  all valid, 1 on any validation/canonical failure, 2 on setup error — mirroring
  wyred-audit's exit convention.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

# --------------------------------------------------------------------------- #
# Keyword universe                                                            #
# --------------------------------------------------------------------------- #
# Keywords whose value is a single subschema.
_SUBSCHEMA = frozenset({"items", "additionalProperties"})
# Keywords whose value is a list of subschemas.
_SUBSCHEMA_LIST = frozenset({"oneOf", "prefixItems"})
# Keywords whose value is a map <name> -> subschema (names are NOT keywords).
_SUBSCHEMA_MAP = frozenset({"properties", "$defs"})
# Pure annotations / identifiers — no validation effect.
_ANNOTATION = frozenset({"$schema", "$id", "title", "description", "$comment",
                         "x-wyred-contract"})
# Leaf assertion keywords whose value is data, never a subschema.
_LEAF_ASSERT = frozenset({"type", "enum", "const", "required", "minItems",
                          "maxItems", "minimum", "pattern"})

# The complete whitelist: every keyword the validator understands. The
# fail-closed scan rejects anything outside this set.
WHITELIST = (_SUBSCHEMA | _SUBSCHEMA_LIST | _SUBSCHEMA_MAP | _ANNOTATION
             | _LEAF_ASSERT | {"$ref"})


class SetupError(Exception):
    """A problem with the schemas / invocation itself -> exit 2."""


# --------------------------------------------------------------------------- #
# Fail-closed keyword scan                                                     #
# --------------------------------------------------------------------------- #
def _scan_schema(node, filename, pointer, refs=None):
    """Walk a schema-position object; raise SetupError on any non-whitelisted
    keyword. Recurses only into genuine subschema positions so that property
    names, $defs names, enum members, required entries and const/x-wyred-contract
    data are never mistaken for keywords.

    If `refs` is a list, every $ref value encountered is appended to it as a
    (pointer, ref_value) pair so the caller can eagerly validate ref STYLE and
    RESOLVABILITY at load time. Without that eager pass a rotten/remote $ref in
    a schema branch that no golden instance exercises would stay latent (never
    reached by _validate), quietly defeating the fail-closed guarantee."""
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        raise SetupError(
            f"{filename}: schema at {pointer or '/'} is not an object or boolean")
    for key, val in node.items():
        if key not in WHITELIST:
            raise SetupError(
                f"{filename}: unsupported schema keyword {key!r} at "
                f"{pointer or '/'} (not in validator whitelist)")
        if key == "$ref":
            if refs is not None:
                refs.append((pointer, val))
        elif key in _SUBSCHEMA:
            _scan_schema(val, filename, f"{pointer}/{key}", refs)
        elif key in _SUBSCHEMA_LIST:
            if isinstance(val, list):
                for i, sub in enumerate(val):
                    _scan_schema(sub, filename, f"{pointer}/{key}/{i}", refs)
        elif key in _SUBSCHEMA_MAP:
            if isinstance(val, dict):
                for name, sub in val.items():
                    _scan_schema(sub, filename, f"{pointer}/{key}/{_esc(name)}", refs)
        # _LEAF_ASSERT, _ANNOTATION -> value is data: no recurse.


# --------------------------------------------------------------------------- #
# Schema set (loading + $ref resolution)                                       #
# --------------------------------------------------------------------------- #
class SchemaSet:
    """Loads and keyword-scans every schema file in a directory, indexes the
    per-kind schemas, and resolves the two supported $ref styles."""

    def __init__(self, schema_dir):
        self.dir = os.path.abspath(schema_dir)
        if not os.path.isdir(self.dir):
            raise SetupError(f"schemas dir not found: {self.dir}")
        self._docs = {}          # abspath -> parsed doc
        self.by_kind = {}        # "l2" -> abspath of l2.schema.json
        files = sorted(glob.glob(os.path.join(self.dir, "*.json")))
        if not files:
            raise SetupError(f"no *.json schema files under {self.dir}")
        all_refs = []            # (abspath, pointer, ref_value) for the eager pass
        for path in files:
            doc = self._load(path)
            # Fail-closed keyword scan on EVERY schema file at startup, so a
            # rogue keyword anywhere aborts before any instance is validated.
            # The same walk collects every $ref value for the eager check below.
            refs = []
            _scan_schema(doc, os.path.basename(path), "", refs)
            ap = os.path.abspath(path)
            for pointer, ref in refs:
                all_refs.append((ap, pointer, ref))
            base = os.path.basename(path)
            if base.endswith(".schema.json"):
                self.by_kind[base[: -len(".schema.json")]] = ap
        # Fail-closed $ref scan: eagerly resolve EVERY $ref value now that all
        # schemas are loaded, so a bad-style or unresolvable (e.g. rotten/remote)
        # $ref in a branch no instance exercises aborts at load time (exit 2)
        # naming the offender, rather than staying latent until _validate happens
        # to reach it. Reuses resolve_ref -> the eager and lazy checks can never
        # diverge in what ref styles they accept.
        for ap, pointer, ref in all_refs:
            try:
                self.resolve_ref(ref, ap)
            except SetupError as e:
                raise SetupError(
                    f"{os.path.basename(ap)}: unresolvable/ill-styled $ref at "
                    f"{pointer or '/'}: {e}")

    def _load(self, path):
        ap = os.path.abspath(path)
        if ap not in self._docs:
            try:
                with open(ap, encoding="utf-8") as f:
                    self._docs[ap] = json.load(f)
            except FileNotFoundError:
                raise SetupError(f"schema file not found: {ap}")
            except json.JSONDecodeError as e:
                raise SetupError(f"schema {ap} is not valid JSON: {e}")
        return self._docs[ap]

    def schema_for_kind(self, kind):
        if kind not in self.by_kind:
            raise SetupError(
                f"no schema for kind {kind!r} "
                f"(expected {kind}.schema.json under {self.dir})")
        path = self.by_kind[kind]
        return self._load(path), path

    def resolve_ref(self, ref, cur_file):
        """Resolve a $ref to (target_subschema, target_doc_file). Supports only
        local "#/$defs/<name>..." and relative-file "<name>.json#/$defs/<name>...";
        anything else is a SetupError (fail-closed on ref style too)."""
        if "#" not in ref:
            raise SetupError(f"unsupported $ref {ref!r} (no '#' fragment)")
        filepart, frag = ref.split("#", 1)
        if filepart == "":
            doc, target_file = self._load(cur_file), cur_file
        else:
            if ("://" in filepart or filepart.startswith("/")
                    or os.sep in filepart or ".." in filepart.split("/")):
                raise SetupError(
                    f"unsupported $ref {ref!r} (only a bare relative filename is "
                    f"allowed before '#')")
            target_file = os.path.join(os.path.dirname(cur_file), filepart)
            doc = self._load(target_file)
        if not frag.startswith("/$defs/"):
            raise SetupError(
                f"unsupported $ref fragment in {ref!r} (only '#/$defs/...' is allowed)")
        node = doc
        for token in frag.split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or token not in node:
                raise SetupError(f"$ref {ref!r} does not resolve (missing {token!r})")
            node = node[token]
        return node, target_file


# --------------------------------------------------------------------------- #
# JSON value helpers (draft-2020-12 equality + type semantics)                 #
# --------------------------------------------------------------------------- #
def _json_equal(a, b):
    """Draft-2020-12 instance equality (for enum/const). Booleans are distinct
    from numbers (True != 1); 1 == 1.0; recurses through arrays/objects."""
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _matches_type(inst, t):
    if t == "integer":
        if isinstance(inst, bool):
            return False
        if isinstance(inst, int):
            return True
        return isinstance(inst, float) and inst.is_integer()
    if t == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "string":
        return isinstance(inst, str)
    if t == "null":
        return inst is None
    if t == "array":
        return isinstance(inst, list)
    if t == "object":
        return isinstance(inst, dict)
    raise SetupError(f"unknown type name {t!r} in schema")


def _typename(inst):
    if isinstance(inst, bool):
        return "boolean"
    if isinstance(inst, int):
        return "integer"
    if isinstance(inst, float):
        return "number"
    if isinstance(inst, str):
        return "string"
    if inst is None:
        return "null"
    if isinstance(inst, list):
        return "array"
    if isinstance(inst, dict):
        return "object"
    return type(inst).__name__


def _esc(token):
    return str(token).replace("~", "~0").replace("/", "~1")


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #
class Failure:
    __slots__ = ("pointer", "keyword", "message")

    def __init__(self, pointer, keyword, message):
        self.pointer = pointer
        self.keyword = keyword
        self.message = message


def _validate(instance, schema, ss, cur_file, pointer, out):
    """Append Failure records for `instance` under `schema`. `cur_file` is the
    file the current schema lives in (for $ref resolution); `pointer` is the
    instance JSON-pointer. All keywords in one schema object apply conjunctively."""
    if schema is True:
        return
    if schema is False:
        out.append(Failure(pointer, "schema", "value is disallowed (false schema)"))
        return
    if not isinstance(schema, dict):
        raise SetupError(f"schema at instance {pointer or '/'} is not an object")

    for key, val in schema.items():
        if key in _ANNOTATION or key == "$defs":
            continue

        if key == "type":
            types = val if isinstance(val, list) else [val]
            if not any(_matches_type(instance, t) for t in types):
                out.append(Failure(pointer, "type",
                                   f"{_typename(instance)} is not of type "
                                   f"{', '.join(types)}"))

        elif key == "enum":
            if not any(_json_equal(instance, e) for e in val):
                out.append(Failure(pointer, "enum",
                                   f"{instance!r} is not one of {val}"))

        elif key == "const":
            if not _json_equal(instance, val):
                out.append(Failure(pointer, "const", f"{instance!r} != {val!r}"))

        elif key == "required":
            if isinstance(instance, dict):
                for name in val:
                    if name not in instance:
                        out.append(Failure(pointer, "required",
                                           f"{name!r} is a required property"))

        elif key == "properties":
            if isinstance(instance, dict):
                for name, subschema in val.items():
                    if name in instance:
                        _validate(instance[name], subschema, ss, cur_file,
                                  f"{pointer}/{_esc(name)}", out)

        elif key == "additionalProperties":
            if isinstance(instance, dict):
                declared = set(schema.get("properties", {}).keys())
                for name in instance:
                    if name in declared:
                        continue
                    if val is False:
                        out.append(Failure(pointer, "additionalProperties",
                                           f"additional property {name!r} is not allowed"))
                    else:
                        _validate(instance[name], val, ss, cur_file,
                                  f"{pointer}/{_esc(name)}", out)

        elif key == "items":
            if isinstance(instance, list):
                start = len(schema.get("prefixItems", []))
                for i in range(start, len(instance)):
                    _validate(instance[i], val, ss, cur_file,
                              f"{pointer}/{i}", out)

        elif key == "prefixItems":
            if isinstance(instance, list):
                for i, subschema in enumerate(val):
                    if i < len(instance):
                        _validate(instance[i], subschema, ss, cur_file,
                                  f"{pointer}/{i}", out)

        elif key == "minItems":
            if isinstance(instance, list) and len(instance) < val:
                out.append(Failure(pointer, "minItems",
                                   f"array length {len(instance)} < minItems {val}"))

        elif key == "maxItems":
            if isinstance(instance, list) and len(instance) > val:
                out.append(Failure(pointer, "maxItems",
                                   f"array length {len(instance)} > maxItems {val}"))

        elif key == "minimum":
            if isinstance(instance, (int, float)) and not isinstance(instance, bool):
                if instance < val:
                    out.append(Failure(pointer, "minimum",
                                       f"{instance} < minimum {val}"))

        elif key == "pattern":
            if isinstance(instance, str) and re.search(val, instance) is None:
                out.append(Failure(pointer, "pattern",
                                   f"{instance!r} does not match /{val}/"))

        elif key == "oneOf":
            matched = 0
            for branch in val:
                branch_fail = []
                _validate(instance, branch, ss, cur_file, pointer, branch_fail)
                if not branch_fail:
                    matched += 1
            if matched != 1:
                out.append(Failure(pointer, "oneOf",
                                   f"{matched} of {len(val)} subschemas matched, "
                                   f"expected exactly 1"))

        elif key == "$ref":
            target, target_file = ss.resolve_ref(val, cur_file)
            _validate(instance, target, ss, target_file, pointer, out)

        else:  # unreachable: fail-closed scan already rejected unknown keywords
            raise SetupError(f"validator reached unhandled keyword {key!r}")


# --------------------------------------------------------------------------- #
# File-level checks                                                            #
# --------------------------------------------------------------------------- #
def _kind_of(path):
    parts = os.path.basename(path).split(".")
    if len(parts) < 3 or parts[-1] != "json":
        raise SetupError(f"cannot derive artifact kind from filename {path!r} "
                         f"(expected <name>.<kind>.json)")
    return parts[-2]


def _canonical_ok(path):
    """True iff the file's bytes equal json.dumps(obj, indent=2, sort_keys=True)
    followed by a single trailing newline (the ga019 serialization convention)."""
    with open(path, "rb") as f:
        raw = f.read()
    obj = json.loads(raw.decode("utf-8"))
    canon = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return raw == canon


def validate_file(path, ss, canonical):
    """Return (schema_ok, canonical_ok_or_None, [Failure...])."""
    kind = _kind_of(path)
    schema, schema_file = ss.schema_for_kind(kind)
    try:
        with open(path, encoding="utf-8") as f:
            instance = json.load(f)
    except FileNotFoundError:
        raise SetupError(f"artifact file not found: {path}")
    except json.JSONDecodeError as e:
        return False, (None if not canonical else False), [
            Failure("", "json", f"not valid JSON: {e}")]
    failures = []
    _validate(instance, schema, ss, schema_file, "", failures)
    canon = _canonical_ok(path) if canonical else None
    return (not failures), canon, failures


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def _default_schemas_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "schemas")


def _default_tree_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "goldens", "ga019")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Dependency-free draft-2020-12 subset validator for the "
                    "wyred emit contract goldens.")
    ap.add_argument("--schemas", default=None,
                    help="schema directory (default: <repo>/schemas)")
    ap.add_argument("--tree", default=None,
                    help="validate every *.json in this directory "
                         "(default: <repo>/goldens/ga019)")
    ap.add_argument("--file", default=None,
                    help="validate a single artifact file")
    ap.add_argument("--canonical", action="store_true",
                    help="also byte-compare each file against its canonical "
                         "json.dumps(indent=2, sort_keys=True)+newline form")
    args = ap.parse_args(argv)

    try:
        ss = SchemaSet(args.schemas or _default_schemas_dir())

        if args.file is not None:
            files = [args.file]
        else:
            tree = args.tree or _default_tree_dir()
            if not os.path.isdir(tree):
                raise SetupError(f"tree dir not found: {tree}")
            files = sorted(glob.glob(os.path.join(tree, "*.json")))
            if not files:
                raise SetupError(f"no *.json files under {tree}")

        total = len(files)
        n_valid = 0
        n_canon = 0
        for path in files:
            schema_ok, canon_ok, failures = validate_file(path, ss, args.canonical)
            base = os.path.basename(path)
            if schema_ok:
                n_valid += 1
            else:
                for fl in failures:
                    print(f"FAIL {base}  {fl.pointer or '/'}  [{fl.keyword}]  "
                          f"{fl.message}")
            if args.canonical:
                if canon_ok:
                    n_canon += 1
                else:
                    print(f"FAIL {base}  /  [canonical]  bytes differ from "
                          f"json.dumps(indent=2, sort_keys=True)+newline")
    except SetupError as e:
        print(f"SETUP ERROR: {e}", file=sys.stderr)
        return 2

    print(f"{n_valid}/{total} valid")
    if args.canonical:
        print(f"{n_canon}/{total} canonical")

    all_ok = (n_valid == total) and (not args.canonical or n_canon == total)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
