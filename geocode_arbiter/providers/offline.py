"""测试用离线确定性 provider + 脚本化 mock。"""
from __future__ import annotations

from geocode_arbiter.providers.base import (
    AbstainResult,
    Candidate,
    Provider,
    ReverseResult,
    Result,
)


class ScriptedProvider(Provider):
    """按 (lon, lat) 四舍五入查表的确定性 provider；可注入失败。"""

    def __init__(
        self,
        name: str,
        table: dict[tuple[float, float], str],  # 坐标 -> adcode
        forward_table: dict[str, tuple[float, float, str]] | None = None,  # 地址 -> (lon, lat, adcode)
        fail: bool = False,
    ):
        self.name = name
        self._table = table
        self._forward = forward_table or {}
        self._fail = fail

    def reverse(self, lon: float, lat: float) -> Result:
        if self._fail:
            return AbstainResult(self.name, "scripted_failure")
        code = self._table.get((round(lon, 4), round(lat, 4)))
        if code is None:
            return AbstainResult(self.name, "scripted_no_result")
        return ReverseResult(adcode=code, district="", precision="adcode",
                             confidence=1.0, source=self.name)

    def forward(self, address: str, adcode_hint: str = "") -> Result:
        hit = self._forward.get(address)
        if self._fail or hit is None:
            return AbstainResult(self.name, "scripted_no_forward")
        lon, lat, code = hit
        return Candidate(lon=lon, lat=lat, adcode=code, precision="POI",
                         confidence=1.0, source=self.name)
