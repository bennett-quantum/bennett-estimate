"""Terminal cleanup obligations beyond the phase-free witness grammar."""
import unittest
from unittest.mock import patch

from test_schedule import ROOT, e, make_object, target, entry, point


class Recompute(unittest.TestCase):
    def scheduled(self, body, kind="perm_action", inherited=0):
        signature={"abi":"0.9","tier":"q","kind":kind,"mut":[1,1],
                   "in":[1,1],"mem":[],"args":[],"bounds":[]}
        code=f"{kind} @root (x:wire, y:wire) (z:wire in, c:wire in) () () ()\n^entry():\n{body}"
        obj=make_object(code,signature);t=target()
        base=e.estimate(obj,t,"root",[],["0"]*4,inherited_controls=inherited)
        doc=base["effective_schedule"]
        doc["entries"]=[entry("cleanup",realisation="recompute")]
        obj.sections["schedule"]=doc
        return obj,t

    def admitted(self, body, kind="perm_action", inherited=0):
        obj,t=self.scheduled(body,kind,inherited)
        result=e.estimate(obj,t,"root",[],["0"]*4,inherited_controls=inherited,include_frame=True)
        self.assertEqual(result["label"],"exact")
        self.assertTrue(all(d["realisation"]=="recompute" for d in result["cleanup_decisions"]))
        return obj,t,result

    def test_effective_controls_and_nonentry_input_versions(self):
        body="x x\nqpred c\nd = qalloc any 1\ncx x d\ncx z d\ncx z d\nqunpred c\nx y\nqpred c\ncx x d\nqunpred c\nqfree d"
        obj,t,result=self.admitted(body,inherited=1)
        self.assertEqual(result["cleanup_decisions"][0]["owned_points"],["entry:5","entry:9","entry:11"])
        schedules=[]
        for inverse in [False,True]:
            catalog=e.Catalog((ROOT/"data/ref-0.9.json").read_text(),t)
            catalog.ledger=e.Ledger(t,e.Schedule(obj.sections["schedule"],obj,"root"))
            controls=(("inherited",0,catalog.default_class),)
            e.Source(obj,t,catalog).region("root",[],["0"]*4,controls=controls,raw_inverse=inverse)
            schedules.append(catalog.ledger.finish())
        self.assertEqual(schedules[0],schedules[1])

    def test_intrinsic_control_duplicates_do_not_change_effective_control_set(self):
        for op in ["cx","qxor"]:
            body=f"d = qalloc any 1\nqpred x\n{op} x d\nqunpred x\n{op} x d\nqfree d"
            _,_,result=self.admitted(body)
            self.assertEqual(result["cleanup_decisions"][0]["owned_points"],["entry:4","entry:5"])

    def test_composed_identity_does_not_replace_source_occurrence_matching(self):
        obj,t=self.scheduled("d = qalloc any 1\nqxor x d\ncx x d\nqfree d")
        with self.assertRaisesRegex(e.ContractError,"recompute.*pending/unestablished.*computing occurrences"):
            e.estimate(obj,t,"root",[],["0"]*4)
        obj.sections["schedule"]["entries"][0]["cleanup"]["realisation"]="reverse"
        self.assertEqual(e.estimate(obj,t,"root",[],["0"]*4)["label"],"exact")

    def test_reallocation_does_not_restore_an_earlier_input_lifetime(self):
        body="b = qalloc any 1\na = qalloc any 1\ncx b a\nqfree b\nb = qalloc any 1\ncx b a\nqfree a\nqfree b"
        obj,t=self.scheduled(body)
        obj.sections["schedule"]["entries"]=[entry("cleanup",path=[point(obj.symbol("root")["interface_hash"],"entry:6")],realisation="recompute")]
        with self.assertRaisesRegex(e.ContractError,"recompute.*pending/unestablished.*computing occurrences"):
            e.estimate(obj,t,"root",[],["0"]*4)
        obj.sections["schedule"]["entries"][0]["cleanup"]["realisation"]="reverse"
        self.assertEqual(e.estimate(obj,t,"root",[],["0"]*4)["label"],"exact")

    def test_diagonal_cancellations_and_controlled_global_phase(self):
        prefix="d = qalloc any 1\nx d\nx d\n"
        self.admitted(prefix+"t d\ntdg d\nqfree d",kind="action")
        for middle,conflict in [("s d\ns d","entry:3"), ("qpred c\ns d\ns d\nqunpred c","entry:4")]:
            with self.subTest(middle=middle):
                obj,t=self.scheduled(prefix+middle+"\nqfree d",kind="action")
                with self.assertRaisesRegex(e.ContractError,"recompute.*refused:.*state/phase.*"+conflict):
                    e.estimate(obj,t,"root",[],["0"]*4)

    def test_relative_phase_on_postponed_scratch_is_not_ignored(self):
        body="d = qalloc any 1\ncx x d\ncx z d\ncx z d\nt d\ncx x d\ntdg x\nqfree d"
        obj,t=self.scheduled(body,kind="action")
        with self.assertRaisesRegex(e.ContractError,"recompute.*refused:.*state/phase.*entry:4"):
            e.estimate(obj,t,"root",[],["0"]*4)

    def test_protected_writes_cannot_be_excused_by_net_identity(self):
        body="d = qalloc any 1\ncx x d\ncx z d\ncx z d\nx x\nx d\nx d\nx x\ncx x d\nqfree d"
        obj,t=self.scheduled(body)
        with self.assertRaisesRegex(e.ContractError,"recompute.*refused:.*protected basis value.*entry:5"):
            e.estimate(obj,t,"root",[],["0"]*4)

    def test_borrowed_entry_is_restored_without_using_it_as_fresh_input(self):
        body="d = qborrow any 1\ncx x d\ncx z d\ncx z d\nx y\ncx x d\nqreturn d"
        _,_,result=self.admitted(body)
        self.assertEqual(result["resources"]["gate_count"],"8")
        self.assertEqual(result["cleanup_decisions"][0]["owned_points"],["entry:3","entry:5","entry:6"])

    def test_joint_inverse_has_one_owner_and_fresh_targets(self):
        body="a = qalloc any 1\nb = qalloc any 1\nswap a b\nswap a b\nqfree a\nqfree b"
        _,_,result=self.admitted(body)
        owners=[d["owned_points"] for d in result["cleanup_decisions"]]
        self.assertEqual(sum(points.count("entry:3") for points in owners),1)
        self.assertEqual(owners,[["entry:3","entry:4"],["entry:5"]])

    def test_empty_cleanup_retains_its_carrier(self):
        _,_,result=self.admitted("d = qalloc any 1\nqfree d")
        self.assertEqual(result["cleanup_decisions"][0]["owned_points"],["entry:1"])
        # Even the empty computing sequence has the literal one-bit XOR.
        self.assertEqual(result["resources"]["gate_count"],"1")

    def test_disjoint_release_does_not_break_a_terminal_chain(self):
        body="a = qalloc any 1\ncx x a\ncx x a\nb = qalloc any 1\nqfree b\nqfree a"
        _,_,result=self.admitted(body)
        self.assertEqual([d["owned_points"] for d in result["cleanup_decisions"]],[["entry:4"],["entry:2","entry:5"]])

    def test_intrinsic_cleanup_remains_a_boundary(self):
        body="d = qcopy z\ncx x d\ncx x d\nquncopy z d"
        _,_,result=self.admitted(body)
        self.assertEqual(len(result["cleanup_decisions"]),1)
        self.assertEqual(result["cleanup_decisions"][0]["chain"][-1]["point"],"entry:3")

    def test_proof_unavailability_preserves_source_reverse_support(self):
        body="d = qalloc any 1\ncx x d\ncx x d\nh y\nqfree d"
        obj,t=self.scheduled(body,kind="action")
        with self.assertRaisesRegex(e.ContractError,"recompute.*pending/unestablished.*proof for h"):
            e.estimate(obj,t,"root",[],["0"]*4)
        obj.sections["schedule"]["entries"][0]["cleanup"]["realisation"]="reverse"
        self.assertEqual(e.estimate(obj,t,"root",[],["0"]*4)["label"],"exact")

    def test_symbolic_work_allowance_defers_instead_of_refusing(self):
        obj,t=self.scheduled("d = qalloc any 1\ncx x d\ncx x d\nqfree d")
        with patch.object(e.CleanupSemantics,"MAX_TERMS",0):
            with self.assertRaisesRegex(e.ContractError,"recompute.*pending/unestablished.*allowance exceeded"):
                e.estimate(obj,t,"root",[],["0"]*4)

    def test_storage_work_is_bounded_before_enumerating_wire_versions(self):
        obj,t=self.scheduled("d = qalloc any 1\ncx x d\ncx x d\nqfree d")
        for allowance in ["MAX_PROOF_WIRES","MAX_PROOF_ROWS"]:
            with patch.object(e.TerminalCleanups,allowance,0),patch.object(e,"CleanupVersions",side_effect=AssertionError("expanded before work guard")):
                obj.sections["schedule"]["entries"][0]["cleanup"]["realisation"]="recompute"
                with self.assertRaisesRegex(e.ContractError,"recompute.*pending"):
                    e.estimate(obj,t,"root",[],["0"]*4)
                obj.sections["schedule"]["entries"][0]["cleanup"]["realisation"]="reverse"
                self.assertEqual(e.estimate(obj,t,"root",[],["0"]*4)["label"],"exact")


if __name__=="__main__":unittest.main()
