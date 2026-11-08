# -*- coding: utf-8 -*-
"""
每日记事本 —— 英文任务解析（本地规则，不联网）

与中文解析器能力对齐：
    "meeting at 9am, submit report before 3pm, buy milk"
    -> [("submit report", "15:00", 59), ("meeting", "09:00", 52), ("buy milk", None, 30)]

识别内容：
  时间    9am / 9:30 / at 9 / 3 pm / noon / midnight / morning / afternoon /
          evening / tonight / before 3pm / by 5 / 9 o'clock
  日期    today / tomorrow / day after tomorrow
  重要性  urgent / asap / important / critical / deadline / boss / client /
          interview / exam / doctor / rent / tax ...
  放松词  whenever / maybe / if possible / sometime / later / no rush
"""
import re
import datetime as dt

IMPORTANT = {
    "urgent": 26, "asap": 26, "immediately": 26, "critical": 24,
    "important": 22, "crucial": 24, "vital": 22, "key": 18, "major": 20,
    "deadline": 22, "priority": 18, "must": 18, "have to": 16, "need to": 14,
    "boss": 20, "manager": 18, "client": 18, "customer": 16, "investor": 20,
    "interview": 20, "exam": 22, "test": 14, "presentation": 18, "demo": 16,
    "doctor": 18, "dentist": 18, "hospital": 18, "appointment": 14,
    "rent": 20, "bill": 18, "payment": 18, "invoice": 18, "tax": 20,
    "flight": 18, "train": 16, "visa": 20, "passport": 18, "renew": 16,
    "birthday": 16, "anniversary": 18, "wedding": 18, "school": 14, "kid": 16,
}
RELAX = {
    "whenever": -18, "sometime": -14, "if possible": -18, "maybe": -14,
    "no rush": -20, "not urgent": -22, "later": -12, "eventually": -16,
    "optional": -16, "by the way": -14, "also": -6, "anytime": -12,
}
LEAD = ["i need to", "i have to", "i must", "please", "remember to", "don't forget to",
        "dont forget to", "make sure to", "remind me to", "i should", "gotta", "to"]
TRAIL = ["please", "asap", "today", "tomorrow", "ok", "okay", "thanks"]
NOISE = {"very", "really", "quite", "so", "just", "the", "a", "an", "to", "of",
         "and", "then", "also", "please", "important", "urgent", "must", "need"}

DONE_RE = re.compile(r"\b(done|finished|completed|did|cross(ed)? off|check(ed)? off)\b", re.I)
DEL_RE = re.compile(r"\b(delete|remove|drop|cancel)\b", re.I)
QUERY_RE = re.compile(r"\b(how many|what'?s left|what is left|left|remaining|progress|status)\b", re.I)
GREET_RE = re.compile(r"\b(hi|hello|hey|morning|good morning|evening)\b", re.I)
THANKS_RE = re.compile(r"\b(thanks|thank you|appreciate)\b", re.I)

