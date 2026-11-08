# -*- coding: utf-8 -*-
"""导出与自动备份（v1.9.9.20）

用户反馈：数据只存本机，没有导出/备份入口，换电脑或硬盘坏就全丢。

三个出口：
  - JSON：完整备份（tasks + history + 设置），可原样拷回来；
  - Markdown：人能读的归档，按天分节、勾选状态、完成率一览；
  - ICS：标准日历文件，可直接导入系统日历 / 手机。

自动备份：每天首次保存时做一次快照，保留最近 7 天（backup/ 目录）。
"""
import datetime as dt
import json
import os
import shutil

KEEP_DAYS = 7


# ---------------------------------------------------------------- 备份
def backup_dir(base_dir):
    return os.path.join(base_dir, "backup")


def auto_snapshot(base_dir, files, keep=KEEP_DAYS, today=None, force=False):
    """把 files 拷进 backup/YYYY-MM-DD/，并清掉超过 keep 天的旧快照。

    files: 形如 [("tasks.json", 绝对路径), ...]；不存在的跳过。
    返回快照目录名（没做事返回 None）。

    v1.9.9.45：默认改为**每次保存前覆盖当天快照**（force=True）。
    旧版「同一天只做一次」的结果是：备份停在当天开机那一刻，用户记了
    一整天 23 条任务，备份里还是早上那 704 字节的空壳，等于没有备份。
    """
    day = (today or dt.date.today()).isoformat()
    root = backup_dir(base_dir)
    target = os.path.join(root, day)
    if os.path.isdir(target) and not force:
        return None                      # 今天已经快照过（兼容旧调用）
    try:
        os.makedirs(target, exist_ok=True)
        copied = False
        for name, path in files:
            if path and os.path.exists(path):
                shutil.copy2(path, os.path.join(target, name))
                copied = True
        if not copied:
            try:
                os.rmdir(target)
            except Exception:
                pass
            return None
        _prune(root, keep)
        return day
    except Exception:
        return None


def _prune(root, keep):
    """只留最近的 keep 个快照目录（按目录名 = 日期排序）"""
    try:
        names = sorted(n for n in os.listdir(root)
                       if os.path.isdir(os.path.join(root, n)))
        for n in names[:-keep] if len(names) > keep else []:
            shutil.rmtree(os.path.join(root, n), ignore_errors=True)
    except Exception:
        pass


def list_snapshots(base_dir):
    root = backup_dir(base_dir)
    if not os.path.isdir(root):
        return []
    return sorted((n for n in os.listdir(root)
                   if os.path.isdir(os.path.join(root, n))), reverse=True)


# ---------------------------------------------------------------- 导出
def to_json(tasks, history, settings=None, messages=None):
    """完整备份。v1.9.9.45：补上 messages——对话记录也是用户数据，
    旧版导出里没有，换机恢复后聊天全空。"""
    obj = {
        "app": "每日记事本",
        "exported_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": tasks or [],
        "history": history or {},
        "settings": settings or {},
        "messages": messages or [],
    }
    return json.dumps(obj, ensure_ascii=False, indent=2)


def to_markdown(tasks, history, title="每日记事本 · 导出"):
    """按天归档：今天用 tasks，其余用 history"""
    lines = ["# " + title, ""]
    days = dict(history or {})
    today = dt.date.today().isoformat()
    if tasks:
        days[today] = tasks
    if not days:
        lines.append("_（还没有任何记录）_")
        return "\n".join(lines) + "\n"

    total_all = done_all = 0
    for day in sorted(days.keys(), reverse=True):
        rows = days.get(day) or []
        if not rows:
            continue
        done = sum(1 for r in rows if r.get("done"))
        total_all += len(rows)
        done_all += done
        label = _day_label(day, today)
        lines.append("## %s  ·  %d/%d" % (label, done, len(rows)))
        lines.append("")
        for r in rows:
            mark = "x" if r.get("done") else " "
            bits = []
            # v1.9.9.51：补优先级。旧版导出只有标题/时间，用户做的
            # 分档信息在归档里彻底丢失（用户实测对比过 JSON 与 MD）。
            try:
                _pl = _prio_label(r.get("score"))
                if _pl:
                    bits.append(_pl)
            except Exception:
                pass
            if r.get("hhmm"):
                bits.append(r["hhmm"])
            if r.get("dur"):
                bits.append(r["dur"])
            if r.get("done_at"):
                bits.append("完成于 %s" % r["done_at"])
            tail = ("  `%s`" % " · ".join(bits)) if bits else ""
            lines.append("- [%s] %s%s" % (mark, r.get("title", ""), tail))
        lines.append("")
    if total_all:
        rate = int(round(done_all * 100.0 / total_all))
        lines.insert(1, "")
        lines.insert(2, "> 共 %d 天 · %d 件任务 · 完成率 %d%%" %
                     (len([d for d in days if days[d]]), total_all, rate))
        lines.insert(3, "")
    return "\n".join(lines) + "\n"


