"""Offline tests for the High / Medium / Low rating logic (no AI calls). Run: ../files2/.venv/Scripts/python -m pytest -q"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "files2"))

from confidence import apply_doubts, score_doc  # noqa: E402
from schemas import Ev, Val  # noqa: E402
from to_viewer import part1_doubt_path  # noqa: E402


def test_generic_values_get_a_model_rating_and_blanks_none():
    doc = {"status": {"kaccha": "N", "mode": "Air", "exam": None, "assess": ""}, "payments": [{"amount": 0}]}
    conf = score_doc(doc, "MODE Air")
    assert conf["status.kaccha"]["b"] == "model" and conf["status.kaccha"]["s"] >= 0.8   # one-letter flag
    assert conf["payments.0.amount"]["b"] == "model"                                     # zero
    assert conf["status.mode"]["b"] == "text"                                            # still text-matched
    assert "status.exam" not in conf and "status.assess" not in conf                     # blank: nothing to rate


def test_doubts_lower_but_never_raise():
    conf = {"a": {"s": 0.9, "b": "model", "r": []}, "b": {"s": 0.45, "b": "text", "r": ["x"]}}
    apply_doubts(conf, [("a", "medium"), ("b", "medium"), ("c", "low")])
    assert conf["a"]["s"] == 0.7 and "not fully sure" in conf["a"]["r"][0]
    assert conf["b"]["s"] == 0.45                                    # already lower: unchanged
    assert conf["c"] == {"s": 0.4, "b": "model", "r": ["AI is not fully sure (low)"]}


def test_part1_doubt_paths():
    assert part1_doubt_path("status.kaccha") == "status.kaccha"
    assert part1_doubt_path("status.sec_48") == "status.sec48"
    assert part1_doubt_path("manifest.igm_no") == "manifest.igmNo"
    assert part1_doubt_path("header.gross_weight") == "boe.grossWeightKg"
    assert part1_doubt_path("payments[0].challan_no") == "payments.0.challanNo"
    assert part1_doubt_path("ooc_no") == "processing.oocNo"
    assert part1_doubt_path("nonsense") is None


def test_core_val_default_is_high_and_caps_score():
    assert Val(value="1").conf == "high" and Ev(value="1").conf == "high"
    import pipeline
    assert pipeline.MODEL_CAP == {"medium": 0.7, "low": 0.4}
