"""仲裁决策矩阵测试：R018/R019/R025/R031 全路径 + 弃权 + 不静默覆盖。"""
from __future__ import annotations

from geocode_arbiter import POI_HIGH_CONFIDENCE, Record, Verdict, arbitrate
from geocode_arbiter.providers.offline import ScriptedProvider

# 坐标查表（保留 4 位与 offline 匹配）
POS_A = (113.2644, 23.1291)  # 广州天河
POS_B = (113.5000, 23.2000)  # 广州邻区（同一 4 位市码 4401 假设）
TIANHE, HUANGPU = "440106", "440112"


def _rec(**kw) -> Record:
    base = dict(
        outlet_id="O1",
        filled_adcode=TIANHE,
        filled_lon=POS_A[0],
        filled_lat=POS_A[1],
        address="广州市天河区测试路1号",
        poi_confidence=0.9,
        official_adcode=TIANHE,
    )
    base.update(kw)
    return Record(**base)


def test_confirmed_when_both_sources_agree_with_fill():
    pri = ScriptedProvider("tencent", {POS_A: TIANHE})
    sec = ScriptedProvider("amap", {POS_A: TIANHE})
    d = arbitrate(_rec(), pri, sec)
    assert d.verdict is Verdict.CONFIRMED
    assert {"R018", "R019", "R025"} <= set(d.rule_hits)


def test_coord_error_candidate_via_r031_tencent_misreport():
    # 腾讯反解 ≠ 填报, 高德 = 填报, POI 高可信, 官方=填报 → 坐标错(腾讯误报)
    pri = ScriptedProvider("tencent", {POS_A: HUANGPU})
    sec = ScriptedProvider("amap", {POS_A: TIANHE})
    rec = _rec(poi_confidence=0.9, official_adcode=TIANHE)
    d = arbitrate(rec, pri, sec)
    assert d.verdict is Verdict.COORD_ERROR_CANDIDATE
    assert "R031" in d.rule_hits
    assert d.correction is None  # R031 坐标错裁定, 不自动产生修正坐标


def test_coord_error_requires_poi_and_official_agreement():
    pri = ScriptedProvider("tencent", {POS_A: HUANGPU})
    sec = ScriptedProvider("amap", {POS_A: TIANHE})
    rec = _rec(poi_confidence=0.5)  # POI 不可信 → 不敢裁决
    d = arbitrate(rec, pri, sec)
    assert d.verdict is Verdict.MANUAL_REVIEW


def test_amap_divergence_goes_manual_not_silent_confirm():
    # 腾讯=填报 但 高德≠: 单源放行会虚高 hard gate → 人工
    pri = ScriptedProvider("tencent", {POS_A: TIANHE})
    sec = ScriptedProvider("amap", {POS_A: HUANGPU})
    d = arbitrate(_rec(), pri, sec)
    assert d.verdict is Verdict.MANUAL_REVIEW


def test_both_sources_differ_from_fill_with_forward_candidate():
    # 双源一致 ≠ 填报 → R031 + forward 候选落在填报区 → 坐标错候选(带修正)
    table = {POS_A: HUANGPU}
    fwd = {"广州市天河区测试路1号": (POS_B[0], POS_B[1], TIANHE)}
    pri = ScriptedProvider("tencent", table, fwd)
    sec = ScriptedProvider("amap", table)
    d = arbitrate(_rec(), pri, sec)
    assert d.verdict is Verdict.COORD_ERROR_CANDIDATE
    assert d.correction is not None and d.correction.adcode == TIANHE
    assert d.correction_offset_m and d.correction_offset_m > 0


def test_field_error_when_official_agrees_with_candidate():
    table = {POS_A: HUANGPU}
    fwd = {"广州市天河区测试路1号": (POS_B[0], POS_B[1], HUANGPU)}
    pri = ScriptedProvider("tencent", table, fwd)
    sec = ScriptedProvider("amap", table)
    rec = _rec(official_adcode=HUANGPU)  # 官方与候选一致而与填报不一致 → 字段错
    d = arbitrate(rec, pri, sec)
    assert d.verdict is Verdict.FIELD_ERROR_CANDIDATE


def test_provider_failure_abstains_and_preserves_record():
    pri = ScriptedProvider("tencent", {}, fail=True)
    sec = ScriptedProvider("amap", {POS_A: TIANHE})
    d = arbitrate(_rec(), pri, sec)
    assert d.verdict is Verdict.ABSTAIN
    assert d.evidence["primary"]["abstain"] == "scripted_failure"
    assert d.correction is None


def test_original_coordinates_never_overwritten_in_any_verdict():
    # 不变量：任何裁决的 Decision 都不携带等于"静默替换"的语义——
    # correction 只在 COORD/FIELD 候选出现且必须带 offset 与来源。
    rec = _rec()
    for t_code, a_code in [(TIANHE, TIANHE), (HUANGPU, TIANHE), (TIANHE, HUANGPU), (HUANGPU, HUANGPU)]:
        pri = ScriptedProvider("tencent", {POS_A: t_code})
        sec = ScriptedProvider("amap", {POS_A: a_code})
        d = arbitrate(rec, pri, sec)
        assert d.to_json()["evidence"]["filled_adcode"] == rec.filled_adcode


def test_poi_high_confidence_constant():
    assert POI_HIGH_CONFIDENCE == 0.80
