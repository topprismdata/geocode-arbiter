"""腾讯位置服务 provider。

端点：
- forward: /ws/geocoder/v1（地址解析）
- reverse: /ws/geocoder/v1（逆地理解析）

状态机与 amap 同：失败即弃权。live 行为待盲测验收；单测走 mock。
"""
from __future__ import annotations

from geocode_arbiter.providers.base import (
    AbstainResult,
    Candidate,
    Provider,
    Result,
    ReverseResult,
)

WS_URL = "https://apis.map.qq.com/ws/geocoder/v1"


class TencentProvider(Provider):
    name = "tencent"

    def __init__(self, key: str = "", timeout: float = 5.0):
        self._key = key or Provider._key("TENCENT_KEY")
        self._timeout = timeout

    def forward(self, address: str, adcode_hint: str = "") -> Result:
        if not self._key:
            return AbstainResult(self.name, "missing_api_key")
        params = {"key": self._key, "address": address}
        if adcode_hint:
            params["region"] = adcode_hint
        try:
            data = self._http_get_json(WS_URL, params, self._timeout)
        except Exception as exc:  # noqa: BLE001
            return AbstainResult(self.name, f"http_error:{exc.__class__.__name__}")
        if data.get("status") != 0:
            return AbstainResult(self.name, f"api_status:{data.get('status')}", data)
        loc = data.get("result", {}).get("location")
        if not loc:
            return AbstainResult(self.name, "no_result", data)
        comp = data.get("result", {}).get("ad_info") or {}
        return Candidate(
            lon=float(loc["lng"]),
            lat=float(loc["lat"]),
            adcode=str(comp.get("adcode", "")),
            precision=str(data.get("result", {}).get("level", "")),
            confidence=data.get("result", {}).get("reliability"),
            source=self.name,
            raw=data.get("result", {}),
        )

    def reverse(self, lon: float, lat: float) -> Result:
        if not self._key:
            return AbstainResult(self.name, "missing_api_key")
        params = {"key": self._key, "location": f"{lat},{lon}", "get_poi": 0}
        try:
            data = self._http_get_json(WS_URL, params, self._timeout)
        except Exception as exc:  # noqa: BLE001
            return AbstainResult(self.name, f"http_error:{exc.__class__.__name__}")
        if data.get("status") != 0:
            return AbstainResult(self.name, f"api_status:{data.get('status')}", data)
        comp = data.get("result", {}).get("ad_info") or {}
        adcode = str(comp.get("adcode", "") or "")
        if not adcode:
            return AbstainResult(self.name, "no_adcode", data)
        rel = data.get("result", {}).get("reliability")
        return ReverseResult(
            adcode=adcode,
            district=str(comp.get("district", "")),
            precision="adcode",
            confidence=float(rel) / 10.0 if rel is not None else None,  # 腾讯 reliability 1-10
            source=self.name,
            raw=data.get("result", {}),
        )
