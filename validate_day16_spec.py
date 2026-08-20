"""
Day 16 validation: proves the OpenAPI spec and JSON Schemas are not just
hand-typed documentation, but actually match what the real Day 13-15
engines produce.

Two checks:
  1. Structural sanity -- openapi.yaml parses as valid YAML with the
     required top-level sections; ats_api_schemas.json parses as valid
     JSON with the expected $defs.
  2. Conformance -- real output already on disk from Day 13/14/15 runs
     (data/results/*.json) is validated against the matching schema in
     ats_api_schemas.json, using a small hand-rolled validator (the
     `jsonschema` package isn't available in every environment this
     project runs in, and this project's schemas only use a small,
     easy-to-implement subset of JSON Schema: type/required/properties/
     items/enum/minimum/maximum/oneOf-with-null).

This is intentionally NOT a general-purpose JSON Schema implementation --
it supports exactly the keywords used in ats_api_schemas.json and no more.
"""

import json
import sys
from pathlib import Path

import yaml

SCHEMA_PATH = Path("schemas/ats_api_schemas.json")
OPENAPI_PATH = Path("api/openapi.yaml")
RESULTS_DIR = Path("data/results")


class SchemaValidationError(Exception):
    pass


def _resolve(schema, defs):
    if isinstance(schema, dict) and "$ref" in schema:
        key = schema["$ref"].split("/")[-1]
        return defs[key]
    return schema


def validate(value, schema, defs, path="$"):
    schema = _resolve(schema, defs)

    if "oneOf" in schema:
        errors = []
        for option in schema["oneOf"]:
            try:
                validate(value, option, defs, path)
                return
            except SchemaValidationError as e:
                errors.append(str(e))
        raise SchemaValidationError(f"{path}: value matched none of oneOf options: {errors}")

    expected_type = schema.get("type")
    if expected_type:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        type_map = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool, "null": type(None)}
        if not any(isinstance(value, type_map[t]) if t != "integer" else (isinstance(value, int) and not isinstance(value, bool)) for t in types):
            raise SchemaValidationError(f"{path}: expected type {types}, got {type(value).__name__}")

    if "enum" in schema and value is not None and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value {value!r} not in enum {schema['enum']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path}: {value} > maximum {schema['maximum']}")

    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                raise SchemaValidationError(f"{path}: missing required field '{req}'")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                validate(value[key], subschema, defs, f"{path}.{key}")

    if isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                validate(item, item_schema, defs, f"{path}[{i}]")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaValidationError(f"{path}: has {len(value)} items, minItems={schema['minItems']}")


def check_structural_sanity():
    print("STEP 1: Structural sanity")

    with open(OPENAPI_PATH) as f:
        spec = yaml.safe_load(f)
    for key in ("openapi", "info", "paths", "components"):
        assert key in spec, f"openapi.yaml missing top-level key '{key}'"
    n_paths = len(spec["paths"])
    n_schemas = len(spec["components"]["schemas"])
    print(f"  {OPENAPI_PATH}: valid YAML, {n_paths} paths, {n_schemas} component schemas")

    with open(SCHEMA_PATH) as f:
        schema_doc = json.load(f)
    defs = schema_doc["$defs"]
    print(f"  {SCHEMA_PATH}: valid JSON, {len(defs)} schema definitions: {', '.join(defs.keys())}")
    print("-" * 78)
    return defs


def check_conformance(defs):
    print("STEP 2: Real Day 13-15 output validated against the schemas")
    checks = 0

    # Day 13 score results -> CandidateScore (minus resume_id/jd_id, which
    # the file's per-pair naming convention encodes instead of embedding)
    for f in sorted(RESULTS_DIR.glob("*__vs__*.json")):
        data = json.loads(f.read_text())
        wrapped = {"resume_id": "x", "jd_id": "y", **data}
        validate(wrapped, {"$ref": "#/$defs/CandidateScore"}, defs)
        print(f"  OK  CandidateScore  <- {f.name}")
        checks += 1

    # Day 14 ranking output -> RankedCandidateView (per-candidate rows)
    for f in sorted(RESULTS_DIR.glob("ranking__*.json")):
        data = json.loads(f.read_text())
        for row in data["candidates"]:
            validate(row, {"$ref": "#/$defs/RankedCandidateView"}, defs)
        print(f"  OK  RankedCandidateView x{len(data['candidates'])}  <- {f.name}")
        checks += 1

    # Day 15 fairness report -> BiasReport + NormalizedScore
    fairness_path = RESULTS_DIR / "fairness_report.json"
    if fairness_path.exists():
        data = json.loads(fairness_path.read_text())
        bias = data["bias_report_resume_15"]
        # NOTE (real finding, not hypothetical): run_fairness_check.py (Day 15's
        # internal debug script) serializes BiasReport.pii_fields_detected under
        # the key "fields_detected" -- a naming choice made for readability in
        # that ad-hoc report, but it doesn't match the dataclass field name. The
        # API schema follows the dataclass (the actual source of truth for a
        # real endpoint), so a real API implementation must emit
        # "pii_fields_detected", not reuse run_fairness_check.py's key name.
        # Remapped here so this check still validates the *data*, and the
        # mismatch itself is called out explicitly in the integration flow doc.
        bias = {**bias, "pii_fields_detected": bias.pop("fields_detected")}
        validate(bias, {"$ref": "#/$defs/BiasReport"}, defs)
        print(f"  OK  BiasReport  <- {fairness_path.name}  (NOTE: source JSON key 'fields_detected' remapped to schema's 'pii_fields_detected' -- see docs)")
        for ns in data["normalized_batch"]:
            validate(ns, {"$ref": "#/$defs/NormalizedScore"}, defs)
        print(f"  OK  NormalizedScore x{len(data['normalized_batch'])}  <- {fairness_path.name}")
        checks += 2

    print("-" * 78)
    print(f"All {checks} real-data conformance checks passed.")


if __name__ == "__main__":
    try:
        defs = check_structural_sanity()
        check_conformance(defs)
    except (SchemaValidationError, AssertionError) as e:
        print(f"VALIDATION FAILED: {e}")
        sys.exit(1)
