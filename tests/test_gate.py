"""Validate pinned hook configuration and its git-free development entry."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
import tomllib

ROOT=Path(__file__).resolve().parents[1]


class Hook(unittest.TestCase):
    def test_pinned_sibling_hook_configuration_and_git_free_working_tree(self):
        config=tomllib.loads((ROOT/"gate.toml").read_text())
        self.assertEqual(config["schema"],1)
        self.assertRegex(config["tool_sha"],r"^[0-9a-f]{40}$")
        self.assertEqual(config["check"],[{"name":"scripts/check","argv":["scripts/check"]}])
        self.assertEqual(set(config["siblings"]),{"bennett-isa-spec","bennett-targets","bennett-conformance","bennett-vm"})
        for sibling in config["siblings"].values():self.assertRegex(sibling["sha"],r"^[0-9a-f]{40}$")
        self.assertEqual(config["env"]["BENNETT_VM_BIN"],"{sibling:bennett-vm}/target/debug/bennett-vm")
        self.assertIn("target/debug/bennett-vm",config["siblings"]["bennett-vm"]["build"][0]["outputs"])
        source=(ROOT/"scripts/pre-push").read_text()
        self.assertIn('tools/gate_run.py',source)
        self.assertIn('show HEAD:gate.toml',source)
        self.assertIn('run --repo "$root" --tool-sha "$tool_sha"',source)
        self.assertLess(source.index('--working-tree'),source.index('$(git'))
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            scripts=Path(directory)/"scripts";scripts.mkdir()
            hook=scripts/"pre-push";hook.write_text(source);hook.chmod(0o755)
            marker=Path(directory)/"checked"
            check=scripts/"check"
            check.write_text('#!/usr/bin/env bash\nset -eu\nprintf checked > "$TEST_CHECK_MARKER"\nexit "${TEST_CHECK_EXIT:-0}"\n');check.chmod(0o755)
            env=dict(os.environ,TEST_CHECK_MARKER=str(marker))
            done=subprocess.run([str(hook),"--working-tree"],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(done.returncode,0,done.stderr);self.assertEqual(marker.read_text(),"checked")
            env["TEST_CHECK_EXIT"]="7"
            self.assertEqual(subprocess.run([str(hook),"--working-tree"],env=env,capture_output=True,timeout=10).returncode,7)

    def test_parallel_suites_partition_every_discovered_case_once(self):
        location=Path(__file__).with_name("run_suite.py")
        spec=importlib.util.spec_from_file_location("suite_runner",location)
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        tests=list(runner.cases(unittest.TestLoader().discover(str(location.parent))))
        groups={name:[t.id() for t in tests if runner.group(t)==name] for name in runner.GROUPS}
        self.assertTrue(all(groups.values()))
        selected=[identity for identities in groups.values() for identity in identities]
        self.assertEqual(sorted(selected),sorted(t.id() for t in tests))
        self.assertEqual(len(selected),len(set(selected)))
        recursive=next(t for t in tests if t.id().endswith('.test_recursive_fixed_instances_keep_separate_row_domains_for_equal_values'))
        self.assertEqual(runner.group(recursive),'selectors')



if __name__=="__main__": unittest.main()
