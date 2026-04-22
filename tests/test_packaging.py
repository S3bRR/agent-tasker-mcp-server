from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


def _match(pattern: str, text: str) -> str:
    matched = re.search(pattern, text, re.MULTILINE)
    if not matched:
        raise AssertionError(f"Pattern not found: {pattern}")
    return matched.group(1)


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.pyproject = (cls.root / "pyproject.toml").read_text(encoding="utf-8")
        cls.readme = (cls.root / "README.md").read_text(encoding="utf-8")
        cls.server_manifest = json.loads((cls.root / "server.json").read_text(encoding="utf-8"))

    def test_server_manifest_matches_package_metadata(self) -> None:
        package_name = _match(r'^name = "([^"]+)"$', self.pyproject)
        package_version = _match(r'^version = "([^"]+)"$', self.pyproject)
        package = self.server_manifest["packages"][0]

        self.assertEqual(self.server_manifest["version"], package_version)
        self.assertEqual(package["identifier"], package_name)
        self.assertEqual(package["version"], package_version)
        self.assertEqual(package["registryType"], "pypi")
        self.assertEqual(package["transport"]["type"], "stdio")

    def test_readme_has_mcp_registry_verification_marker(self) -> None:
        marker = f"mcp-name: {self.server_manifest['name']}"
        self.assertIn(marker, self.readme)
        self.assertRegex(self.server_manifest["name"], r"^io\.github\.[^/]+/.+$")


if __name__ == "__main__":
    unittest.main()
