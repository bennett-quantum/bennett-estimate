"""Exercise hook orchestration with an explicit VCS test double: no git runs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class Hook(unittest.TestCase):
    def test_sha_selection_deletion_and_failure_cleanup(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            base=Path(directory);repo=base/"repo";repo.mkdir()
            log=base/"calls";fake=base/"vcs-double"
            fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,sys
a=sys.argv[3:]
root=pathlib.Path(os.environ["TEST_ROOT"])
log=pathlib.Path(os.environ["TEST_LOG"])
if a[:2]==["rev-parse","--show-toplevel"]: print(root)
elif a[:2]==["rev-parse","HEAD"]: print("1"*40)
elif a[:2]==["rev-parse","--verify"]: print(a[2].split("^")[0])
elif a[:2]==["worktree","add"]:
 p=pathlib.Path(a[3]);sha=a[4];(p/"scripts").mkdir(parents=True)
 check=p/"scripts/check"
 check.write_text('#!/bin/bash\\necho "check:'+sha+'" >> "$TEST_LOG"\\nexit "${TEST_FAIL:-0}"\\n')
 check.chmod(0o755)
elif a[:2]==["worktree","remove"]:
 shutil.rmtree(a[3]);log.open("a").write("cleanup\\n")
else: raise RuntimeError(repr(a))
''')
            fake.chmod(0o755)
            env=dict(os.environ,BENNETT_GATE_GIT=str(fake),TEST_ROOT=str(repo),TEST_LOG=str(log))
            sha="2"*40;zero="0"*40
            line=f"refs/heads/main {sha} refs/heads/main {zero}\n"
            done=subprocess.run([str(ROOT/"scripts/pre-push")],input=line+line,capture_output=True,text=True,env=env,timeout=15)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertEqual(log.read_text().splitlines(),["check:"+sha,"cleanup"])
            self.assertEqual(list(base.glob(".bennett-estimate-gate.*")),[])
            log.write_text("")
            deleted=subprocess.run([str(ROOT/"scripts/pre-push")],input=f"ref {zero} ref {sha}\n",capture_output=True,text=True,env=env,timeout=15)
            self.assertEqual(deleted.returncode,0,deleted.stderr)
            self.assertEqual(log.read_text(),"")
            env["TEST_FAIL"]="7"
            failed=subprocess.run([str(ROOT/"scripts/pre-push")],input=line,capture_output=True,text=True,env=env,timeout=15)
            self.assertEqual(failed.returncode,7,failed.stderr)
            self.assertEqual(log.read_text().splitlines(),["check:"+sha,"cleanup"])
            self.assertEqual(list(base.glob(".bennett-estimate-gate.*")),[])


if __name__=="__main__": unittest.main()
