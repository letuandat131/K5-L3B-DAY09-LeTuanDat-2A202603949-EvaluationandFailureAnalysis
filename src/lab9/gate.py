"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_bad_number(val: object) -> bool:
    return isinstance(val, float) and (math.isnan(val) or math.isinf(val))


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted."""
    problems: list[str] = []

    for mid, val in (pr.get("metrics") or {}).items():
        if _is_bad_number(val):
            problems.append(f"metric {mid!r} is NaN/Inf")

    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    pr_manifest = pr.get("manifest") or {}
    expected_count = int(pr_manifest.get("items") or 0) * len(pr_manifest.get("seeds") or [])
    if len(pr_rows) != expected_count:
        problems.append(f"row count {len(pr_rows)} != manifest items*seeds ({expected_count})")

    pr_keys_list = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(set(pr_keys_list)) != len(pr_keys_list):
        problems.append("duplicate (item_id, seed) rows in PR")
    pr_keys = set(pr_keys_list)
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if pr_keys != base_keys:
        problems.append(
            f"(item_id, seed) set differs from baseline (missing={len(base_keys - pr_keys)}, extra={len(pr_keys - base_keys)})"
        )

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")

    base_sample = base_rows[0] if base_rows else {}
    row_metrics = [
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or m["id"] in base_sample
    ]
    for idx, r in enumerate(pr_rows):
        for mid in row_metrics:
            val = r.get(mid)
            if val is None or _is_bad_number(val):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} (#{idx}) has missing/NaN {mid}")
                break

    base_slices: dict[str, tuple[str, ...]] = {}
    for r in base_rows:
        iid = r.get("item_id")
        if iid is not None and iid not in base_slices:
            base_slices[iid] = tuple(sorted(r.get("slices") or []))
    for r in pr_rows:
        iid = r.get("item_id")
        if iid in base_slices and tuple(sorted(r.get("slices") or [])) != base_slices[iid]:
            problems.append(f"slice tags mutated for item {iid}")
            break

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        b_metrics = {m["id"]: m for m in (base_spec.get("metrics") or [])}
        p_metrics = {m["id"]: m for m in (spec.get("metrics") or [])}
        for mid, bm in b_metrics.items():
            if mid not in p_metrics:
                problems.append(f"ratchet: metric {mid!r} removed from spec")
                continue
            pm = p_metrics[mid]
            if bm.get("blocking") and not pm.get("blocking"):
                problems.append(f"ratchet: metric {mid!r} changed from blocking to non-blocking")
            bth = bm.get("threshold") or {}
            pth = pm.get("threshold") or {}
            if "min" in bth and ("min" not in pth or pth["min"] < bth["min"]):
                problems.append(f"ratchet: metric {mid!r} min lowered ({bth['min']} -> {pth.get('min')})")
            if "max" in bth and ("max" not in pth or pth["max"] > bth["max"]):
                problems.append(f"ratchet: metric {mid!r} max raised ({bth['max']} -> {pth.get('max')})")
            if "max_increase" in bth and ("max_increase" not in pth or pth["max_increase"] > bth["max_increase"]):
                problems.append(f"ratchet: metric {mid!r} max_increase raised ({bth['max_increase']} -> {pth.get('max_increase')})")
            if bth.get("no_significant_drop") and not pth.get("no_significant_drop"):
                problems.append(f"ratchet: metric {mid!r} dropped no_significant_drop")

        b_slices = {(s["name"], s["metric"]): s for s in (base_spec.get("slices") or [])}
        p_slices = {(s["name"], s["metric"]): s for s in (spec.get("slices") or [])}
        for key, bs in b_slices.items():
            if key not in p_slices:
                problems.append(f"ratchet: slice {key[0]}/{key[1]} removed from spec")
                continue
            ps = p_slices[key]
            if bs.get("blocking") and not ps.get("blocking"):
                problems.append(f"ratchet: slice {key[0]}/{key[1]} changed from blocking to non-blocking")
            if "min" in bs and ("min" not in ps or ps["min"] < bs["min"]):
                problems.append(f"ratchet: slice {key[0]}/{key[1]} min lowered ({bs['min']} -> {ps.get('min')})")
            if "max" in bs and ("max" not in ps or ps["max"] > bs["max"]):
                problems.append(f"ratchet: slice {key[0]}/{key[1]} max raised ({bs['max']} -> {ps.get('max')})")
            if bs.get("no_significant_drop") and not ps.get("no_significant_drop"):
                problems.append(f"ratchet: slice {key[0]}/{key[1]} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): per-slice threshold and paired bootstrap check."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        blocking = bool(s.get("blocking", False))
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        else:
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        sid = f"slice:{name}/{mid}"
        if verdict != "ok" and blocking:
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if blocking else "warn")
        th_view = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<22} {val!s:<8} {json.dumps(th_view):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
