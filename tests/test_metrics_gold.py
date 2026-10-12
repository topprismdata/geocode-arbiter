"""指标与金标校验测试。"""
from __future__ import annotations

import pytest

from geocode_arbiter import Decision, Record, Verdict, arbitrate
from geocode_arbiter.gold import GoldIssue, validate_gold
from geocode_arbiter.metrics import batch_rates, error_distribution, report_markdown, verdict_summary
from geocode_arbiter.providers.offline import ScriptedProvider

TIANHE, HUANGPU = "440106", "440112"
POS_A = (113.2644, 23.1291)


def _d(vid: Verdict, hits: list[str], offset: float | None = None,
       pri_code: str | None = TIANHE, sec_code: str | None = TIANHE) -> Decision:
    return Decision(
        outlet_id="x", verdict=vid, rule_hits=hits,
        evidence={"primary": {"adcode": pri_code}, "secondary": {"adcode": sec_code}},
        correction_offset_m=offset,
    )


def test_batch_rates_denominators_per_rule():
    ds = [
        _d(Verdict.CONFIRMED, ["R018", "R019", "R025"], None, TIANHE, TIANHE),
        _d(Verdict.ABSTAIN, [], None, None, TIANHE),        # 腾讯弃权
        _d(Verdict.MANUAL_REVIEW, ["R031"], None, HUANGPU, TIANHE),
    ]
    rates = batch_rates(ds)
    assert rates["R018"].base == 2 and rates["R018"].agree == 1      # 1/2
    assert rates["R019"].base == 3 and rates["R019"].agree == 1      # 1/3
    assert rates["R025"].base == 2 and rates["R025"].agree == 1      # 1/2
    assert rates["R018"].pass_() is False


def test_batch_rates_empty_base_is_none_not_fake_100():
    rates = batch_rates([_d(Verdict.ABSTAIN, [], None, None, None)])
    assert rates["R018"].rate is None and rates["R018"].pass_() is False


def test_error_distribution_percentiles():
    ds = [_d(Verdict.COORD_ERROR_CANDIDATE, ["R031"], off) for off in (100.0, 500.0, 9000.0)]
    dist = error_distribution(ds)
    assert dist["n"] == 3
    assert dist["p50_m"] == 500.0
    assert dist["max_m"] == 9000.0
    assert dist["hist"]["<= 500m"] == 2          # 累计: 100+500
    assert dist["hist"]["<= 10000m"] == 3
    assert dist["hist"]["> 10000m"] == 0


def test_report_markdown_renders():
    md = report_markdown([_d(Verdict.CONFIRMED, ["R018", "R019", "R025"])])
    assert "R018" in md and "CONFIRMED" in md and "修正偏移分布" in md


# ---- gold 校验 ----

def _gold_row(tmp_path, **over):
    row = {
        "outlet_id": "O1", "address": "a", "filled_adcode": "440106",
        "filled_lon": "113.2644", "filled_lat": "23.1291",
        "gold_lon": "113.27", "gold_lat": "23.13", "gold_adcode": "440106",
        "poi_confidence": "0.9", "official_adcode": "", "annotator": "t", "notes": "",
    }
    row.update(over)
    p = tmp_path / "gold.csv"
    import csv
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    return p


def test_gold_valid(tmp_path):
    rows, issues = validate_gold(_gold_row(tmp_path))
    assert issues == [] and len(rows) == 1


def test_gold_rejects_bad_adcode_and_range(tmp_path):
    _, issues = validate_gold(_gold_row(tmp_path, filled_adcode="44x", gold_lat="99"))
    kinds = " | ".join(i.problem for i in issues)
    assert "6 位" in kinds and "越界" in kinds


def test_gold_missing_column_fail_closed(tmp_path):
    import csv
    p = tmp_path / "g.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["outlet_id", "address"])
        w.writerow(["O1", "a"])
    rows, issues = validate_gold(p)
    assert rows == [] and any("缺字段" in i.problem for i in issues)
