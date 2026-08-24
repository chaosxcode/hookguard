"""Unit tests for the scoring engine — the weights are public, so the math
must be too. Run: python3 -m unittest discover -s tests -v"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from score import compute_score, band                      # noqa: E402


class ScoringMath(unittest.TestCase):
    def test_baseline_is_zero(self):
        s = compute_score({"source_analyzed": True})
        self.assertEqual((s["score"], s["band"]), (0, "LOW"))

    def test_no_source_prices_opacity(self):
        s = compute_score({"source_checked_and_missing": True})
        self.assertEqual(s["score"], 25)
        self.assertEqual([f["key"] for f in s["factors"]], ["no_source"])

    def test_high_findings_stack_linearly(self):
        one = compute_score({"source_analyzed": True, "high_findings": 1})
        three = compute_score({"source_analyzed": True, "high_findings": 3})
        self.assertEqual(one["score"], 15)
        self.assertEqual(three["score"], 45)

    def test_opaque_impl_beats_readable_impl(self):
        opaque = compute_score({"delegatecall_targets": {"kind": "constant"},
                                "opaque_implementations": ["0xdead"]})
        readable = compute_score({"delegatecall_targets": {"kind": "constant"}})
        self.assertEqual(opaque["score"], 20)
        self.assertEqual(readable["score"], 12)

    def test_author_confirmation_subtracts(self):
        base = {"source_analyzed": True,
                "medium_findings": 4}          # +28, comfortably above floor
        with_c = dict(base, author_confirmed_intended=True)
        a, b = compute_score(base), compute_score(with_c)
        self.assertEqual(a["score"] - b["score"], 12)
        self.assertTrue(any(f["key"] == "author_confirmed" for f in b["factors"]))

    def test_score_clamps_to_zero_floor(self):
        s = compute_score({"source_analyzed": True, "medium_findings": 1,
                           "author_confirmed_intended": True})
        self.assertEqual(s["score"], 0)        # +7 -12 floors at zero

    def test_score_clamps_to_100(self):
        s = compute_score({"no_source": None, "source_checked_and_missing": True,
                           "selfdestruct": True, "permission_bits": 14,
                           "high_findings": 4, "medium_findings": 6,
                           "unregistered": True, "audit_recorded": False})
        self.assertLessEqual(s["score"], 100)


class Confidence(unittest.TestCase):
    def test_layers_drive_confidence(self):
        full = compute_score({"source_analyzed": True,
                              "delegatecall_targets": {"kind": "storage-derived"},
                              "selfdestruct": True})
        self.assertEqual(full["confidence"], "high")
        thin = compute_score({"source_checked_and_missing": True})
        self.assertIn(thin["confidence"], ("medium", "low"))


class Bands(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(band(0), "LOW")
        self.assertEqual(band(24), "LOW")
        self.assertEqual(band(25), "MODERATE")
        self.assertEqual(band(49), "MODERATE")
        self.assertEqual(band(50), "ELEVATED")
        self.assertEqual(band(75), "HIGH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
