"""CLI: arbitrate / validate-gold / report。

- arbitrate: 读 JSONL 记录文件, 双 provider 仲裁, 输出 JSONL 决策留痕
- validate-gold: 金标 CSV fail-closed 校验
- report: 由决策 JSONL 生成达成率+误差分布 markdown

live provider 需要 AMAP_KEY / TENCENT_KEY 环境变量; 缺失时全部弃权,
可用于 dry-run 检查输入管道。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from geocode_arbiter.arbiter import Record, arbitrate
from geocode_arbiter.gold import validate_gold
from geocode_arbiter.metrics import report_markdown
from geocode_arbiter.providers.amap import AmapProvider
from geocode_arbiter.providers.tencent import TencentProvider


def _load_records(path: str) -> list[Record]:
    out = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(Record(
            outlet_id=d["outlet_id"],
            filled_adcode=d["filled_adcode"],
            filled_lon=float(d["filled_lon"]),
            filled_lat=float(d["filled_lat"]),
            address=d.get("address", ""),
            poi_confidence=float(d.get("poi_confidence", 0.0)),
            official_adcode=d.get("official_adcode", ""),
        ))
    return out


def cmd_arbitrate(args: argparse.Namespace) -> int:
    recs = _load_records(args.records)
    pri = TencentProvider()
    sec = AmapProvider()
    with Path(args.out).open("w", encoding="utf-8") as fh:
        for rec in recs:
            fh.write(json.dumps(arbitrate(rec, pri, sec).to_json(), ensure_ascii=False) + "\n")
    print(f"arbitrated {len(recs)} records -> {args.out}", file=sys.stderr)
    return 0


def cmd_validate_gold(args: argparse.Namespace) -> int:
    rows, issues = validate_gold(args.gold)
    if issues:
        for i in issues:
            print(f"line {i.line_no} [{i.outlet_id}] {i.problem}", file=sys.stderr)
        print(f"INVALID: {len(issues)} issue(s)", file=sys.stderr)
        return 1
    print(f"valid: {len(rows)} rows", file=sys.stderr)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from geocode_arbiter.arbiter import Decision, Verdict

    ds = []
    for line in Path(args.decisions).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            ds.append(Decision(
                outlet_id=d["outlet_id"],
                verdict=Verdict(d["verdict"]),
                rule_hits=d["rule_hits"],
                evidence=d["evidence"],
                correction_offset_m=d.get("correction_offset_m"),
            ))
    print(report_markdown(ds))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="geocode-arbiter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("arbitrate", help="双源仲裁记录(JSONL)")
    p1.add_argument("--records", required=True)
    p1.add_argument("--out", required=True)
    p1.set_defaults(fn=cmd_arbitrate)
    p2 = sub.add_parser("validate-gold", help="金标 CSV 校验")
    p2.add_argument("--gold", required=True)
    p2.set_defaults(fn=cmd_validate_gold)
    p3 = sub.add_parser("report", help="决策 JSONL -> 报告")
    p3.add_argument("--decisions", required=True)
    p3.set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
