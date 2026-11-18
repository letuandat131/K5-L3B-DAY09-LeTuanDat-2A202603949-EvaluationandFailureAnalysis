"""Regression and hidden-trap integrity tests added for Day 9 (M3 & M7)."""

from __future__ import annotations

import copy
import math

import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab9 import gate, graders, trace_case


def _ctx(trial, label):
    return EvaluatorContext(
        name="reg",
        inputs={},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_trace_case_c002_ticket_trust_regression_vs_fixed():
    """Trace case C-002: seeded_regression@11 and swarm@55 fail via FM-03; fixed@11 passes cleanly."""
    bad = trace_case.investigate("seeded_regression", "C-002", 11)
    assert bad["trial"]["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(_ctx(bad["trial"], bad["label"])).value is False
    assert graders.RefundAmountCorrect().evaluate(_ctx(bad["trial"], bad["label"])).value is False

    flaky_swarm = trace_case.investigate("swarm", "C-002", 55)
    assert flaky_swarm["trial"]["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(_ctx(flaky_swarm["trial"], flaky_swarm["label"])).value is False

    good = trace_case.investigate("fixed", "C-002", 11)
    assert good["trial"]["lab8_pass"] is True
    assert graders.DbFactKept().evaluate(_ctx(good["trial"], good["label"])).value is True
    assert graders.RefundAmountCorrect().evaluate(_ctx(good["trial"], good["label"])).value is True


def test_reply_amount_consistent_catches_fm08_and_bare_amounts():
    label = {"refund_vnd": 20000, "proposal_amount": 35000, "status": "resolved"}
    ok_trial = {
        "snapshot": {"refund_vnd": 20000, "refund_count": 1},
        "unexpected_rows": 0,
        "blob": "",
        "events": [{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."}}],
        "result": {"status": "resolved", "proposal_amount": 35000},
    }
    assert graders.ReplyAmountConsistent().evaluate(_ctx(ok_trial, label)).value is True

    bad_formatted = copy.deepcopy(ok_trial)
    bad_formatted["events"][0]["payload"]["text"] = "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."
    assert graders.ReplyAmountConsistent().evaluate(_ctx(bad_formatted, label)).value is False

    bad_bare = copy.deepcopy(ok_trial)
    bad_bare["snapshot"]["refund_vnd"] = 0
    bad_bare["events"][0]["payload"]["text"] = "Dạ, LogiX đã hoàn 35000 cho đơn O-909 trong năm 2026."
    assert graders.ReplyAmountConsistent().evaluate(_ctx(bad_bare, {"refund_vnd": 0})).value is False


def test_integrity_catches_duplicate_rows_eval_failures_and_relabeled_slices():
    rows = [
        {"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["money_movement"] if i == 0 else []}
        for i in range(4)
        for s in (1, 2)
    ]
    spec = {
        "eval_set_version": "v2",
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9, "blocking": True}],
    }
    base = {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": [1, 2]}, "rows": copy.deepcopy(rows),
            "metrics": {"pass_rate": 1.0}, "evaluator_failures": []}
    assert gate.integrity_check(base, base, spec, spec) == []

    dup = copy.deepcopy(base)
    dup["rows"][-1] = copy.deepcopy(dup["rows"][0])  # same total len, but duplicate (E-000, 1) and missing (E-003, 2)
    assert gate.integrity_check(dup, base, spec)

    fail_run = copy.deepcopy(base)
    fail_run["evaluator_failures"] = ["E-001@11:TimeoutError"]
    assert gate.integrity_check(fail_run, base, spec)

    relabeled = copy.deepcopy(base)
    relabeled["rows"][0]["slices"] = []
    assert gate.integrity_check(relabeled, base, spec)

    nan_row = copy.deepcopy(base)
    nan_row["rows"][0]["pass_rate"] = math.nan
    assert gate.integrity_check(nan_row, base, spec)
