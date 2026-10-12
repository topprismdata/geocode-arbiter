# geocode-arbiter

地理编码仲裁层（潜店雷达模块① 整合计划 WP04）。先落仲裁框架，provider 盲测选型并行。

## 规则落地（GeoGov dq_rules_v1_frozen）

| 规则 | 语义 | 阈值 | hard gate |
|---|---|---|---|
| R018 | 填报区县 = 腾讯坐标反解 adcode | 0.98 | ✔ |
| R019 | 填报区县 = 高德坐标反解 adcode（独立第二源） | 0.98 | — |
| R025 | 腾讯反解 = 高德反解（双源互证） | 0.99 | — |
| R031 | 跨源裁决：POI 高可信(≥0.80) 且 官方adcode=填报 → 裁坐标错（非字段错） | 过程留痕 | — |

## 裁决输出（五态，全部留痕）

- `CONFIRMED` 双源与填报一致
- `COORD_ERROR` 坐标错候选（R031 裁定或双源互证+forward 落填报区；带修正候选+偏移米数，采纳可撤销）
- `FIELD_ERROR` 字段错候选（官方 adcode 与候选一致而与填报不一致）
- `MANUAL_REVIEW` 双源分歧 → 人工裁决队列，**绝不静默覆盖**
- `ABSTAIN` provider 失败/证据不足 → 补采队列，不伪造结论

铁律：任何裁决不修改原坐标；修正只是候选，回滚路径=撤销采纳保留原坐标（WP04 风险表）。

## 用法

```bash
pip install -e .
export AMAP_KEY=... TENCENT_KEY=...   # 缺失则全弃权（dry-run 安全）
geocode-arbiter validate-gold --gold data/gold.csv
geocode-arbiter arbitrate --records outlets.jsonl --out decisions.jsonl
geocode-arbiter report --decisions decisions.jsonl > report.md
```

## 金标（≥500 条，组织任务）

schema 见 `data/gold_template.csv`；`validate-gold` fail-closed：缺字段/越界/
adcode 非法/重复 ID 全部列出，不静默裁剪。标注由治理负责人+业务方承担。

## 依赖

- `coords-core @ v0.1.0`（坐标帧纪律与 haversine；本包不实现任何坐标转换）
- live provider（高德/腾讯）行为待盲测验收；单测全部走确定性 mock，不联网