CLOCK_RE = re.compile(
    r"\b(?:at\s+|by\s+|before\s+|around\s+|@\s*)?"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", re.I)
PERIOD_WORDS = {
    "morning": "09:00", "this morning": "09:00", "afternoon": "15:00",
    "this afternoon": "15:00", "evening": "19:00", "tonight": "20:00",
    "noon": "12:00", "midday": "12:00", "midnight": "00:00",
}
SPLIT_RE = re.compile(r"\s*(?:,|;|\band then\b|\bthen\b|\band\b|\balso\b|\bplus\b)\s*", re.I)


def _norm(s):
    return " " + re.sub(r"\s+", " ", (s or "").strip().lower()) + " "


def find_time(seg):
    """返回 (hhmm, passed, day_offset) 或 (None, False, 0)"""
    text = _norm(seg)
    day_offset = 0
    if "day after tomorrow" in text:
        day_offset = 2
    elif "tomorrow" in text:
        day_offset = 1
    elif "today" in text or "tonight" in text:
        day_offset = 0
    # v1.9.9.51：next / this + 星期几、next week。
    # 旧版只认 today/tomorrow/day after tomorrow，`review next monday 9am`
    # 的日期被彻底丢掉（due_date=None），下午测试时 already-passed 判定
    # 还会误触发「时间已过，还要加吗」。中文侧一直支持「下周一」。
    if not day_offset:
        _WD = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6}
        _WD_PAT = "|".join(_WD)
        # v1.9.9.52：裸星期几也要认（"pay bill on friday"）。旧版只认
        # next/this/coming + 星期，用户只说 "on friday" 时日期整个丢失，
        # 任务被当成「今天」，晚上录入还会被追问「时间已过还加吗」。
        # 但 every/each + 星期是**周期**任务，不能塞「某一天」，
        # 否则和中文侧「周期任务不带 due_date」的规则冲突。
        if re.search(r"\b(?:every|each)\s+(?:single\s+)?(?:%s)s?\b" % _WD_PAT, text):
            pass
        else:
            _m = re.search(r"\b(?:(next|this|coming)\s+)?(%s)\b" % _WD_PAT, text)
            if _m:
                _mode, _wd = (_m.group(1) or ""), _WD[_m.group(2)]
                _today_wd = dt.date.today().weekday()
                _delta = (_wd - _today_wd) % 7      # 本周内，已过则顺延
                if _mode == "next" and _delta == 0:
                    _delta = 7                      # next monday 不含今天
                day_offset = _delta
            elif re.search(r"\bnext\s+week\b", text):
                day_offset = 7
            elif re.search(r"\bweekend\b", text):
                day_offset = (5 - dt.date.today().weekday()) % 7   # 本周六，已过则下周六

    now = dt.datetime.now()
    hhmm = None

    for w, h in PERIOD_WORDS.items():
        if re.search(r"\b" + re.escape(w) + r"\b", text):
            hhmm = h
            break

    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        ap = (m.group(3) or "").lower().replace(".", "")
        looks_like_time = bool(m.group(2) or ap) or re.search(
            r"\b(at|by|before|around|@)\s*" + re.escape(m.group(1)), text) is not None
        if looks_like_time and 0 <= h <= 24 and mi < 60:
            if ap == "pm" and h < 12:
                h += 12
            elif ap == "am" and h == 12:
                h = 0
            elif not ap and h <= 7:
                # "at 3" 这种没说上下午的，按工作时间往后推
                h = h if h >= 8 else h + 12
            hhmm = "%02d:%02d" % (min(h, 23), mi)

    if hhmm is None:
        return None, False, day_offset
    passed = day_offset > 0 or (int(hhmm[:2]) * 60 + int(hhmm[3:])) < (now.hour * 60 + now.minute)
    return hhmm, passed, day_offset


def score(title, raw, hhmm, passed=False, day_offset=0):
    text = _norm(raw)
    s = 30.0
    imp = max([v for k, v in IMPORTANT.items() if k in text] or [0])
    s += imp * 0.9
    urg = max([v for k, v in RELAX.items() if k in text] or [0])
    s += urg
    if day_offset == 1:
        s -= 10
    elif day_offset >= 2:
        s -= 18
    if hhmm:
        now = dt.datetime.now()
        mins = int(hhmm[:2]) * 60 + int(hhmm[3:]) - (now.hour * 60 + now.minute)
        if passed:
            s -= 8
        for lim, add in ((30, 34), (60, 30), (120, 26), (180, 20), (360, 14), (600, 9)):
            if mins <= lim:
                s += add
                break
        else:
            s += 4
    return max(0, min(100, round(s)))


