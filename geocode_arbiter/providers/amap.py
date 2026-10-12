"""高德 provider（AMap Web 服务 API）。

端点：
- forward: /v3/geocode/geo（地理编码）
- reverse: /v3/geocode/regeo（逆地理）

状态机：key 缺失、HTTP 失败、status!=1、返回空 → AbstainResult。
live 调用行为未实测（无 key 环境），以盲测选型（WP04 并行任务）验收；
单元测试全部走 offline/mock provider，不依赖本模块联网。
"""
from __future__ import annotations

from geocode_arbiter.providers.base import (
    AbstainResult,
    Candidate,
    Provider,
    ReverseResult,
)

GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"


class AmapProvider(Provider):
    name = "amap"

    def __init__(self, key: str = "", timeout: float = 5.0):
        self._key = key or self._key_env()
        self._timeout = timeout

    @staticmethod
    def _key_env() -> str:
        return Provider._key("AMAP_KEY")

    def forward(self, address: str, adcode_hint: str = "") -> Result:
        if not self._key:
            return AbstainResult(self.name, "missing_api_key")
        params = {"key": self._key, "address": address}
        if adcode_hint:
            params["city"] = adcode_hint
        try:
            data = self._http_get_json(GEO_URL, params, self._timeout)
        except Exception as exc:  # noqa: BLE001 - 任何网络失败都弃权
            return AbstainResult(self.name, f"http_error:{exc.__class__.__name__}")
        if str(data.get("status")) != "1":
            return AbstainResult(self.name, f"api_status:{data.get('status')}", data)
        geos = data.get("geocodes") or []
        if not geos:
            return AbstainResult(self.name, "no_result", data)
        g = geos[0]
        lon, lat = g.get("location", "").split(",")
        return Candidate(
            lon=float(lon),
            lat=float(lat),
            adcode=str(g.get("adcode", "")),
            precision=str(g.get("level", "")),
            confidence=None,
            source=self.name,
            raw=g,
        )

    def reverse(self, lon: float, lat: float) -> Result:
        if not self._key:
            return AbstainResult(self.name, "missing_api_key")
        params = {"key": self._key, "location": f"{lon},{lat}", "extensions": "base"}
        try:
            data = self._http_get_json(REGEO_URL, params, self._timeout)
        except Exception as exc:  # noqa: BLE001
            return AbstainResult(self.name, f"http_error:{exc.__class__.__name__}")
        if str(data.get("status")) != "1":
            return AbstainResult(self.name, f"api_status:{data.get('status')}", data)
        regeo = data.get("regeocode") or {}
        acd = (regeo.get("addressComponent") or {})
        adcode = str(acd.get("adcode", "") or "")
        if not adcode:
            return AbstainResult(self.name, "no_adcode", data)
        return ReverseResult(
            adcode=adcode,
            district=str(acd.get("district", "")),
            precision="adcode",
            confidence=None,
            source=self.name,
            raw=regeo,
        )
