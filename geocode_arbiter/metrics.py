"""批次指标：R018/R019/R025 达成率 + 误差分布报告。

口径与 GeoGov dq_rules_v1_frozen.json 一致：
- R018: A=一致记录数, B=腾讯成功反解记录数, threshold 0.98, hard_gate
- R019: 同上对高德, 0.98
- R025: A=一致, B=双源成功, 0.99
误差分布：CONFIRMED 之外带 correction 的裁决，haversine(填报, 候选) 分位数。
"""
from __future__ import annotations

from dataclasses import dataclass

from coords_core import haversine_m

from geocode_arbiter.arbiter import Decision, Verdict

THRESHOLDS = {"R018": 0.98, "R019": 0.98, "R025": 0.99}


@dataclass
class RateResult:
    rule_id: str
    agree: int
    base: int
    rate: float | None  # base=0 → None（不报告假 100%）
    threshold: float

    def pass_(self) -> bool:
        return self.rate is not None and self.rate >= self.threshold

    def to_json(self) -> dict:
        return {
            "rule_id": self.rule_id, "agree": self.agree, "base": self.base,
            "rate": self.rate, "threshold": self.threshold, "pass": self.pass_(),
        }


def batch_rates(decisions: list[Decision]) -> dict[str, RateResult]:
    def base_for(rule: str) -> int:
        # R018 B=腾讯成功反解数; R019 B=高德成功数; R025 B=双源成功数
        pri_ok = sum(1 for d in decisions if d.evidence["primary"].get("adcode"))
        sec_ok = sum(1 for d in decisions if d.evidence["secondary"].get("adcode"))
        both_ok = sum(
            1
            for d in decisions
            if d.evidence["primary"].get("adcode") and d.evidence["secondary"].get("adcode")
        )
        return {"R018": pri_ok, "R019": sec_ok, "R025": both_ok}[rule]

    def stat(rule: str) -> RateResult:
        agree = sum(1 for d in decisions if rule in d.rule_hits)
        base = base_for(rule)
        rate = agree / base if base else None
        return RateResult(rule, agree, base, rate, THRESHOLDS[rule])

    return {r: stat(r) for r in ("R018", "R019", "R025")}


def error_distribution(decisions: list[Decision]) -> dict:
    """correction_offset_m 的分位数与直方（米）。"""
    offsets = sorted(
        d.correction_offset_m
        for d in decisions
        if d.correction_offset_m is not None
    )
    if not offsets:
        return {"n": 0}
    def pct(p: float) -> float:
        i = min(len(offsets) - 1, int(round(p * (len(offsets) - 1))))
        return round(offsets[i], 1)
    buckets = [100, 250, 500, 1000, 3000, 10000]
    # 累计直方：<= X m 表示偏移不超过 X 米的记录数
    hist = {f"<= {b}m": sum(1 for m in offsets if m <= b) for b in buckets}
    hist["> 10000m"] = sum(1 for m in offsets if m > buckets[-1])
    return {
        "n": len(offsets),
        "p50_m": pct(0.50), "p90_m": pct(0.90), "p99_m": pct(0.99),
        "max_m": round(offsets[-1], 1),
        "hist": hist,
    }


def verdict_summary(decisions: list[Decision]) -> dict:
    out: dict[str, int] = {}
    for d in decisions:
        out[d.verdict.value] = out.get(d.verdict.value, 0) + 1
    return out


def report_markdown(decisions: list[Decision]) -> str:
    rates = batch_rates(decisions)
    lines = [
        "# WP04 误差分布与达成率报告（框架自检）",
        "",
        "## 裁决分布",
        "",
        "| verdict | n |",
        "|---|---|",
    ]
    for v, n in verdict_summary(decisions).items():
        lines.append(f"| {v} | {n} |")
    lines += ["", "## 规则达成率", "", "| rule | agree | base | rate | threshold | pass |", "|---|---|---|---|---|---|"]
    for rid, r in rates.items():
        rate = "n/a" if r.rate is None else f"{r.rate:.4f}"
        lines.append(f"| {rid} | {r.agree} | {r.base} | {rate} | {r.threshold} | {r.pass_()} |")
    lines += ["", "## 修正偏移分布", "", "```json", str(error_distribution(decisions)), "```", ""]
    return "\n".join(lines)
