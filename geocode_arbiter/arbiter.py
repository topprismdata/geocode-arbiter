"""核心仲裁引擎：R018 / R019 / R025 / R031 落地。

输入：单条门店记录（填报坐标+填报区县+地址）+ 两个 provider。
输出：带全量留痕的裁决 Decision。铁律：
- 任何坐标都不被静默覆盖：CONFIRMED 之外一律保留原坐标；
  候选修正（COORD_ERROR）只是候选，采纳可撤销（回滚路径 WP04）。
- 双源不一致且无法用 R031 规则裁决 → MANUAL_REVIEW 人工队列。
- provider 弃权 → ABSTAIN，证据不足不下结论。

R018 填报区县 = 腾讯坐标反解 adcode（hard gate, threshold 0.98）
R019 填报区县 = 高德坐标反解 adcode（独立第二源, 0.98）
R025 腾讯反解 adcode = 高德反解 adcode（双源互证, 0.99）
R031 腾讯≠填报时: POI 高可信 且 官方adcode=填报 → 裁决坐标错(非字段错)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from coords_core import haversine_m

from geocode_arbiter.providers.base import (
    AbstainResult,
    Candidate,
    Provider,
    ReverseResult,
)


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"                    # 双源反解=填报区县
    COORD_ERROR_CANDIDATE = "COORD_ERROR"      # R031: 坐标错（候选修正，可撤销）
    FIELD_ERROR_CANDIDATE = "FIELD_ERROR"      # 字段错候选（官方 adcode 与填报不符）
    MANUAL_REVIEW = "MANUAL_REVIEW"            # 双源分歧，人工裁决
    ABSTAIN = "ABSTAIN"                        # 证据不足


@dataclass
class Record:
    """待仲裁门店记录。"""

    outlet_id: str
    filled_adcode: str      # 填报区县 adcode（6 位）
    filled_lon: float
    filled_lat: float
    address: str = ""       # 填报地址（forward 修正候选用）
    poi_confidence: float = 0.0  # POI 匹配可信度（0-1，来自主数据/上游）
    official_adcode: str = ""    # 官方侧区县 adcode（如上报道授权值；空=无）

    def official_matches_fill(self) -> bool:
        return bool(self.official_adcode) and self.official_adcode == self.filled_adcode


@dataclass
class Decision:
    """裁决留痕：一切结论带证据，review 队列可审计、可重放。"""

    outlet_id: str
    verdict: Verdict
    rule_hits: list[str]
    evidence: dict[str, Any]
    correction: Optional[Candidate] = None   # 仅 COORD_ERROR 候选携带
    correction_offset_m: Optional[float] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))

    def to_json(self) -> dict:
        return {
            "outlet_id": self.outlet_id,
            "verdict": self.verdict.value,
            "rule_hits": self.rule_hits,
            "evidence": self.evidence,
            "correction": None
            if self.correction is None
            else {
                "lon": self.correction.lon,
                "lat": self.correction.lat,
                "adcode": self.correction.adcode,
                "precision": self.correction.precision,
                "source": self.correction.source,
            },
            "correction_offset_m": self.correction_offset_m,
            "created_at": self.created_at,
        }


# R031 采用候选修正要求的最低 POI 可信度
POI_HIGH_CONFIDENCE = 0.80
# 反解 adcode 与填报 adcode 同城不同区视为"区级不一致"（adcode 前 4 位=市）
def _same_city(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a[:4] == b[:4]


def _rev_adcode(res: Any) -> Optional[str]:
    """从 provider 结果提取反解 adcode；弃权/无 adcode → None。"""
    if isinstance(res, AbstainResult):
        return None
    if isinstance(res, ReverseResult):
        return res.adcode or None
    return None


def arbitrate(rec: Record, primary: Provider, secondary: Provider) -> Decision:
    """对单条记录跑双源仲裁。

    primary = 腾讯（R018 主源），secondary = 高德（R019 独立第二源）。
    """
    rev_pri = primary.reverse(rec.filled_lon, rec.filled_lat)
    rev_sec = secondary.reverse(rec.filled_lon, rec.filled_lat)
    code_pri = _rev_adcode(rev_pri)
    code_sec = _rev_adcode(rev_sec)

    evidence: dict[str, Any] = {
        "filled_adcode": rec.filled_adcode,
        "primary": {"source": primary.name, "adcode": code_pri,
                    "abstain": isinstance(rev_pri, AbstainResult) and rev_pri.reason},
        "secondary": {"source": secondary.name, "adcode": code_sec,
                      "abstain": isinstance(rev_sec, AbstainResult) and rev_sec.reason},
    }

    # 弃权路径：任一源不可用 → 只报 ABSTAIN（除非另一源已给出强结论的场景，
    # WP04 从保守：单源结论不足以触发裁决，全部弃权进补采队列）
    if code_pri is None or code_sec is None:
        return Decision(rec.outlet_id, Verdict.ABSTAIN, [], evidence)

    rule_hits = []
    r018 = code_pri == rec.filled_adcode      # 腾讯反解 = 填报
    r019 = code_sec == rec.filled_adcode      # 高德反解 = 填报
    r025 = code_pri == code_sec               # 双源互证
    if r018:
        rule_hits.append("R018")
    if r019:
        rule_hits.append("R019")
    if r025:
        rule_hits.append("R025")

    if r018 and r019:
        return Decision(rec.outlet_id, Verdict.CONFIRMED, rule_hits, evidence)

    # R025 场景：双源一致但都 ≠ 填报 → 整体位置疑错，但双源互证支持候选
    if r025:
        rule_hits.append("R031")
        cand = primary.forward(rec.address, rec.filled_adcode) if rec.address else None
        if isinstance(cand, AbstainResult) or cand is None:
            # 无地址或 forward 弃权 → 人工
            return Decision(rec.outlet_id, Verdict.MANUAL_REVIEW, rule_hits, evidence)
        offset = haversine_m(rec.filled_lon, rec.filled_lat, cand.lon, cand.lat)
        evidence["forward_candidate"] = {
            "adcode": cand.adcode, "precision": cand.precision, "source": cand.source,
        }
        # 候选落在填报区县 → 坐标错（字段对，位置跑偏）
        if cand.adcode == rec.filled_adcode:
            return Decision(rec.outlet_id, Verdict.COORD_ERROR_CANDIDATE, rule_hits,
                            evidence, cand, offset)
        # 候选落在别的区 & 官方 adcode 与候选一致 → 字段错候选
        if rec.official_matches_fill() is False and rec.official_adcode == cand.adcode:
            return Decision(rec.outlet_id, Verdict.FIELD_ERROR_CANDIDATE, rule_hits,
                            evidence, cand, offset)
        return Decision(rec.outlet_id, Verdict.MANUAL_REVIEW, rule_hits, evidence)

    # 到此 r025 为假：双源反解彼此不一致 → R031 裁决
    rule_hits.append("R031")
    # R031: 腾讯≠填报 且 高德=填报，POI 高可信 且 官方=填报 → 坐标错（腾讯误报）
    if (
        not r018
        and r019
        and rec.poi_confidence >= POI_HIGH_CONFIDENCE
        and rec.official_matches_fill()
    ):
        return Decision(rec.outlet_id, Verdict.COORD_ERROR_CANDIDATE, rule_hits, evidence)
    # 镜像：腾讯=填报 且 高德≠填报 且 官方=填报 → 裁决坐标基本可信，
    # 高德差异记为源分歧；仍不覆盖，留痕进 CONFIRMED_WITH_DIVERGENCE 的简化：
    # 保守起见进人工（避免把 hard gate R018 单源放行）
    if r018 and not r019:
        return Decision(rec.outlet_id, Verdict.MANUAL_REVIEW, rule_hits, evidence)
    # 其余分歧（同城不同区/跨市）→ 人工裁决，绝不静默覆盖
    return Decision(rec.outlet_id, Verdict.MANUAL_REVIEW, rule_hits, evidence)
