"""Provider 抽象：可插拔地理编码源。

契约（WP04，潜店雷达模块①整合计划）：
- forward(address, adcode_hint) -> Candidate | AbstainResult
- reverse(lon, lat) -> ReverseResult | AbstainResult

铁律：
1. 任何 provider 失败/超时/不可解析 = 弃权（ABSTAIN），绝不抛异常污染仲裁，
   绝不返回编造值。
2. Candidate 必须携带 source、precision、raw_confidence（provider 原始置信，
   仲裁层不做二次打折，也不把分数当授权）。
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Candidate:
    """forward 结果候选。"""

    lon: float
    lat: float
    adcode: str  # 可能空：provider 未返回行政区
    precision: str  # provider 原话，如 "POI" / "门址" / "区县"
    confidence: Optional[float]  # provider 原始置信分（若有），无则 None
    source: str  # "amap" / "tencent" / ...
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ReverseResult:
    """reverse 结果。"""

    adcode: str
    district: str  # 区县级名称，可空
    precision: str
    confidence: Optional[float]
    source: str
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class AbstainResult:
    """弃权：provider 层失败、不可解析或证据不足。

    仲裁层据此走 abstain 路径，不静默覆盖任何坐标。
    """

    source: str
    reason: str
    raw: dict = field(default_factory=dict, repr=False)


Result = Any  # Candidate | ReverseResult | AbstainResult


class Provider:
    """Provider 协议基类。子类实现 forward/reverse。"""

    name = "base"

    def forward(self, address: str, adcode_hint: str = "") -> Result:
        raise NotImplementedError

    def reverse(self, lon: float, lat: float) -> Result:
        raise NotImplementedError

    # ---- 供 HTTP provider 共用的最小工具（stdlib only）----
    @staticmethod
    def _http_get_json(url: str, params: dict, timeout: float = 5.0) -> dict:
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": "geocode-arbiter/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json

            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _key(env_name: str) -> str:
        """API key 只从环境取；缺失返回空串（子类据此弃权，不猜 key）。"""
        return os.environ.get(env_name, "").strip()
