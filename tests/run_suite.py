"""Disjoint discovery groups for cargo's bounded four-thread test runner."""
from pathlib import Path
import sys
import unittest


GROUPS=("objects", "accounting", "selectors", "other")


def cases(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite):yield from cases(test)
        else:yield test


def group(test):
    module=test.__class__.__module__
    if module=="test_estimate":return "objects"
    if module=="test_schedule":
        return "accounting" if test.__class__.__name__=="Accounting" else "selectors"
    return "other"


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in GROUPS:
        raise SystemExit("expected one suite group: "+", ".join(GROUPS))
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent))
    selected=unittest.TestSuite(test for test in cases(suite) if group(test)==sys.argv[1])
    if not selected.countTestCases():raise SystemExit("suite group contains no tests")
    result=unittest.TextTestRunner(verbosity=2).run(selected)
    raise SystemExit(not result.wasSuccessful())


if __name__=="__main__":main()
