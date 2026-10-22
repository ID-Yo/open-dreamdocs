import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
import project_memory as pm
import release_package as rp


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dreamdocs-release-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic release test")
        self.git("config", "user.email", "release-test@example.invalid")
        self.put("README.md", "# Synthetic public template\n")
        self.put("LICENSE", "Synthetic license fixture\n")
        self.put("scripts/install.py", 'PACKAGE_VERSION = "test-rc"\n')
        self.put("scripts/dreamdocs.py", "# synthetic entry point\n")
        self.put("scripts/project_memory.py", "# synthetic engine\n")
        self.put("adapters/outcome-block.md", "# Synthetic outcome block\n")
        self.put("human-materials/README.md", (ROOT / "human-materials/README.md").read_text(encoding="utf-8"))
        self.put("human-materials/.gitignore", "*\n!README.md\n!.gitignore\n")
        self.commit()

    def put(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode())

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, timeout=20).stdout

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "Synthetic reviewed snapshot")
        self.revision = self.git("rev-parse", "HEAD").decode().strip()

    def test_reproducible_zip_has_exact_file_hashes_no_history_and_upgrade_manifest(self):
        first, second = (Path(self.temp.name) / name for name in ("first.zip", "second.zip"))
        report = rp.prepare(self.root, self.revision, first)
        self.assertTrue(report["ok"], report)
        self.assertTrue(rp.prepare(self.root, self.revision, second)["ok"])
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertFalse(any(name.startswith((".git/", ".dreamdocs/", "team/", ".bot-mode/")) for name in archive.namelist()))
            inventory = json.loads(archive.read("release-package.json"))
            self.assertFalse(inventory["includes_git_history"])
            self.assertEqual(inventory["revision"], self.revision)
            for path, sha in inventory["files"].items():
                self.assertEqual(pm.digest(archive.read(path)), sha)
            manifest = json.loads(archive.read("dreamdocs-release.json"))
            self.assertEqual(manifest["package_version"], "test-rc")
            self.assertEqual(manifest["revision"], self.revision)
        self.assertTrue(report["history_audited"])
        self.assertFalse(report["publication_authorized"])

    def test_private_runtime_cbm_material_and_key_paths_refuse_package(self):
        for path in ("team/manager/STATE.md", ".bot-mode/agent.json", ".dreamdocs/backup/settings.json", ".codex/hooks.json",
                     "memory/episodes/real.md", "memory/automation/install.json", "human-materials/private.pdf", ".env.local"):
            with self.subTest(path=path):
                self.put(path, "Private synthetic fixture")
                self.git("add", "-f", "--", path)
                self.git("commit", "-qm", "Synthetic private contamination")
                revision = self.git("rev-parse", "HEAD").decode().strip()
                out = Path(self.temp.name) / "refused.zip"
                self.assertFalse(rp.prepare(self.root, revision, out)["ok"])
                self.assertFalse(out.exists())
                self.git("reset", "--hard", self.revision)

    def test_removed_secret_or_cbm_history_still_refuses_clean_looking_head(self):
        self.put("team/private.md", "Synthetic private prior record")
        self.commit()
        self.git("rm", "team/private.md")
        self.commit()
        result = rp.prepare(self.root, self.revision)
        self.assertFalse(result["ok"])
        self.assertTrue(any(f["scope"] == "history" for f in result["findings"]))

    def test_secret_content_and_populated_index_are_not_silently_exported(self):
        self.put("docs/operations/accidental.md", "token=" + "sk-" + "AbCdEf1234567890" * 2)
        self.commit()
        self.assertFalse(rp.prepare(self.root, self.revision)["ok"])

    def test_exact_marker_only_fixture_is_allowed_but_modified_credential_content_is_not(self):
        fixture = "tests/fixtures/automation/unsafe-secret.json"
        target = self.root / fixture
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / fixture).read_bytes())
        self.commit()
        clean = rp.prepare(self.root, self.revision)
        self.assertTrue(clean["ok"], clean)
        self.assertEqual(clean["synthetic_fixture_exceptions"], 1)
        target.write_bytes(target.read_bytes() + b"\n" + b"sk-" + b"AbCdEf1234567890" * 2)
        self.commit()
        self.assertFalse(rp.prepare(self.root, self.revision)["ok"])
        self.put("human-materials/README.md", "# Private index without originals\n")
        self.commit()
        self.assertFalse(rp.prepare(self.root, self.revision)["ok"])

    def test_dirty_source_exact_revision_and_output_overwrite_refuse(self):
        self.put("README.md", "unreviewed edit")
        self.assertFalse(rp.prepare(self.root, self.revision)["ok"])
        self.git("restore", "README.md")
        self.assertFalse(rp.prepare(self.root, "HEAD")["ok"])
        out = Path(self.temp.name) / "existing.zip"
        out.write_bytes(b"preserve owner file")
        self.assertFalse(rp.prepare(self.root, self.revision, out)["ok"])
        self.assertEqual(out.read_bytes(), b"preserve owner file")

    def test_version_stamps_agree_and_candidate_does_not_claim_both_agents_are_released(self):
        self.assertEqual(install.PACKAGE_VERSION, "1.5.0-rc.1")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(install.PACKAGE_VERSION, readme)
        self.assertIn("Claude", readme)
        self.assertIn("release gate", readme.casefold())


if __name__ == "__main__":
    unittest.main()
