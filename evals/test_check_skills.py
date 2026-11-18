import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from check_skills import check_manifests, MANIFESTS, ROOT


class TestPluginManifests(TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))
        for name in MANIFESTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        (self.root / 'skills').mkdir()
        (self.root / 'plugins').mkdir()
        (self.root / 'plugins/python-powers').symlink_to('..', target_is_directory=True)
        self.assertEqual(check_manifests(self.root), [])

    def test_mismatched_release(self) -> None:
        path = self.root / '.claude-plugin/marketplace.json'
        manifest = json.loads(path.read_text())
        manifest['metadata']['version'] = '0.0.0-test'
        path.write_text(json.dumps(manifest))
        self.assertTrue(any('plugin versions differ' in error for error in check_manifests(self.root)))

    def test_broken_marketplace_link(self) -> None:
        (self.root / 'plugins/python-powers').unlink()
        self.assertTrue(any('.agents/plugins/marketplace.json' in error for error in check_manifests(self.root)))
