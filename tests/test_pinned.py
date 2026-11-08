"""Pinned siblings resolve in isolated gate layouts and ordinary checkouts."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pinned import sibling


class PinnedSibling(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.main = self.base / "main"
        self.layout = self.base / "gate-root/.tmp/gate/runs/run"
        self.root = self.layout / "bennett-estimate"
        self.root.mkdir(parents=True)
        metadata = self.main / ".git/worktrees/run"
        metadata.mkdir(parents=True)
        (metadata / "commondir").write_text("../..\n")
        (self.root / ".git").write_text(f"gitdir: {metadata}\n")
        self.name = "bennett-targets"
        self.sha = "a" * 40
        self.content = b'{"name":"pinned target"}\n'
        digest = hashlib.sha256(self.content).hexdigest()
        (self.root / "gate.toml").write_text(
            f'[siblings."{self.name}"]\nsha = "{self.sha}"\n'
            f'[siblings."{self.name}".files]\n"target.json" = "{digest}"\n')
        self.candidates = [self.layout / self.name,
                           self.root / ".tmp/gate/cache" / f"{self.name}@{self.sha[:12]}" / self.name,
                           self.root / ".tmp/gate-siblings" / f"{self.name}@{self.sha}",
                           self.main / ".tmp/gate/cache" / f"{self.name}@{self.sha[:12]}" / self.name]
        environment = patch.dict(os.environ, BENNETT_GATE_LAYOUT=str(self.layout))
        environment.start()
        self.addCleanup(environment.stop)

    def populate(self, path):
        path.mkdir(parents=True)
        (path / ".gate-pin").write_text(self.sha + "\n")
        (path / "target.json").write_bytes(self.content)
        return path

    def test_gate_layout_resolves_symlink_without_commondir_cache(self):
        pinned = self.populate(self.base / "gate-root/.tmp/gate/cache" /
                               f"{self.name}@{self.sha[:12]}" / self.name)
        self.candidates[0].symlink_to(pinned, target_is_directory=True)
        self.assertTrue(all(not path.exists() for path in self.candidates[1:]))
        resolved = sibling(self.root, self.name)
        self.assertEqual(resolved, self.candidates[0])
        self.assertEqual(resolved.resolve(), pinned)
        self.assertEqual((resolved / "target.json").read_bytes(), self.content)

    def test_layout_precedes_all_existing_cache_candidates(self):
        self.populate(self.candidates[0])
        for candidate in self.candidates[1:]:
            self.populate(candidate)
            (candidate / ".gate-pin").write_text("b" * 40)
        self.assertEqual(sibling(self.root, self.name), self.candidates[0])

    def test_selected_candidate_never_falls_back_on_revision_or_hash_mismatch(self):
        for candidate in self.candidates:
            self.populate(candidate)
        for candidate in self.candidates:
            with self.subTest(candidate=candidate):
                try:
                    (candidate / ".gate-pin").write_text("b" * 40)
                    with self.assertRaisesRegex(RuntimeError, f"{self.name}@{self.sha}: checkout revision {'b' * 40}"):
                        sibling(self.root, self.name)
                    (candidate / ".gate-pin").write_text(self.sha)
                    (candidate / "target.json").write_bytes(b"modified")
                    actual = hashlib.sha256(b"modified").hexdigest()
                    expected = hashlib.sha256(self.content).hexdigest()
                    with self.assertRaisesRegex(RuntimeError, f"target.json hash {actual}, expected {expected}"):
                        sibling(self.root, self.name)
                finally:
                    (candidate / "target.json").unlink()
                    (candidate / ".gate-pin").unlink()
                    candidate.rmdir()

    def test_existing_candidates_with_unset_empty_or_missing_layout(self):
        for setting in (None, "", str(self.layout)):
            with patch.dict(os.environ):
                os.environ.pop("BENNETT_GATE_LAYOUT")
                if setting is not None:
                    os.environ["BENNETT_GATE_LAYOUT"] = setting
                for candidate in self.candidates[1:]:
                    with self.subTest(layout=setting, candidate=candidate):
                        self.populate(candidate)
                        self.assertEqual(sibling(str(self.root), self.name), candidate)
                        (candidate / "target.json").unlink()
                        (candidate / ".gate-pin").unlink()
                        candidate.rmdir()

    def test_layout_checks_detached_git_revision_without_marker(self):
        candidate = self.populate(self.candidates[0])
        (candidate / ".gate-pin").unlink()
        (candidate / ".git").mkdir()
        (candidate / ".git/HEAD").write_text(self.sha + "\n")
        self.assertEqual(sibling(self.root, self.name), candidate)
        (candidate / ".git/HEAD").write_text("b" * 40)
        with self.assertRaisesRegex(RuntimeError, "checkout revision " + "b" * 40):
            sibling(self.root, self.name)

    def test_relative_layout_resolves_from_the_process_directory(self):
        self.populate(self.candidates[0])
        relative = os.path.relpath(self.layout, Path.cwd())
        with patch.dict(os.environ, BENNETT_GATE_LAYOUT=relative):
            resolved = sibling(self.root, self.name)
        self.assertEqual(resolved.resolve(), self.candidates[0])
        self.assertEqual((resolved / "target.json").read_bytes(), self.content)

    def test_malformed_or_non_directory_layout_uses_valid_pinned_cache(self):
        self.populate(self.candidates[1])
        regular_file = self.base / "regular-file"
        regular_file.write_text("not a layout")
        for value in (str(regular_file), " ", "\t", "\n", "not-a-layout"):
            with self.subTest(layout=value), patch.dict(os.environ, BENNETT_GATE_LAYOUT=value):
                self.assertEqual(sibling(self.root, self.name), self.candidates[1])

    def test_missing_pinned_file_propagates(self):
        candidate = self.populate(self.candidates[0])
        self.populate(self.candidates[1])
        (candidate / "target.json").unlink()
        with self.assertRaises(FileNotFoundError) as raised:
            sibling(self.root, self.name)
        self.assertEqual(raised.exception.filename, str(candidate / "target.json"))

    def test_missing_pin_names_every_candidate(self):
        with self.assertRaises(RuntimeError) as raised:
            sibling(self.root, self.name)
        message = str(raised.exception)
        self.assertIn(f"missing gate pin {self.name}@{self.sha}", message)
        for candidate in self.candidates:
            self.assertIn(str(candidate), message)


if __name__ == "__main__":
    unittest.main()
