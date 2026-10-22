"""Manifest shape checks run without dependencies; jsonschema adds full verification when available."""
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import test_setup
import install
import project_memory as pm


def shape(value, schema):
    """Small assertion for the features used by this manifest schema (not a general validator)."""
    types = {"object": dict, "array": list, "string": str, "integer": int, "null": type(None), "boolean": bool}
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        assert type(value) in tuple(types[n] for n in names), "type"
    if "const" in schema:
        assert value == schema["const"], "const"
    if "enum" in schema:
        assert value in schema["enum"], "enum"
    if isinstance(value, dict):
        assert set(schema.get("required", [])) <= value.keys(), "required"
        for key, item in value.items():
            child = schema.get("properties", {}).get(key, schema.get("additionalProperties", {}))
            assert child is not False, "unknown field: " + key
            if isinstance(child, dict):
                shape(item, child)
    if isinstance(value, list):
        for item in value:
            shape(item, schema.get("items", {}))
    if isinstance(value, str) and "pattern" in schema:
        assert re.fullmatch(schema["pattern"], value), "pattern"


class InstallSchemaTests(unittest.TestCase):
    setUp = test_setup.SetupTests.setUp
    tearDown = test_setup.SetupTests.tearDown

    def test_actual_generated_client_manifests_and_unknown_field_rejection(self):
        schema = json.loads((self.root / "templates/install-manifest.schema.json").read_text(encoding="utf-8"))
        for clients in (("codex",), ("claude-code",), ("codex", "claude-code")):
            install.setup(self.root, True, clients=clients)
            generated = pm.read_json(self.root / install.MANIFEST)
            shape(generated, schema)
            try:
                import jsonschema
            except ImportError:
                pass
            else:
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(generated, schema)
            for container in (generated, generated["binding"], *generated["clients"].values()):
                container["unexpected"] = True
                with self.assertRaises(AssertionError):
                    shape(generated, schema)
                del container["unexpected"]
            install.uninstall(self.root, True)


if __name__ == "__main__":
    unittest.main()