def _prio_label(score):
    """优先级档位文案（与界面同一套文案，导出是中英双语的）"""
    try:
        score = float(score if score is not None else 0)
    except (TypeError, ValueError):
        return ""
    try:
        from i18n import t as _t
        labels = _t("prio")
    except Exception:
        labels = ["紧急", "重要", "一般", "不急"]
    if score >= 75:
        return labels[0]
    if score >= 55:
        return labels[1]
    if score >= 35:
        return labels[2]
    return labels[3]


def _day_label(day, today):
    try:
        d = dt.date.fromisoformat(day)
        delta = (dt.date.fromisoformat(today) - d).days
        base = "%d月%d日" % (d.month, d.day)
        if delta == 0:
            return base + "（今天）"
        if delta == 1:
            return base + "（昨天）"
        return base
    except Exception:
        return day


def _ics_escape(s):
    """v1.9.9.45：补上 \\r（Outlook/系统日历对裸 CR 会解析失败）"""
    return (s or "").replace("\\", "\\\\").replace(",", "\\,") \
                    .replace(";", "\\;").replace("\r\n", "\\n") \
                    .replace("\r", "\\n").replace("\n", "\\n")


def _fold(line, limit=75):
    """ICS 规定单行不超过 75 字节，超出要用「空格+续行」折行。
    中文标题很容易超；不折行时部分客户端会截断或整条丢弃。"""
    out = []
    cur = ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > limit:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return out


def to_ics(tasks, history, stamp=None):
    """生成 ICS 日历。有 hhmm 的任务做成定时事件（1 小时），
    没有时间的做成全天事件。"""
    now = (stamp or dt.datetime.utcnow()).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//DailyNotebook//CN", "CALSCALE:GREGORIAN"]
    days = dict(history or {})
    days[dt.date.today().isoformat()] = (tasks or [])
    n = 0
    for day in sorted(days.keys()):
        try:
            d = dt.date.fromisoformat(day)
        except Exception:
            continue
        for r in days.get(day) or []:
            title = (r.get("title") or "").strip()
            if not title:
                continue
            n += 1
            uid = "dn-%s-%d@localhost" % (day.replace("-", ""), n)
            out += ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + now]
            hhmm = r.get("hhmm") or ""
            start = None
            if ":" in hhmm:
                try:
                    hh, mm = hhmm.split(":")[:2]
                    start = dt.datetime.combine(
                        d, dt.time(int(hh), int(mm[:2])))
                except Exception:
                    start = None
            if start:
                end = start + dt.timedelta(hours=1)
                out.append("DTSTART:" + start.strftime("%Y%m%dT%H%M%S"))
                out.append("DTEND:" + end.strftime("%Y%m%dT%H%M%S"))
            else:
                out.append("DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"))
            status = ("STATUS:COMPLETED" if r.get("done")
                      else "STATUS:CONFIRMED")
            out += ["SUMMARY:" + _ics_escape(title),
                    "DESCRIPTION:" + _ics_escape(
                        ("优先级 " + str(r.get("score", ""))) if r.get("score")
                        else ""),
                    status, "END:VEVENT"]
    out.append("END:VCALENDAR")
    folded = []
    for ln in out:
        folded.extend(_fold(ln))
    return "\r\n".join(folded) + "\r\n"


def safe_name(s):
    """文件名里的非法字符替换掉"""
    bad = '\\/:*?"<>|'
    for c in bad:
        s = s.replace(c, "_")
    return s.strip() or "export"
