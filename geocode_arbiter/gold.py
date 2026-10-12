"""金标数据集（≥500 条人工金标）schema 与校验。

金标由治理负责人+业务方标注（WP04 组织任务，不计工程人日）。
格式：CSV/JSONL，字段见 GOLD_FIELDS。校验 fail-closed：任何缺字段/
坐标越界/adcode 非法 → 列出全部问题行，不裁剪静默通过。
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

GOLD_FIELDS = [
    "outlet_id",        # 主数据唯一 ID
    "address",          # 填报地址原文
    "filled_adcode",    # 填报区县 adcode（6 位数字）
    "filled_lon",       # 填报坐标（GCJ-02，业务包标准帧）
    "filled_lat",
    "gold_lon",         # 人工金标坐标（GCJ-02）
    "gold_lat",
    "gold_adcode",      # 人工核定的真实区县 adcode
    "poi_confidence",   # 0-1，主数据 POI 匹配可信度
    "official_adcode",  # 官方侧 adcode（可空）
    "annotator",        # 标注人
    "notes",
]

_ADC_RE = re.compile(r"^\d{6}$")


@dataclass
class GoldIssue:
    line_no: int
    outlet_id: str
    problem: str


def validate_gold(path: str | Path) -> tuple[list[dict], list[GoldIssue]]:
    """读金标并全量校验。返回 (rows, issues)；issues 非空即不可用。"""
    p = Path(path)
    rows: list[dict] = []
    issues: list[GoldIssue] = []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [f for f in GOLD_FIELDS if f not in (reader.fieldnames or [])]
        if missing:
            issues.append(GoldIssue(0, "-", f"缺字段: {missing}"))
            return rows, issues
        for i, raw in enumerate(reader, start=2):
            oid = raw.get("outlet_id", "")
            try:
                lon_f, lat_f = float(raw["filled_lon"]), float(raw["filled_lat"])
                lon_g, lat_g = float(raw["gold_lon"]), float(raw["gold_lat"])
                if not (73 <= lon_f <= 136 and 3 <= lat_f <= 54):
                    issues.append(GoldIssue(i, oid, "filled 坐标越界（中国大陆外）"))
                if not (73 <= lon_g <= 136 and 3 <= lat_g <= 54):
                    issues.append(GoldIssue(i, oid, "gold 坐标越界"))
                if not _ADC_RE.match(raw["filled_adcode"]):
                    issues.append(GoldIssue(i, oid, "filled_adcode 非 6 位"))
                if not _ADC_RE.match(raw["gold_adcode"]):
                    issues.append(GoldIssue(i, oid, "gold_adcode 非 6 位"))
                pc = float(raw["poi_confidence"])
                if not 0.0 <= pc <= 1.0:
                    issues.append(GoldIssue(i, oid, "poi_confidence 出 0-1"))
            except (KeyError, ValueError) as exc:
                issues.append(GoldIssue(i, oid, f"数值字段缺失/非法: {exc}"))
                continue
            rows.append({k: raw.get(k, "") for k in GOLD_FIELDS})
    ids = [r["outlet_id"] for r in rows]
    dup = {x for x in ids if ids.count(x) > 1}
    for d in dup:
        issues.append(GoldIssue(0, d, "outlet_id 重复"))
    return rows, issues


def load_gold_jsonl(path: str | Path) -> list[dict]:
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
