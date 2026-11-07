"""Product reports describe contract evidence without task-tracker identities."""
import contextlib
import io
import json
import unittest
from test_estimate import ROOT, e, sibling


class Output(unittest.TestCase):
    def test_pending_output_has_contract_code_and_reason_only(self):
        command = [str(ROOT / "tests/fixtures/ret-delivery-source-gap.bisa"), "--target",
                   str(sibling(ROOT, "bennett-targets") / "targets/ideal-all-to-all.json"),
                   "--region", "root", "--budget", "2,0,0,0", "--token-aliases", "[0]"]
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            status = e.main(command)
        self.assertEqual(status, 3, err.getvalue())
        report = json.loads(out.getvalue())
        self.assertEqual(set(report["pending"][0]), {"code", "reason"})
        self.assertEqual(report["pending"][0]["code"], "EST-SOURCE-03")
        self.assertTrue(report["pending"][0]["reason"])
        self.assertNotIn("bennett-estimate-bph", out.getvalue())

    def test_unknown_native_models_report_unsupported_obligations(self):
        doc = e.loads((ROOT / "data/ideal-four-clique.json").read_text())
        doc["gates"][0]["realisation_model"] = {"version": "future.native-model/2", "payload": {}}
        target = e.Target.read(e.jcs(doc))
        obj = e.Object.read((ROOT / "tests/fixtures/example3.bisa").read_text())
        result = e.estimate(obj, target, "borrow_demo", [], ["0"] * 4)
        self.assertEqual(result["native_model_obligations"],
                         [{"gate_entry": 0, "version": "future.native-model/2", "status": "unsupported-model"}])
        self.assertEqual(result["resources"], {"gate_count": "4", "time": "4", "peak_qubits[data]": "3", "qubit_second[data]": "12"})
