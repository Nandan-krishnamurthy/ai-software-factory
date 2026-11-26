"""SR1.1: ``safe_write``, the factory writers' refusal of protected folders (N1, N22)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import acmap, evidence, files, prbody


class SafeWriteTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.factory = self.root / "factory"
        self.home = self.root / "home"
        self.roots = dict(factory_root=self.factory, home=self.home)

    def protected(self):
        return {
            "scripts/": self.factory / "scripts" / "factory" / "guard.py",
            ".claude/": self.factory / ".claude" / "settings.json",
            ".claude/ (local)": self.factory / ".claude" / "settings.local.json",
            ".factory-local/": self.factory / ".factory-local" / "target.json",
            "~/.claude/": self.home / ".claude" / "projects" / "x" / "memory" / "m.md",
            "~/.claude/ settings": self.home / ".claude" / "settings.json",
        }

    def test_refuses_each_protected_root(self):
        for label, path in self.protected().items():
            with self.subTest(root=label):
                with self.assertRaises(files.UnsafeWriteError):
                    files.safe_write(path, "x", **self.roots)
                self.assertFalse(path.exists())
                self.assertFalse(path.parent.exists(), "no folder is created either")

    def test_writes_elsewhere_as_text_or_bytes(self):
        text = files.safe_write(self.root / "out" / "a.md", "héllo\n", **self.roots)
        self.assertEqual(text.read_text(encoding="utf-8"), "héllo\n")
        raw = files.safe_write(self.root / "b.bin", b"\x00\r\n", **self.roots)
        self.assertEqual(raw.read_bytes(), b"\x00\r\n")
        # The factory's other folders are not protected by safe_write.
        files.safe_write(self.factory / "docs" / "x.md", "x", **self.roots)

    def test_similar_names_are_not_protected(self):
        files.safe_write(self.factory / ".factory-localx" / "a", "x", **self.roots)
        files.safe_write(self.factory / "scripts-old" / "a", "x", **self.roots)

    def test_relative_and_dotted_paths_are_resolved(self):
        sneaky = self.factory / "docs" / ".." / "scripts" / "factory" / "guard.py"
        with self.assertRaises(files.UnsafeWriteError):
            files.safe_write(sneaky, "x", **self.roots)

    def test_a_link_into_a_protected_root_is_refused(self):
        real = self.factory / ".claude"
        real.mkdir(parents=True)
        link = self.root / "innocent"
        try:
            os.symlink(real, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symlinks")
        with self.assertRaises(files.UnsafeWriteError):
            files.safe_write(link / "settings.json", "x", **self.roots)


class WritersUseSafeWriteTest(unittest.TestCase):
    """Each factory writer refuses a protected path (with the real roots patched to a
    temporary factory, so nothing near this repo is touched)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.factory = Path(tmp.name).resolve() / "factory"
        patcher = mock.patch.object(files.target_mod, "FACTORY_ROOT", self.factory)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = self.factory / ".claude" / "settings.json"

    def assert_refused(self, write):
        with self.assertRaises(files.UnsafeWriteError):
            write(self.path)
        self.assertFalse(self.path.exists())

    def test_prbody_write(self):
        rendered = prbody.Rendered(body="x", gates=[], problems=[], warnings=[])
        self.assert_refused(lambda p: prbody.write(rendered, p))

    def test_acmap_write(self):
        result = acmap.AcMap(issue=1, repo="o/r", branch="b", sha="s", base="main@s",
                             sources=[], acs=[])
        self.assert_refused(lambda p: acmap.write(result, p))

    def test_evidence_write(self):
        result = evidence.Evidence(issue=1, repo="o/r", branch="b", sha="s", started_at="t",
                                   finished_at="t", commands=[], sha_after="s")
        self.assert_refused(lambda p: evidence.write(result, p))

    def test_evidence_files_beside_the_json_are_checked_too(self):
        result = evidence.Evidence(issue=1, repo="o/r", branch="b", sha="s", started_at="t",
                                   finished_at="t", commands=[], sha_after="s",
                                   outputs={"test": "ok"})
        calls = []
        with mock.patch.object(evidence, "safe_write",
                               side_effect=lambda p, c: calls.append(Path(p)) or Path(p)):
            evidence.write(result, Path(tempfile.gettempdir()) / "evidence-1.json")
        self.assertEqual([p.name for p in calls], ["evidence-1.json", "evidence-1.test.log"])


if __name__ == "__main__":
    unittest.main()
