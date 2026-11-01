#!/usr/bin/env python3
# build_ics.py — 从 data.json 生成 calendar.ics（全量订阅）与 milestones.ics（关键里程碑单次导入）
# 仅用 Python3 标准库。用法：python3 build_ics.py
import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))

LMP_OFFSET_FROM_CONCEPTION = -14   # 受孕日 ≈ 末次月经 + 14 天
DUE_OFFSET_FROM_LMP = 280          # 预产期 = 末次月经 + 280 天


def add_months(d: date, months: int) -> date:
    """日历月加减（dateutil 语义）：月底溢出时钳制到目标月最后一天。"""
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    m += 1
    # 目标月天数
    if m == 12:
        next_month = date(y + 1, 1, 1)
    else:
        next_month = date(y, m + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day))


def resolve_anchors(data):
    a = data["anchor"]
    d = date.fromisoformat(a["date"])
    t = a["type"]
    if t == "conception":
        con = d
        lmp = d + timedelta(days=LMP_OFFSET_FROM_CONCEPTION)
    elif t == "lmp":
        lmp = d
        con = d - timedelta(days=LMP_OFFSET_FROM_CONCEPTION)
    elif t == "dueDate":
        due = d
        lmp = due - timedelta(days=DUE_OFFSET_FROM_LMP)
        con = lmp - timedelta(days=LMP_OFFSET_FROM_CONCEPTION)
        return {"lmp": lmp, "con": con, "due": due}
    else:
        raise ValueError(f"未知锚点类型: {t}")
    due = lmp + timedelta(days=DUE_OFFSET_FROM_LMP)
    return {"lmp": lmp, "con": con, "due": due}


ATOM = re.compile(r"^(lmp|con|due)([+-])(\d+)([DWM])$")


def parse_atom(s: str, anchors) -> date:
    m = ATOM.match(s.strip())
    if not m:
        raise ValueError(f"无法解析规则片段: {s!r}")
    ref, sign, n, unit = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    base = anchors[ref]
    n = n if sign == "+" else -n
    if unit == "D":
        return base + timedelta(days=n)
    if unit == "W":
        return base + timedelta(weeks=n)
    if unit == "M":
        return add_months(base, n)
    raise ValueError(unit)


def parse_rule(rule: str, anchors):
    """返回 (start_date, end_date|None)。区间形如 lmp+0W..due+0W。"""
    if ".." in rule:
        a, b = rule.split("..", 1)
        return parse_atom(a, anchors), parse_atom(b, anchors)
    return parse_atom(rule, anchors), None


# ---------- ICS 输出 ----------

def esc(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> bytes:
    """按 75 字节折行，不切断 UTF-8 多字节字符，续行以空格开头。"""
    raw = line.encode("utf-8")
    out = []
    first = True
    limit = 75
    while len(raw) > limit:
        cut = limit
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # 避免切断多字节字符
            cut -= 1
        out.append(raw[:cut])
        raw = raw[cut:]
        limit = 74  # 续行前导空格占 1 字节
        first = False
    out.append(raw)
    return b"\r\n ".join(out)


def fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def build_event(item, anchors, dtstamp: str) -> bytes:
    start, end = parse_rule(item["rule"], anchors)
    lines = ["BEGIN:VEVENT"]
    uid = f"{item['id']}@daopai"
    lines.append(f"UID:{uid}")
    lines.append(f"DTSTAMP:{dtstamp}")
    lines.append(f"DTSTART;VALUE=DATE:{fmt_date(start)}")
    if end:  # 区间事件延伸到结束日次日（DTEND 独占）
        lines.append(f"DTEND;VALUE=DATE:{fmt_date(end + timedelta(days=1))}")
    lines.append(f"SUMMARY:{esc(item['title'])}")
    desc_parts = []
    if item.get("note"):
        desc_parts.append(item["note"])
    if end:
        desc_parts.append(f"持续至 {end.isoformat()}")
    r = item.get("remind", {})
    if r.get("enabled") and r.get("time"):
        desc_parts.append(f"建议提醒时间 {r['time']}（全天事件，以系统默认提醒为准）")
    desc_parts.append(f"规则: {item['rule']}")
    lines.append(f"DESCRIPTION:{esc(chr(10).join(desc_parts))}")
    lines.append(f"CATEGORIES:{esc('备孕生产倒排表')}")
    if r.get("enabled"):
        days = int(r.get("daysBefore", 0))
        lines.append("BEGIN:VALARM")
        lines.append("ACTION:DISPLAY")
        if days > 0:
            lines.append(f"TRIGGER:-P{days}D")
        else:
            lines.append("TRIGGER;VALUE=DATE-TIME:" + fmt_date(start) + "T090000")
        lines.append(f"DESCRIPTION:{esc(item['title'])}")
        lines.append("END:VALARM")
    lines.append("END:VEVENT")
    return b"\r\n".join(fold(l) for l in lines)


def build_calendar(items, anchors, calname: str) -> bytes:
    dtstamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    head = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//daopai//pregnancy-countdown//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(calname)}",
        "X-PUBLISHED-TTL:PT1H",
    ]
    tail = ["END:VCALENDAR"]
    body = [build_event(it, anchors, dtstamp) for it in items if it.get("status", "active") == "active"]
    out = b"\r\n".join(fold(l) for l in head) + b"\r\n" + b"\r\n".join(body) + b"\r\n" + b"\r\n".join(fold(l) for l in tail) + b"\r\n"
    return out


def main():
    anchors = resolve_anchors(DATA)
    items = DATA["items"]
    print(f"锚点换算: 末次月经 LMP={anchors['lmp']}  受孕日={anchors['con']}  预产期={anchors['due']}")
    for it in items:
        s, e = parse_rule(it["rule"], anchors)
        rng = f" .. {e}" if e else ""
        print(f"  {it['id']}  {it['title']:<24}  {s}{rng}")

    cal_all = build_calendar(items, anchors, "备孕生产倒排表")
    (BASE / "calendar.ics").write_bytes(cal_all)
    milestones = [it for it in items if it.get("milestone")]
    cal_ms = build_calendar(milestones, anchors, "备孕生产·关键里程碑")
    (BASE / "milestones.ics").write_bytes(cal_ms)
    print(f"已生成 calendar.ics（{len([i for i in items if i.get('status','active')=='active'])} 条）"
          f" 与 milestones.ics（{len(milestones)} 条）")


if __name__ == "__main__":
    main()