def clean(seg):
    """把时间/前导词/语气词从片段里剥掉，留任务标题"""
    t = " " + (seg or "").strip() + " "
    # 去掉时间表达
    t = re.sub(r"\b(at|by|before|around|@)\s*\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.)?\b",
               " ", t, flags=re.I)
    t = re.sub(r"\b(at|by|before|around|@)\s*(noon|midday|midnight|morning|afternoon|evening|night)\b",
               " ", t, flags=re.I)
    t = re.sub(r"\b\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.)\b", " ", t, flags=re.I)
    t = re.sub(r"\b(today|tomorrow|day after tomorrow|tonight|this morning|this afternoon|"
               r"this evening|morning|afternoon|evening|noon|midday|midnight)\b", " ", t, flags=re.I)
    # v1.9.9.51：相对星期（next monday / this friday / next week）也算时间表达，
    # 旧版不认识就把它们留在标题里，成了「review next Monday」这种半截任务名
    # v1.9.9.52：裸星期几同样要剥（"dinner sunday" -> "dinner"），
    # 否则标题里挂着星期，用户得自己删。
    t = re.sub(r"\b(?:(?:next|this|coming|on|every|each)\s+(?:single\s+)?)?"
               r"(monday|tuesday|wednesday|thursday|friday|"
               r"saturday|sunday)\b", " ", t, flags=re.I)
    t = re.sub(r"\b(next|this|coming|on)\s+(week|weekend)\b", " ", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2})\s*o'?clock\b", " ", t, flags=re.I)
    # 时长（for 15 min / 2 hours）：不进标题，只作次要信息
    t = re.sub(r"\b(for|in|within|about|around)\s+\d{1,3}\s*"
               r"(min|mins|minutes?|h|hr|hrs|hours?)\b", " ", t, flags=re.I)
    t = re.sub(r"\b\d{1,3}\s*(min|mins|minutes?|h|hr|hrs|hours?)\b", " ", t, flags=re.I)
    # 语气/优先级副词
    t = re.sub(r"\b(whenever|sometime|if possible|no rush|not urgent|eventually|anytime|"
               r"by the way|very|really|quite|just|asap|urgent|important|crucial|vital|"
               r"immediately|right away)\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:-")

    changed = True
    rounds = 0
    while changed and rounds < 4:
        changed = False
        rounds += 1
        low = t.lower()
        for w in LEAD:
            if low.startswith(w + " "):
                t = t[len(w):].strip()
                low = t.lower()
                changed = True
        for w in TRAIL:
            if low.endswith(" " + w):
                t = t[:-(len(w) + 1)].strip()
                low = t.lower()
                changed = True
    t = re.sub(r"^[\s:：\-—*·]+", "", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:-")
    return t


def _is_noise(title):
    words = [w for w in re.split(r"[^A-Za-z0-9']+", title.lower()) if w]
    real = [w for w in words if w not in NOISE and w not in RELAX]
    return len(" ".join(real)) < 3


def split_segments(text):
    out = []
    for part in SPLIT_RE.split(text or ""):
        part = (part or "").strip(" ,.;")
        if not part:
            continue
        # "meeting at 9 and report at 3" 已被 and 切开
        marks = list(re.finditer(r"\b(?:at|by|before|around)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?",
                                 part, re.I))
        if len(marks) >= 2:
            cut = [0] + [m.start() for m in marks[1:]] + [len(part)]
            for i in range(len(cut) - 1):
                piece = part[cut[i]:cut[i + 1]].strip(" ,.;")
                if piece:
                    out.append(piece)
            continue
        out.append(part)
    return out


EMPH_RE = None


def _is_emphasis(seg):
    """整段只是「很重要 / 非常紧急」这类评价语"""
    global EMPH_RE
    if EMPH_RE is None:
        import re as _re
        EMPH_RE = _re.compile(
            r"^(?:\W|\b)*(?:it'?s?|this is|that'?s|so|very|really|quite|extremely|"
            r"super|pretty|too)?(?:\W|\b)*(?:very|really|quite|extremely|super|pretty)?"
            r"(?:\W|\b)*(?:important|urgent|critical|crucial|vital|key|major|"
            r"a priority|top priority|asap)(?:\W|\b)*$", _re.I)
    return bool(EMPH_RE.match((seg or "").strip()))


def has_priority_signal(raw):
    """English: did the user express priority themselves?"""
    import re as _re
    return bool(_re.search(
        r"\b(urgent|asap|immediately|critical|crucial|vital|important|"
        r"no\s*rush|not\s*urgent|eventually|whenever|sometime|low\s*priority|"
        r"top\s*priority|a\s*priority)\b", (raw or ""), _re.I))


def find_repeat(text):
    """v1.9.9.48：英文周期表达 -> {"kind", "weekday", "weekdays", "monthday"}

    与中文解析器同构（main 的 _is_daily / _daily_due_today 直接复用）。
    识别 every day / daily / every week / every monday / on mondays /
    every weekday / every month 等。识别不出返回 None。"""
    t = (text or "").lower()
    if not t:
        return None
    m = re.search(r"\b(?:every|each)\s+(?:single\s+)?month\b|\bmonthly\b", t)
    if m:
        return {"kind": "monthly", "weekday": None, "weekdays": None,
                "monthday": None}
    wd_names = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
                "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3,
                "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
    days = []
    for m in re.finditer(r"\b(?:(every|each)\s+(?:single\s+)?|on\s+)?"
                         r"(monday|tuesday|wednesday|thursday|friday|"
                         r"saturday|sunday|mon|tues?|weds?|thur?s?|fri|sat|sun)"
                         r"(s?)\b", t):
        # 周期判定：every/each 修饰，或复数形式（on Mondays = 每周一）。
        # 单数「on Monday / meeting Monday」是一次性约会，不算日常。
        pre = (m.group(1) or "").strip()
        plural = m.group(3) == "s"
        if not pre and not plural:
            continue
        d = wd_names.get(m.group(2))
        if d is not None and d not in days:
            days.append(d)
    if days:
        return {"kind": "weekly", "weekday": days[0], "weekdays": days,
                "monthday": None}
    if re.search(r"\b(?:every|each)\s+(?:single\s+)?day\b|\bdaily\b|"
                 r"\b(?:every|each)\s+day\s+of\s+the\s+week\b|\beveryday\b", t):
        return {"kind": "daily", "weekday": None, "weekdays": None,
                "monthday": None}
    if re.search(r"\b(?:every|each|on)\s+(?:week\s*days?|work\s*days?|weekdays?)\b"
                 r"|\bweekdays\b", t):
        return {"kind": "weekly", "weekday": 0,
                "weekdays": [0, 1, 2, 3, 4], "monthday": None}
    if re.search(r"\b(?:every|each)\s+week\b|\bweekly\b", t):
        return {"kind": "weekly", "weekday": None, "weekdays": None,
                "monthday": None}
    return None


# v1.9.9.48：英文疑问句不是任务。「what did I do today」「what's on my
# list」此前被建成任务（查询入口只认中文，parser 这层也没拦）。
_QSTART_RE = re.compile(
    r"^\s*(?:what|when|where|why|who|how)('?s|\s+(?:did|do|does|is|are|was|"
    r"were|should|can|could|i|we|to|about|much|many|long))"
    r"|^\s*(?:did|do|does|is|are|can|could|should)\s+"
    r"(?:i|we|you|he|she|they|it|there|that)\b"
    r"|^\s*(?:is|was)\s+there\b", re.I)


def _is_question(text):
    t = (text or "").strip()
    if not t:
        return False
    if _QSTART_RE.match(t):
        return True
    # 句首疑问词 + 问号（「Buy milk?」是用户自问，不当任务更好——
    # 但太激进会拦掉「buy milk?」这种随手记，只拦真疑问词开头）
    return bool(re.match(r"^\s*(?:what|when|where|why|who|how)\b", t, re.I)
                and t.endswith("?"))


def parse_tasks(text, fallback=True):
    text = (text or "").strip()
    if not text:
        return []
    if _is_question(text):
        return []
    results, seen = [], set()
    for seg in split_segments(text):
        hhmm, passed, offset = find_time(seg)
        title = "" if _is_emphasis(seg) else clean(seg)
        if not title or _is_noise(title):
            # 「, very important」「this is urgent」这类评价语：并入上一条并抬分
            if results and _is_emphasis(seg):
                t0, h0, s0, raw0, d0 = results[-1]
                raw_new = raw0 + " , " + seg
                results[-1] = (t0, h0, score(t0, raw_new, h0, passed, offset), raw_new, d0)
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        # v1.9.9.49：补 due 日期（item[6]）。此前 tomorrow / day after tomorrow
        # 的 day_offset 被直接丢弃，主程序按「今天」判断，导致下午说
        # 「tomorrow 3pm」被误判成「时间已过」并追问，用户还得再答一次
        due = (dt.date.today() + dt.timedelta(days=offset)) if offset else None
        # v1.9.9.45：标题不再硬截断（显示层负责省略）
        # v1.9.9.48：补 repeat（item[5]）——英文「every monday」此前被
        # 当成普通临时任务，主窗口天天挂着（与中文行为不一致）
        rep = find_repeat(seg) or find_repeat(text)
        # 「every monday」这类周期词不留标题（同中文 clean 的行为）
        if rep:
            title = re.sub(
                r"\b(?:every|each)\s+(?:single\s+)?"
                r"(?:day|week|month|weekday|workday|mondays?|tuesdays?|"
                r"wednesdays?|thursdays?|fridays?|saturdays?|sundays?|"
                r"mons?|tues?|weds?|thur?s?|fris?|sats?|suns?)\b\s*"
                r"|\bmondays\b\s*|\btuesdays\b\s*|\bwednesdays\b\s*"
                r"|\bthursdays\b\s*|\bfridays\b\s*|\bsaturdays\b\s*"
                r"|\bsundays\b\s*|\bweekly\b\s*|\bdaily\b\s*",
                "", title, flags=re.I).strip() or title
        results.append((title, hhmm, score(title, seg, hhmm, passed, offset),
                        seg, _dur(seg), rep, due))
    if not results and fallback:
        # Fallback: a plain sentence like "buy milk" still becomes a task
        text2 = re.sub(r"^(?:please\s+|remember\s+to\s+|don'?t\s+forget\s+to\s+"
                       r"|i\s+(?:want\s+to|need\s+to|have\s+to|must)\s+"
                       r"|i'?ll\s+)""", "", text.strip(), flags=re.I)
        t = clean(text2)
        if t and len(t) >= 2 and len(t) <= 40:
            hhmm = None
            m2 = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text2, re.I)
            if m2:
                h = int(m2.group(1)) % 12 + (12 if m2.group(3).lower() == "pm" else 0)
                hhmm = "%02d:%02d" % (h, int(m2.group(2) or 0))
            _off = find_time(text2)[2]
            _due = (dt.date.today() + dt.timedelta(days=_off)) if _off else None
            results.append((t, hhmm, score(t, text2, hhmm, False, _off),
                            text2, _dur(text2), None, _due))
            results.sort(key=lambda x: (-x[2], x[1] or "99:99"))
    return results


def _dur(text):
    """时长（次要信息，不参与打分）"""
    import re as _re
    m = _re.search(r"\d{1,3}\s*(?:min|mins|minutes?|h|hr|hrs|hours?)\b", text or "", _re.I)
    return m.group(0).strip() if m else None


def priority_label(s):
    from i18n import t
    labels = t("prio")
    if s >= 75:
        return labels[0], "#E2434B"
    if s >= 55:
        return labels[1], "#EE9A2B"
    if s >= 35:
        return labels[2], "#3E8ED0"
    return labels[3], "#8A8F98"
