# -*- coding: utf-8 -*-
"""
每日记事本 —— 中文任务解析引擎（纯本地规则，不联网）

实现说明：本文件刻意避免使用 str.find / in / re.search 这类“子串查找”。
改为把文本拆成码点列表做序列匹配，行为与语言、编码、运行环境无耦合，
跨 Windows / Linux 结果完全一致。
"""
import re
import datetime as dt

# ---------------------------------------------------------------- 词表
IMPORTANT_WORDS = {
    "非常重要": 30, "最重要": 30, "重大": 26, "关键": 24, "核心": 22,
    "重要": 22, "要紧": 20, "重点": 18, "必须": 18, "务必": 18, "一定": 14,
    "领导": 20, "老板": 20, "客户": 18, "甲方": 18, "上级": 18, "汇报": 16,
    "合同": 20, "付款": 18, "转账": 18, "报销": 14, "工资": 16,
    "考试": 20, "面试": 20, "答辩": 20, "报名": 16, "预约": 12, "体检": 16,
    "医院": 18, "看病": 18, "吃药": 12, "接孩子": 20, "接送": 16,
    "生日": 16, "纪念日": 18, "结婚": 18, "婚礼": 18, "机票": 16, "高铁": 16,
    "飞机": 16, "签证": 20, "护照": 18, "身份证": 16, "贷款": 20, "还款": 20,
    "信用卡": 16, "房租": 16, "交费": 14, "缴费": 14, "学费": 16,
}
URGENT_WORDS = {
    "马上": 26, "立刻": 26, "立即": 26, "火速": 26, "赶紧": 22, "尽快": 20,
    "加急": 24, "紧急": 26, "现在就": 24, "救急": 24, "急救": 24, "急诊": 24,
    # v1.9.9.19：口语急迫说法（「买牛奶 很急」原来完全不得分）
    "很急": 26, "好急": 26, "太急": 26, "特急": 26, "十分紧急": 30,
}
RELAX_WORDS = {
    "有空": -18, "顺便": -16, "随便": -14, "不急": -20, "以后": -14,
    "改天": -16, "看情况": -14, "如果有时间": -20, "抽空": -12, "闲了": -16,
}
CN_NUM = {"零": 0, "〇": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
          # 大写（壹贰叁…）与异体（廿、两）一并识别，解析与「几点」互不影响
          "壹": 1, "贰": 2, "貳": 2, "叁": 3, "參": 3, "肆": 4, "伍": 5,
          "陆": 6, "陸": 6, "柒": 7, "捌": 8, "玖": 9, "拾": 10,
          "廿": 20, "卅": 30}
# 「十一点」「二十三点」「三十五分钟」「十五分钟」这类合成数，统一用这个字符组
CN_DIGIT = "零〇一二两三四五六七八九十壹贰貳叁參肆伍陆陸柒捌玖拾廿卅"
# 数字 + 中文量词：这些「数词」不是时间、不是时长，不能当噪音删掉
_COUNT_UNITS = ["个", "只", "件", "遍", "张", "本", "支", "瓶", "杯", "片", "条",
                "首", "篇", "页", "次", "位", "双", "套", "颗", "粒", "根", "把",
                "公里", "千米", "米", "公里路", "斤", "克", "公斤", "元", "块",
                "岁", "层", "楼", "路", "点建议"]
COUNT_RE = re.compile(r"(?:\d{1,4}|[%s]{1,4})\s*(?:%s)" % (
    CN_DIGIT, "|".join(sorted(_COUNT_UNITS, key=len, reverse=True))))
PERIOD_HINTS = {"上午": 9, "早上": 8, "早晨": 8, "中午": 12, "下午": 15,
                "傍晚": 18, "晚上": 20, "今晚": 20, "明晚": 20, "昨夜": 22,
                "夜里": 22, "凌晨": 2,
                "下班前": 18, "上班前": 9, "午饭前": 12, "睡觉前": 22}

DAY_WORDS = ["今天", "今日", "明天", "明日", "后天", "今儿", "明儿"]
PER_WORDS = ["上午", "下午", "中午", "早上", "早晨", "晚上", "今晚", "明晚", "傍晚",
             "夜里", "凌晨", "下班前", "上班前", "午饭前", "睡觉前"]
CLOCK_UNITS = ["点", "時", "时"]
BEFORE_TAILS = ["之前", "以前"]
AFTER_TAILS = ["左右"]
SPLIT_TOKENS = ["，", ",", "。", ";", "；", "\n", "\r", "!", "！", "?", "？", "~", "～", "、"]
JOIN_VERBS = ["然后", "接着", "还有", "另外", "以及", "之后", "并且", "接下来",
              "顺便", "再", "完了以后", "完了"]
TAIL_FILLERS = ["必须", "一定要", "务必", "记得", "要", "去", "得"]
TRAIL_WORDS = ["一下", "吧", "啊", "哦", "呢", "呀", "了", "哈", "嘛", "啦"]
LEAD_WORDS = ["的", "帮我", "请", "麻烦", "记得", "别忘了", "先",
              "我想", "我打算", "我准备", "我需要", "我要",
              "想要", "打算", "准备", "需要", "想", "得", "我得", "今天想", "今天我",
              "记得要", "别忘记了", "帮忙", "帮我个忙", "我想要", "今天需要",
              "提醒我", "提醒", "请提醒我", "帮我提醒", "我得去", "我要去"]
# 「把」「我」这类在句首不能直接删：删了会变成「换季的衣服整理好…」这种病句。
# 只有「我把 / 把」后面紧跟动词时才连带动词一起规范化 —— 保守起见直接保留原样。
LEAD_KEEP = ["把", "将", "我的"]
DEGREE_WORDS = ["非常", "特别", "很", "一定", "必须", "务必", "记得"]
MODIFIERS = ["非常", "特别", "很", "必须", "务必", "记得", "马上", "立刻", "立即", "赶紧", "尽快"]


# ---------------------------------------------------------------- 码点工具
def _codes(s):
    """字符串 -> 码点列表（唯一可靠的比较基准）"""
    return [ord(ch) for ch in s]


def _find_seq(seq, sub, start=0):
    """在码点列表中查找子序列，返回下标或 -1"""
    n, m = len(seq), len(sub)
    if m == 0:
        return start if start <= n else -1
    for i in range(start, n - m + 1):
        ok = True
        for j in range(m):
            if seq[i + j] != sub[j]:
                ok = False
                break
        if ok:
            return i
    return -1


def _contains(seq, word):
    return _find_seq(seq, _codes(word)) >= 0


def _has_word(text, word):
    return _contains(_codes(text), word)


def _remove_words(text, words):
    """删除文本中出现的若干词（码点级替换，长词优先）"""
    if not text:
        return text
    codes = _codes(text)
    for w in sorted([x for x in words if x], key=len, reverse=True):
        wc = _codes(w)
        i = 0
        while True:
            k = _find_seq(codes, wc, i)
            if k < 0:
                break
            codes = codes[:k] + codes[k + len(wc):]
            i = k
    return "".join(chr(c) for c in codes)


def _cut_at(text, marks):
    """按 [(start, end)] 列表把文本切成互不重叠的片段（保留非时间部分）"""
    out, last = [], 0
    for s, e in marks:
        if s > last:
            out.append(text[last:s])
        last = max(last, e)
    if last < len(text):
        out.append(text[last:])
    return "".join(out)


# 时间文本匹配（只用于定位要剔除的片段，不用它做“是否包含”判断）
# ⚠ 兼容「十一点」「二十三点」「三十五分钟」：数字部分统一用 %s 占位 CN_DIGIT
TIME_STRIP_RE = re.compile(
    r"\d{1,2}\s*[:：]\s*\d{1,2}|"
    r"(?:上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨|下班前|上班前|午饭前|睡觉前)\s*"
    r"(?:\d{1,2}|[%s]{1,3})?\s*(?:点|時|时)?\s*(?:半|\d{1,2}分?)?|"
    r"(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)\s*(?:钟|半|一刻|两刻|二刻|三刻|\d{1,2}分?)?\s*(?:之前|以前|前)?|"
    r"(?:\d{1,2}|[%s]{1,3}|半)\s*(?:天|日|个?\s*(?:周|星期|礼拜)|个?\s*月)\s*(?:之)?后|"
    # 「两小时后 / 半小时后 / 45分钟后」这类相对时刻
    r"(?:\d{1,3}|[%s]{1,3}|半)\s*个?\s*(?:半\s*)?(?:小时|分钟)\s*(?:之)?后|"
    # v1.9.9.18：纯时长也要整体剥（跑10分钟 → 跑，而不是「跑分钟」）
    r"(?:\d{1,3}|[%s]{1,3}|半)\s*个?\s*(?:半\s*)?(?:小时|分钟|秒钟?)|"
    r"一个半小时|半个小时|半小时|小半天|半天|"
    r"\d{1,2}\s*(?:之前|以前|前)|"
    r"上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨|下班前|上班前|午饭前|睡觉前|"
    r"今天|今日|明天|明日|后天|今儿|明儿|之前|以前|左右|点|時|时|(?<!\d)分(?!钟)|"
    # 日期：周三 / 下周一 / 周末 / 3月5日 / 15号
    r"(?:下下|下个?|这个?|本)?\s*(?:周|星期|礼拜)\s*[一二三四五六日天1-7]|"
    r"(?:下下|下个?|这个?|本)?\s*周末|"
    r"(?:\d{1,2}|[%s]{1,3})\s*月\s*(?:\d{1,2}|[%s]{1,3})\s*[日号]|"
    # 「N号」排除量词（3号电池 / 5号楼 / 2号会议室），用负向环视挡住
    r"(?<!\d)(?:\d{1,2}|[%s]{1,3})\s*[日号]"
    r"(?![记码楼栋房院线机位桌床柜仓门车窗箱包厅室岗位店单元])"
    % (CN_DIGIT, CN_DIGIT, CN_DIGIT, CN_DIGIT, CN_DIGIT, CN_DIGIT, CN_DIGIT,
       CN_DIGIT))


# ---------------------------------------------------------------- 时间识别
def _hits_of(text, words):
    """返回 [(word, start_index)]，按出现顺序"""
    seq = _codes(text)
    out = []
    for w in words:
        wc = _codes(w)
        i = 0
        while True:
            k = _find_seq(seq, wc, i)
            if k < 0:
                break
            out.append((w, k))
            i = k + len(wc)
    out.sort(key=lambda x: x[1])
    return out


def _num(tok):
    """中文/阿拉伯数字 -> int，支持「十一」「二十三」「三十五」「廿」"""
    tok = (tok or "").strip()
    if not tok:
        return 0
    if tok.isdigit():
        return int(tok)
    if tok in CN_NUM:
        return CN_NUM[tok]
    # 通用合成：X十Y / 十Y / X十
    total, cur = 0, 0
    for ch in tok:
        if ch in ("十", "拾"):
            if total > 0:
                # 「二十一」这种连续十位：先把已累积的整体再乘十
                total = (total + cur) * 10
                cur = 0
            else:
                cur = cur or 1
                total += cur * 10
                cur = 0
        elif ch in ("廿",):
            total += 20
        elif ch in ("卅",):
            total += 30
        else:
            cur = CN_NUM.get(ch, 0)
    return total + cur


def _parse_clock(segment):
    """从 '下午4点半' / '9:30' / '八点' / '晚上十一点' 里解析出 (hour, minute)"""
    hour = minute = None
    m = re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", segment)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(\d{1,2}|[%s]{1,3})\s*(?:点|時|时)" % CN_DIGIT +
                      r"(?:\s*半|\s*(?:(\d{1,2})|([%s]{1,3}))\s*分?)?" % CN_DIGIT, segment)
        if m:
            hour = _num(m.group(1))
            if "半" in segment:
                minute = 30
            elif m.group(2):
                minute = int(m.group(2))
            elif m.group(3):
                minute = _num(m.group(3))
            else:
                minute = 0
            per = re.search(r"上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨", segment)
            if per:
                pw = per.group(0)
                if pw in ("下午", "晚上", "傍晚", "夜里") and hour < 12:
                    hour += 12
                elif pw == "中午" and hour < 11:
                    hour += 12
                elif pw == "凌晨" and hour == 12:
                    hour = 0
    if hour is None or not (0 <= hour <= 23):
        return None
    return hour % 24, min(minute or 0, 59)


WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6,
               "天": 6, "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}
WEEKDAY_NUM = ["一", "二", "三", "四", "五", "六", "日"]


def find_weekday(text):
    """「周三」「星期三」「礼拜五」「下周一」「这周末」-> (距今天数, 原始片段)
    距今天数可以为 0（就是今天）。找不到返回 (None, None)。"""
    m = re.search(r"(下下|下个?|这个?|本)?\s*(?:周|星期|礼拜)\s*([一二三四五六日天1-7])"
                  r"|(下下|下个?|这个?|本)?\s*周末", text)
    if not m:
        return None, None
    today = dt.date.today()
    if m.group(0).endswith("周末"):
        pre = m.group(3) or ""
        sat = 5 - today.weekday()          # 本周六还有几天
        if sat < 0:
            sat += 7
        if pre.startswith("下下"):
            sat += 14
        elif pre.startswith("下"):
            sat += 7
        return sat, m.group(0)
    pre, wd = m.group(1) or "", m.group(2)
    target = WEEKDAY_MAP.get(wd, 0)
    delta = (target - today.weekday()) % 7
    if pre.startswith("下下"):
        delta += 14
    elif pre.startswith("下"):
        delta += 7 if delta else 7      # 「下周三」永远是 7 天后那一周
    # 光说「周三」且已经过了 -> 顺延到下周
    if delta == 0 and re.search(r"(之前|以前|前)", text[m.end():m.end() + 4] or ""):
        delta = 0
    return delta, m.group(0)


def find_weekday_multi(text):
    """v1.9.9.29：「每周一三五」/「周三、周五」这类连写的星期几。

    返回命中的片段（含所有连写的星期几），没有则 None。
    用途只有一个：**连写时不要再拿「第一个」当截止日期**。
    「每周一三五跑步」如果只认「周一」，clean_title 会剥掉「周一」，
    标题就剩「三五跑步」；而且 find_times 会给它兜底 18:00 的截止时间。
    """
    if not text:
        return None
    m = re.search(r"(?:周|星期|礼拜)\s*"
                  r"[一二三四五六日天1-7](?:\s*[、,，和]?\s*[至到\-~]?\s*[一二三四五六日天1-7])+",
                  text)
    return m.group(0) if m else None


def is_multi_weekday(text):
    """「每周一三五」这类连写星期几（≥2 个）——不是单一日期"""
    return find_weekday_multi(text) is not None


def find_deadline_date(text):
    """抽取「日期型」截止信息 -> (date 或 None, 原始片段)
    支持：明天/后天/大后天/今天、周三/星期三/下周一/周末、
          3月5日/3-5/3/5、15号/15日。"""
    today = dt.date.today()
    # 0) 「3天后 / 一周后 / 半个月后」这类相对天数
    _REL_N = r"(\d{1,2}|[%s]{1,3}|半)" % CN_DIGIT
    m = re.search(_REL_N + r"\s*(?:天|日)\s*(?:之)?后", text)
    if m:
        n = 15 if m.group(1) == "半" else _num(m.group(1))
        if 0 < n <= 365:
            return today + dt.timedelta(days=n), m.group(0)
    m = re.search(_REL_N + r"\s*(?:个)?\s*(?:周|星期|礼拜)\s*(?:之)?后", text)
    if m:
        n = 0.5 if m.group(1) == "半" else _num(m.group(1))
        if 0 < n <= 52:
            return today + dt.timedelta(days=int(round(n * 7))), m.group(0)
    m = re.search(_REL_N + r"\s*(?:个)?\s*月\s*(?:之)?后", text)
    if m:
        if m.group(1) == "半":
            return today + dt.timedelta(days=15), m.group(0)
        n = _num(m.group(1))
        if 0 < n <= 24:
            y, mo = today.year + (today.month - 1 + n) // 12, (today.month - 1 + n) % 12 + 1
            try:
                return dt.date(y, mo, min(today.day, 28)), m.group(0)
            except ValueError:
                pass
    # 1) 相对天
    for w, off in (("大后天", 3), ("后天", 2), ("明天", 1), ("明日", 1), ("明儿", 1),
                   ("今天", 0), ("今日", 0), ("今儿", 0)):
        if _has_word(text, w):
            return today + dt.timedelta(days=off), w
    # 2) 星期
    delta, raw = find_weekday(text)
    if delta is not None:
        return today + dt.timedelta(days=delta), raw
    # 3) 月日
    m = re.search(r"(\d{1,2}|[一二三四五六七八九十]{1,3})\s*月\s*(\d{1,2}|[一二三四五六七八九十]{1,3})\s*[日号]", text)
    if m:
        mo, dy = _num(m.group(1)), _num(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            try:
                d = dt.date(today.year, mo, dy)
                if d < today and (today - d).days > 184:
                    d = dt.date(today.year + 1, mo, dy)   # 早了半年以上 -> 用户多半指明年
                # 半年内的过去日期原样保留，上层做「已过截止日期」确认
                return d, m.group(0)
            except ValueError:
                pass
    m = re.search(r"(\d{1,2})\s*[/-]\s*(\d{1,2})(?!\d)", text)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            try:
                d = dt.date(today.year, mo, dy)
                if d < today and (today - d).days > 184:
                    d = dt.date(today.year + 1, mo, dy)
                return d, m.group(0)
            except ValueError:
                pass
    # 4.5) 月底（当月最后一天）
    m = re.search(r"(?:这个月|本月|月)底", text)
    if m:
        nxt = dt.date(today.year + (1 if today.month == 12 else 0),
                      today.month % 12 + 1, 1)
        return nxt - dt.timedelta(days=1), m.group(0)
    # 5) 日：15号 / 15日
    # ⚠ 只有「N号」后面不是量词时才算日期：「3号电池」「5号楼」「2号会议室」
    #   里的「号」是序号，误判会把标题啃成「电池」「楼开会」。
    _UNIT = "记码楼栋房院线机位桌床柜仓门车窗箱包厅室会岗位店单元电"
    for m in re.finditer(r"(?<!\d)(\d{1,2}|[一二三四五六七八九十]{1,3})\s*[号日]", text):
        tail = text[m.end():m.end() + 2]
        # 「号楼」「号房」「号会议室」这类后面还跟实词的，一律按序号处理
        if m.group(0)[-1] == "号" and tail and (
                tail[0] in _UNIT or re.match(r"(会议|活动|方案|文件|项目|桌子)", tail)):
            continue
        dy = _num(m.group(1))
        if 1 <= dy <= 31:
            try:
                d = today.replace(day=dy)
                if d < today:
                    mo = today.month % 12 + 1
                    yr = today.year + (1 if today.month == 12 else 0)
                    d = dt.date(yr, mo, dy)
                return d, m.group(0)
            except ValueError:
                pass
    return None, None


def find_times(text):
    """扫描时间信息 -> [(hhmm, 是否已过, 命中的原始片段, 日期偏移)]"""
    out = []

    # 1) 数字型 "9:30"
    for m in re.finditer(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", text):
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23:
            out.append((f"{h:02d}:{mi:02d}", (h, mi), m.start(), m.group(0)))
    # 1.5) 「下午三点到四点」这种区间：取开始时间，避免被后面的「四点」覆盖
    _rng = re.search(
        r"(上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨)?\s*"
        r"(\d{1,2}|[%s]{1,3})\s*(?:点|時|时)\s*(?:半|\d{1,2}分?)?"
        r"\s*(?:到|至|-|~|～)\s*"
        r"(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)" % (CN_DIGIT, CN_DIGIT), text)
    if _rng:
        h = _num(_rng.group(2))
        per = _rng.group(1) or ""
        if per in ("下午", "晚上", "傍晚", "夜里") and h < 12:
            h += 12
        elif per == "中午" and h < 11:
            h += 12
        if 0 <= h <= 23:
            out.append((f"{h:02d}:00", (h, 0), _rng.start(), _rng.group(0)))
    # 2) 中文钟点（含「十一点」「二十三点」「壹拾贰点」；v1.9.4 加「一刻」=15分）
    # v1.9.9.18：刻钟要排在「数字分钟」之前匹配，否则「九点三刻」里的
    # 「三」被当成 3 分钟（→ 09:03），正确应为 09:45
    for m in re.finditer(r"(上午|下午|中午|早上|早晨|晚上|今晚|明晚|傍晚|夜里|凌晨)?\s*"
                         r"(\d{1,2}|[%s]{1,3})\s*(?:点|時|时)\s*钟?" % CN_DIGIT +
                         r"(?:\s*半|\s*(一刻|两刻|二刻|三刻)|"
                         r"\s*(?:(\d{1,2})|([%s]{1,3}))\s*分?)?" % CN_DIGIT +
                         r"\s*(?:之前|以前|前)?", text):
        h = _num(m.group(2))
        per = m.group(1) or ""
        if per in ("下午", "晚上", "今晚", "明晚", "傍晚", "夜里") and h < 12:
            h += 12
        elif per == "中午" and h < 11:
            h += 12
        elif per == "凌晨" and h == 12:
            h = 0
        if not (0 <= h <= 23):
            continue
        if "半" in m.group(0):
            mi = 30
        elif m.group(3):                    # 一刻/两刻/二刻/三刻
            mi = {"一刻": 15, "两刻": 30, "二刻": 30, "三刻": 45}[m.group(3)]
        else:
            mi = int(m.group(4)) if m.group(4) else (_num(m.group(5)) if m.group(5) else 0)
        out.append((f"{h:02d}:{mi:02d}", (h, mi), m.start(), m.group(0)))
    # 3) 只有时段词
    for w, idx in _hits_of(text, PER_WORDS):
        h = PERIOD_HINTS.get(w)
        if h is not None:
            out.append((f"{h:02d}:00", (h, 0), idx, w))
    # 4) 星期：周三之前 / 星期五 / 下周一 -> 18:00（当天结束前）
    #    ⚠ 只在「没有任何真实钟点」时才兜底；像「周五晚上十点前洗漱」
    #    已有 22:00，不能再让星期兜底的 18:00 排在前面抢走 hhmm
    #    v1.9.9.19：「周六上午去银行」里有真实时段词（上午→09:00）时
    #    也不追加 18:00，否则 18:00 按位置排在前面，提醒定到傍晚
    wdelta, wraw = find_weekday(text)
    has_clock = any(("点" in raw or ":" in raw) for _h, _hm, _pos, raw in out)
    _has_period = any(raw in PERIOD_HINTS for _h, _hm, _pos, raw in out)
    # v1.9.9.29：连写的星期几（每周一三五）不是「某个具体日子」，
    # 它的「今天该不该做」由 repeat 判断，不能兜底成 18:00 的截止时间
    # ——否则会凭空多出一个当天截止，且 clean_title 还会只剥掉第一个星期几。
    if find_weekday_multi(text):
        wdelta, wraw = None, None
    if wdelta is not None and not has_clock and not _has_period:
        out.append(("18:00", (18, 0), 0, wraw))

    if not out:
        return []

    out.sort(key=lambda x: x[2])
    # 去重（同一位置只保留一个）
    dedup, seen_pos = [], set()
    for hhmm, hm, pos, raw in out:
        if pos in seen_pos:
            continue
        seen_pos.add(pos)
        dedup.append((hhmm, hm, pos, raw))

    now = dt.datetime.now()
    result = []
    day_offset = 1 if (_has_word(text, "明天") or _has_word(text, "明日") or _has_word(text, "明儿")) else (
        2 if _has_word(text, "后天") else 0)
    if day_offset == 0 and _has_word(text, "大后天"):
        day_offset = 3
    if day_offset == 0 and wdelta is not None:
        day_offset = wdelta
    for hhmm, (h, mi), pos, raw in dedup:
        passed = day_offset > 0 or (h * 60 + mi) < (now.hour * 60 + now.minute)
        result.append((hhmm, passed, raw, day_offset))
    return result


# ---------------------------------------------------------------- 标题清洗
# 时间/数量之外的「噪音数字」：只清掉裸数字，带量词的（30个 / 五公里 / 2位）保留
# ⚠ 不能用前瞻断言剔除——\d{1,5} 会回溯出一位来满足前瞻（「20个」→「0个」）。
#   做法：先把「数字+量词」换成占位符保护起来，清洗完再还原。
BARE_NUM_RE = re.compile(r"(?<!\d)\d+(?!\d)")
# 占位符必须用「字母」而不是私用区字符：BARE_NUM_RE 的 (?<!\d) 后视会把
# 「\ue00020个」里的 20 当成独立数字继续拆（字符边界判断按 \w 走），导致保护失效。
# 占位符里绝对不能出现数字，否则 BARE_NUM_RE 仍会把编号当裸数字删掉
_QTY_SLOTS = ["\x02aq\x03", "\x02bq\x03", "\x02cq\x03", "\x02dq\x03", "\x02eq\x03",
              "\x02fq\x03", "\x02gq\x03", "\x02hq\x03", "\x02iq\x03", "\x02jq\x03"]


# v1.9.9.18：算式保护槽。BARE_NUM_RE 会剥掉孤立数字，「1+1=2」就只剩「+=」。
# 槽位同样不能含数字。
_MATH_SLOTS = ["\x02am\x03", "\x02bm\x03", "\x02cm\x03", "\x02dm\x03", "\x02em\x03",
               "\x02fm\x03", "\x02gm\x03", "\x02hm\x03"]
# 算式：至少一个运算符，两侧带数字（1+1=2 / 3*4 / 15/3 / 2^10）
_MATH_RE = re.compile(r"\d+(?:\.\d+)?(?:\s*[+\-*/×÷^%]\s*\d+(?:\.\d+)?)+"
                      r"(?:\s*=\s*\d+(?:\.\d+)?)?")


def _protect_math(t):
    """把算式整体换成占位符，避免孤立数字被剥掉后只剩运算符"""
    bag = []

    def _wrap(m):
        v = m.group(0)
        slot = _MATH_SLOTS[len(bag) % len(_MATH_SLOTS)]
        bag.append((slot, v))
        return slot

    return _MATH_RE.sub(_wrap, t), bag


def _restore_math(t, bag):
    for slot, v in bag or []:
        t = t.replace(slot, v)
    return t


def _protect_qty(t):
    """把「20个 / 3次 / 2位」这类数量词换成占位符，免被当噪音数字删掉。
    时间量词（分钟 / 小时 / 点）不保护，交给 find_duration / find_times 处理。"""
    bag = []

    def _wrap(m):
        v = m.group(0)
        if re.search(r"(小时|分钟|分|点)$", v):
            return v
        slot = _QTY_SLOTS[len(bag) % len(_QTY_SLOTS)]
        bag.append(v)
        return slot

    out = COUNT_RE.sub(_wrap, t)
    return out, bag


def _restore_qty(t, bag):
    for i, v in enumerate(bag or []):
        slot = _QTY_SLOTS[i % len(_QTY_SLOTS)]
        t = t.replace(slot, v, 1)
    return t


# 序号「N号」的保护：3号电池 / 5号楼 / 2号会议室 里的「号」是序号，
# 不是「某月某号」的日期。判定靠「号」后面紧跟的实词——
# 日期用法后面通常接动词/时间词（15号交房租、20号之前报销），
# 序号用法后面接的是量词/名词（3号电池、5号楼、2号会议室）。
_SEQ_UNIT = "记码楼栋房院线机位桌床柜仓门车窗箱包室会岗位店单元床单电电池"
_SEQ_RE = re.compile(
    r"(?<![\d一二三四五六七八九十])"
    r"(\d{1,2}|[一二三四五六七八九十]{1,3})\s*号"
    r"(?=[" + _SEQ_UNIT + r"])")
# 用汉字占位（控制字符会被后续清理正则吞掉）
_SEQ_SLOTS = ["卮甲", "卮乙", "卮丙", "卮丁", "卮戊", "卮己", "卮庚", "卮辛", "卮壬"]


def _protect_seq_no(t):
    """把「N号+量词」整体换成占位符，避免被 TIME_STRIP_RE 当日期剔除"""
    bag = []

    def _wrap(m):
        slot = _SEQ_SLOTS[len(bag) % len(_SEQ_SLOTS)]
        bag.append(m.group(0))
        return slot

    return _SEQ_RE.sub(_wrap, t), bag


def _restore_seq_no(t, bag):
    for i, v in enumerate(bag or []):
        t = t.replace(_SEQ_SLOTS[i % len(_SEQ_SLOTS)], v, 1)
    # 占位符若被空格切断，把残留片段也还原成原文（兜底）
    for slot in _SEQ_SLOTS:
        if slot in t:
            t = t.replace(slot, "")
    return t


# 「时」开头但并不是钟点的复合词（v1.9.9）
# TIME_STRIP_RE 末尾有一条单字兜底 r"...|点|時|时|..."，本意是收掉
# 「九点」被吃掉数字后剩下的「点」、以及半角写法。但它对「时」是不加区分的，
# 于是「整理时间表」→「整理间表」、「时间管理课」→「间管理课」、
# 「撤一下时间」→「撤一下间」。这直接影响：
#   ① 标题准确性（用户最关心的解析准确率）
#   ② 撤回指令识别（「撤一下时间」认不出来，被当成新任务记了下来）
# 这里把「时间/小时/时候…」整体占位保护，时间片段剔完再换回。
_SHI_WORDS = ["时间", "时候", "时段", "时区", "时钟", "时常", "时期", "时光",
              "时代", "时效", "时时", "时不时", "时分", "时辰", "时机",
              "小时", "几时", "何时", "同时", "及时", "按时", "准时",
              "临时", "实际", "时尚", "时差", "时薪", "工时", "课时", "学时"]
_SHI_RE = re.compile("|".join(sorted(map(re.escape, _SHI_WORDS), key=len, reverse=True)))
# 占位符必须用中文字符集之外的符号：TIME_STRIP_RE 里还有「分」「间」这种单字分支，
# 用汉字占位会被二次误伤（实测「时间」被啃成「间」）。
# 占位符要同时躲开两件事：① TIME_STRIP_RE 里的中文单字分支（「分」「间」「点」），
# ② BARE_NUM_RE 对裸数字的清洗（「卮子1」里的 1 会被吃掉，导致还不了原）。
# 所以用私有区字符打头 + 纯字母编号，两端用 \uE0FF 收口。
_SHI_SLOTS = ["\uE000", "\uE001", "\uE002", "\uE003", "\uE004", "\uE005",
              "\uE006", "\uE007", "\uE008", "\uE009", "\uE00A", "\uE00B",
              "\uE00C", "\uE00D", "\uE00E", "\uE00F"]
_ALPHA = "abcdefghijklmnopqrstuvwxyz"


def _protect_shi(t):
    """把「时间」「小时」这类词整体占位，避免里面的「时」被当钟点单位剔掉"""
    bag = []

    def _wrap(m):
        idx = len(bag)
        bag.append(m.group(0))
        return _SHI_SLOTS[idx % len(_SHI_SLOTS)] + "z" + _ALPHA[idx % 26] + "\uE0FF"

    return _SHI_RE.sub(_wrap, t), bag


def _restore_shi(t, bag):
    for i, v in enumerate(bag or []):
        t = t.replace(_SHI_SLOTS[i % len(_SHI_SLOTS)] + "z" + _ALPHA[i % 26] + "\uE0FF", v)
    # 兜底：占位符被后续清洗拆散时，直接抹掉残留标记
    for slot in _SHI_SLOTS:
        if slot in t:
            t = re.sub(re.escape(slot) + r"[a-z]*\uE0FF?", "", t)
    return t


# 行首残留：完成任务的语气/指代，属于噪音
HEAD_NOISE = ["记一下", "记下", "帮我记", "帮我记一下", "帮我记下", "记一笔", "备注",
              "提醒我一句", "友善提醒", "提醒一下", "请提醒我", "帮我提醒", "一下"]# 句中噪音：礼貌、语气，不参与任务本体
MID_NOISE = ["麻烦你", "麻烦", "请帮我", "帮我一下", "谢谢你", "好的", "其实", "那个",
             "这个事", "一下子", "别忘了"]


def clean_title(text, hits=()):
    t = text or ""
    # v1.9.9.19：「9:00-11:00开会」的区间里两个时间 hit 被分别切掉后，
    # 残留「-」和半截数字（→「00-11开会」）。先把「时间-连接-时间」
    # 整段剥掉，四种连接符（- / ~ / 到 / 至）都覆盖。
    _RT = (r"(?:\d{1,2}\s*[:：]\s*\d{1,2}|(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)"
           r"(?:\s*(?:钟|半|一刻|两刻|二刻|三刻|\d{1,2}\s*分?))?)" % CN_DIGIT)
    t = re.sub(r"(?:上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨)?\s*"
               r"%s\s*(?:到|至|-|~|～|—)\s*%s" % (_RT, _RT), " ", t)
    # v1.9.9.19：句尾优先级短语整体剥掉（「9点开会 很重要」→「开会」）。
    # 只剥句尾，避免误伤「买重要文件」「重要客户到访」这类正文。
    # 必须在程度词删除之前做：否则 DEGREE_WORDS 先删「很」剩孤字「重」。
    _PRI = r"(?:非常重要|十分紧急|特别重要|很重要|很紧急|很急|好急|太急|特急|重要|紧急|要紧|火急|加急|急)"
    t = re.sub(r"[\s，,]*" + _PRI + r"\s*$", " ", t)
    # v1.9.9.18：算式（1+1=2 / 3*4 / 15/3）先整体保护起来。否则
    # BARE_NUM_RE 会把孤立的数字剥掉，只剩「+=」这种残缺标题。
    t, _math_bag = _protect_math(t)
    # v1.9.9.18：hits 只覆盖「九点」不含「钟」，先整体吃掉复合时间词，
    # v1.9.9.18：时长 + 截止词整体剥掉，否则「一个小时内交」剩「内交」、
    # 「15分钟后交报告」剩「后交报告」。放在最前面，避免 hits 先切了时长
    # 只留下悬空的「内/后」。
    _DUR = r"(?:\d{1,3}|[%s]{1,3}|半)\s*个?\s*(?:半\s*)?(?:小时|分钟|秒|钟头)" % CN_DIGIT
    t = re.sub(_DUR + r"\s*(?:之内|以内|内|之后|以后|后|之前|以前|前)?", " ", t)
    t = re.sub(r"(?:\d{1,3}|[%s]{1,3})\s*刻\s*钟\s*"
               r"(?:之内|以内|内|之后|以后|后|之前|以前|前)?" % CN_DIGIT, " ", t)
    # 否则残留「钟」（九点钟开会 → 钟开会）。同理「N点M刻」的「刻」。
    t = re.sub(r"(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)\s*钟"
               r"(?:\s*半|\s*一刻|\s*两刻|\s*二刻|\s*三刻|\s*\d{1,2}\s*分?)?" % CN_DIGIT,
               " ", t)
    t = re.sub(r"(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)\s*"
               r"(?:一刻|两刻|二刻|三刻)" % CN_DIGIT, " ", t)
    # 「每 + 日期/时间词」整体移除（每周三下午2点开会 → 开会）
    # v1.9.9.29：「每周一三五跑步」原来只剥掉「每周一」，剩「三五跑步」。
    # 星期几可以连写（一三五 / 二四 / 一至五），这里把整串一起吃掉。
    _WD = r"[一二三四五六日天1-7]"
    _WDSEQ = _WD + r"(?:\s*[、,，和]?\s*[至到\-~]?\s*" + _WD + r")*"
    t = re.sub(r"每\s*(?:周|星期|礼拜)\s*" + _WDSEQ + r"\s*"
               r"(?:上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨)?\s*"
               r"(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)\s*"
               r"(?:钟|半|\d{1,2}\s*分?)?" % CN_DIGIT, " ", t)
    # v1.9.9.29：没有钟点的纯星期串也要整段吃（每周一三五跑步 → 跑步）。
    # 放在上面带钟点的那条之后，避免把「每周三下午2点」啃成「下午2点」。
    t = re.sub(r"每\s*(?:周|星期|礼拜)\s*" + _WDSEQ, " ", t)
    # v1.9.9.17：先切最长的时间词（「每周一」要在「周一」之前切，
    # 否则短的先切掉、长的就找不到了，标题残留「每」）
    for h in sorted([h for h in hits if h], key=len, reverse=True):
        t = _cut_at(t, [(m.start(), m.end()) for m in re.finditer(re.escape(h), t)])
    # 去掉所有时间表达（点/分钟/日期/时段）；数量词先保护起来
    t, _bag = _protect_qty(t)
    # ⚠「3号电池」「5号楼」「2号会议室」里的「N号」是序号不是日期，
    #   先换成占位符保护起来，否则会被当日期整段剔除（标题变「电池」）
    t, _seq_bag = _protect_seq_no(t)
    # ⚠ v1.9.9：「时间」「小时」里的「时」不是钟点单位。
    #   TIME_STRIP_RE 末尾有单字兜底「点|時|时|」，会把「时间管理课」啃成
    #   「间管理课」、「整理时间表」啃成「整理间表」、「撤一下时间」啃成
    #   「撤一下间」（后者还导致「撤一下时间」不被识别为撤回指令）。
    #   这里先把「时间/小时/时候/时段/时区/时不时…」整体换成占位符，
    #   等时间表达剔完再换回来。
    t, _t_bag = _protect_shi(t)
    t = TIME_STRIP_RE.sub(" ", t)
    t = BARE_NUM_RE.sub(" ", t)
    t = _restore_qty(t, _bag)
    t = _restore_seq_no(t, _seq_bag)
    # 「时间」占位符先不还原：后面的 TAIL_FILLERS/_remove_words/单字兜底
    # 也会按子串啃「时」，提前还原等于把肉喂给它们。统一在函数末尾还原。
    t = t.strip()
    # 时间表达被剔掉后常留下「在…前完成数学」→「在前完成数学」这种残句：
    # 收掉悬空的「在/于/从/到/截至」和孤零零的「前/之前/以前」。
    for _ in range(2):
        t = re.sub(r"^(?:在|于|从|到|至|截至|赶在|趁着)\s*", "", t)
        t = re.sub(r"^(?:之前|以前|前|左右)\s*", "", t)
        t = re.sub(r"^(?:在|于)\s*(?=.{2,})", "", t)
        t = re.sub(r"^(?:之前|以前|前|之内|以内|内|左右|点|时)\s*", "", t)
        # v1.9.9：上面那条会把「时间表」的「时」当残留钟点剔掉（→「间表」）。
        # 只在「时」后面不是「间/候/段…」时才动手。
        t = re.sub(r"^(?:之前|以前|前|之内|以内|内|左右|点)\s*", "", t)
        t = re.sub(r"^时(?!间|候|段|区|钟|常|期|光|代|效|辰|差|尚)", "", t)
        t = re.sub(r"^[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’、]+", "", t)
        t = re.sub(r"[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’、]+$", "", t)
    # 去掉前导动词/代词、尾部语气词
    changed, rounds = True, 0
    while changed and rounds < 5:
        changed = False
        rounds += 1
        for w in HEAD_NOISE + LEAD_WORDS:
            if t.startswith(w):
                t = t[len(w):]
                changed = True
        for w in TAIL_FILLERS:
            if t.endswith(w):
                t = t[:-len(w)]
                changed = True
        for w in TRAIL_WORDS:
            if t.endswith(w):
                t = t[:-len(w)]
                changed = True
        t = t.strip()
        t = re.sub(r"^[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’、]+", "", t)
        t = re.sub(r"[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’、]+$", "", t)
    t = _remove_words(t, DEGREE_WORDS)
    t = _remove_words(t, MID_NOISE)
    # 「把水电费交了」→「交水电费」：介词结构里结果补语跑到了句尾
    # （「了」被当语气词删掉后只剩「把X交」这种病句）
    m_ba = re.match(r"^[把将](.+?)([交办买做发写读看念拿还送打洗整理准备完成弄修换])$", t)
    if m_ba and len(m_ba.group(1)) >= 2:
        t = m_ba.group(2) + m_ba.group(1)
    # 句首残留的「我 / 我的」：只在后面还有实词时才删
    # （「我护照放在…」→「护照放在…」，但单独的「我」不动）
    t = re.sub(r"^我的(?=.{2,})", "", t)
    t = re.sub(r"^我(?=[去见拿做写读看做吃喝办交还打发买送学练背])", "", t)
    # 时长被剔除后常留下"看的书""跑半小时的步"这类残句，把孤立的"的"收掉
    t = re.sub(r"[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’]+", "", t)
    # 只在"动词+的+名词"这种被截断的残句里去掉"的"（看书 而不是 看的书）
    if len(t) >= 3 and t[1] == "的":
        t = t[0] + t[2:]
    if len(t) <= 1:
        t2 = _remove_words(text, MODIFIERS + DAY_WORDS + PER_WORDS)
        t2 = TIME_STRIP_RE.sub("", t2)
        t2 = BARE_NUM_RE.sub("", t2)
        # v1.9.9.18：残留的「之后/以内/之内/后/前」粘连词也要收掉，
        # 否则「一个小时内交」兜底重建出「内交」把正确的「交」盖掉
        _DUR2 = (r"(?:\d{1,3}|[%s]{1,3}|半)\s*个?\s*(?:半\s*)?"
                 r"(?:小时|分钟|秒|钟头|刻\s*钟)" % CN_DIGIT)
        t2 = re.sub(_DUR2 + r"\s*(?:之内|以内|内|之后|以后|后|之前|以前|前)?", "", t2)
        t2 = re.sub(r"^(?:之内|以内|内|之后|以后|后|之前|以前|前)\s*", "", t2)
        t2 = re.sub(r"[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’]+", "", t2)
        # 只有重建结果确实比现有更完整（且不含悬空截止词）时才采用
        if len(t2) >= 2 and not re.match(r"^(?:之?[内外后前])", t2):
            t = t2
    t = _restore_shi(t, _t_bag)
    t = _restore_math(t, _math_bag)
    return t


# ---------------------------------------------------------------- 优先级
def find_duration(text):
    """抽取「时长」类表达 -> (时长文本, 命中的原始片段) 或 (None, None)
    与「几点」不同，时长不参与优先级计算，只作为任务的次要信息展示。"""
    if not text:
        return None, None
    # 15分钟 / 半小时 / 两个小时 / 一个半小时 / 45 min / 1h
    pats = [
        # v1.9.9.18：先认「两刻钟 / 一刻钟」（=15 的整数倍），否则「两刻钟」
        # 会被下面的「X分钟」近似不上而漏掉
        r"(?:\d{1,3}|[%s]{1,3})\s*刻\s*钟" % CN_DIGIT,
        r"(?:\d{1,3}|[%s]{1,3})\s*个\s*半\s*小时" % CN_DIGIT,
        r"(\d{1,3}|[%s]{1,3})\s*个?\s*半?\s*小时" % CN_DIGIT,
        r"(\d{1,3}|[%s]{1,3})\s*分钟" % CN_DIGIT,
        r"(?<![点時时\d])(\d{1,3}|[%s]{1,3})\s*分(?!钟)" % CN_DIGIT,
        r"半\s*个?\s*小时",
        r"(\d{1,3})\s*(?:min|mins|minutes?)",
        r"(\d{1,2})\s*(?:h|hr|hrs|hours?)",
    ]
    for p in pats:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0).strip(), m.group(0).strip()
    return None, None


def has_priority_signal(raw):
    """用户有没有亲口表达过优先级（重要/紧急/不急……）"""
    seq = _codes(raw or "")
    for w in list(IMPORTANT_WORDS) + list(URGENT_WORDS) + list(RELAX_WORDS):
        if _contains(seq, w):
            return True
    return False


def score_task(title, raw, hhmm, passed=False, day_offset=0):
    seq = _codes(raw)
    s = 30.0
    imp = 0
    for w in IMPORTANT_WORDS:
        if _contains(seq, w):
            imp = max(imp, IMPORTANT_WORDS[w])
    s += imp * 0.9
    # v1.9.9.17：多个紧急词同时出现要叠加（马上+救急=明确紧急），
    # 之前只取第一个就 break，「马上救急送医院」到不了紧急档
    _urgent_hits = [w for w in URGENT_WORDS if _contains(seq, w)]
    for w in _urgent_hits:
        s += URGENT_WORDS[w] * 0.8
    if len(_urgent_hits) >= 2:
        s += 15          # 叠加奖励：两个以上紧急词直接拉进紧急档
    # v1.9.9.19：用户**亲口**说「紧急/很急/马上」时保底进相应档，
    # 否则「买牛奶 很急」30+21=51 还是「一般」，急迫表达完全没生效。
    # 强急词（紧急/很急…）保底紧急档；弱急词（马上/赶紧…）保底重要档；
    # 明确说「很重要/非常重要」保底重要档。
    _STRONG_URGENT = {"紧急", "很急", "好急", "太急", "特急", "火速", "加急",
                      "现在就", "救急", "急救", "急诊", "十分紧急"}
    if _urgent_hits:
        if set(_urgent_hits) & _STRONG_URGENT:
            s = max(s, 78)
        else:
            s = max(s, 60)
    elif any(_contains(seq, w) for w in ("非常重要", "很重要", "特别重要",
                                         "最重要", "要紧")):
        s = max(s, 60)
    for w in RELAX_WORDS:
        if _contains(seq, w):
            s += RELAX_WORDS[w]
            break
    # 按「距离今天的天数」扣分，而不是把星期折叠成 offset 一起扣
    wd_raw = bool(re.search(r"(?:周|星期|礼拜)\s*[一二三四五六日天1-7]", raw or ""))
    weekend_raw = "周末" in (raw or "")
    if weekend_raw:
        s -= 2                          # 周末计划：略低，但别压成最低
    elif wd_raw:
        s += 10 if day_offset in (0, 1, 2) else 5    # 周三前＝本周内，偏要紧
    elif day_offset == 1:
        s -= 10
    elif day_offset >= 2:
        s -= 18
    # 周期任务（每天/每周）不是「今天必须交」那一类，稍微降一点
    if re.search(r"(每天|每日|每晚|每早|每周|每月)", raw or ""):
        s -= 6
    if hhmm:
        now = dt.datetime.now()
        mins = int(hhmm[:2]) * 60 + int(hhmm[3:]) - (now.hour * 60 + now.minute)
        if passed:
            s -= 8
        if mins <= 30:
            s += 34
        elif mins <= 60:
            s += 30
        elif mins <= 120:
            s += 26
        elif mins <= 180:
            s += 20
        elif mins <= 360:
            s += 14
        elif mins <= 600:
            s += 9
        else:
            s += 4
    return max(0, min(100, round(s)))


# ---------------------------------------------------------------- 周期任务
def find_repeat(text):
    """识别「每天 / 每晚 / 每周一 / 每月5号 / 每个工作日」-> dict 或 None
    返回 {"kind": daily|weekly|monthly|workday, "weekday": 0-6 或 None,
          "monthday": 1-31 或 None}
    """
    if not text:
        return None
    if re.search(r"(每个?工作日|周一到周五|工作日)", text):
        return {"kind": "workday", "weekday": None, "monthday": None}
    m = re.search(r"每个?\s*(?:周|星期|礼拜)\s*((?:[一二三四五六日天1-7][、,，和\s]*)+)", text)
    if m:
        # v1.9.9.27：「每周一三五」原来只认第一个「一」，「三五」被丢掉，
        # 变成「每周一」；顺带「周二四」也只算了周二。现在把这一段里
        # 所有星期几都收集起来，命中任一天就算今天该做。
        days = [WEEKDAY_MAP.get(c) for c in re.findall(r"[一二三四五六日天1-7]",
                                                       m.group(1))]
        days = [d for d in days if d is not None]
        if days:
            return {"kind": "weekly", "weekday": days[0],
                    "weekdays": days, "monthday": None}
    if re.search(r"(每个?周(?!\s*[一二三四五六日天1-7])|每星期(?!\s*[一二三四五六日天])|每礼拜(?!\s*[一二三四五六日天]))", text):
        return {"kind": "weekly", "weekday": None, "monthday": None}
    m = re.search(r"每个?月\s*(\d{1,2}|[一二三四五六七八九十]{1,3})\s*[号日]", text)
    if m:
        return {"kind": "monthly", "weekday": None, "monthday": _num(m.group(1))}
    if re.search(r"(每天|每日|每晚|每早|每天早|每天晚|天天|每一?天)", text):
        return {"kind": "daily", "weekday": None, "monthday": None}
    return None


def repeat_due_today(rep, d=None):
    """这个周期任务今天该不该出现"""
    if not rep:
        return False
    d = d or dt.date.today()
    k = rep.get("kind")
    if k == "daily":
        return True
    if k == "workday":
        return d.weekday() < 5
    if k == "weekly":
        wds = rep.get("weekdays")
        if wds:
            return d.weekday() in wds
        wd = rep.get("weekday")
        return True if wd is None else (d.weekday() == wd)
    if k == "monthly":
        md = rep.get("monthday") or 1
        return d.day == md
    return False


# ---------------------------------------------------------------- 分句
def split_segments(text):
    pat = "|".join(re.escape(x) for x in SPLIT_TOKENS) + "|" + "|".join(re.escape(x) for x in JOIN_VERBS)
    text = text or ""
    # v1.9.9.19：「~」「～」「—」「-」都是分割符/残留源，「9:00~11:00」
    # 会在 re.split 前就被拆开，区间保护形同虚设。先把「时间-时间」
    # 区间的连接符统一归一成「到」（「到」不是分割符），区间就能
    # 完整走到后面的保护逻辑。
    _T = (r"(?:\d{1,2}\s*[:：]\s*\d{1,2}|(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)"
          r"(?:\s*(?:钟|半|一刻|两刻|二刻|三刻|\d{1,2}\s*分?))?)" % CN_DIGIT)
    text = re.sub(r"(%s)\s*(?:[~～\-—]|~)\s*(%s)" % (_T, _T), r"\1到\2", text)
    # v1.9.9.29：「每周一、三、五跑步」里的顿号不是分句符，是星期几的
    # 连接符。先换成占位符，等分句完再还原——否则会被切成
    # 「每周一 / 三 / 五跑步」三条，标题碎成「每周一」「三」「五跑步」。
    _SEP = "\u0001"
    text = re.sub(r"((?:周|星期|礼拜)\s*[一二三四五六日天1-7])"
                  r"\s*[、,，]\s*(?=[一二三四五六日天1-7])",
                  lambda m: m.group(1) + _SEP, text)
    # 连写的第二、三个（周一、三、五 → 已替换成「周一\x01三、五」）
    for _ in range(5):
        text2 = re.sub(r"(" + _SEP + r"\s*[一二三四五六日天1-7])"
                       r"\s*[、,，]\s*(?=[一二三四五六日天1-7])",
                       lambda m: m.group(1) + _SEP, text)
        if text2 == text:
            break
        text = text2
    segs = []
    for part in re.split(pat, text):
        part = (part or "").strip().replace("\u0001", "、")
        if not part:
            continue
        # v1.9.9.18：时间区间先整体保护，不让它成为分割点。
        # 覆盖「三点到四点」「9点到11点」「9:00-11:00」「9:00至11:00」
        # 以及「上午9点到11点半」这类带时段词/分钟的组合。
        _RANGE_RE = (r"(?:上午|下午|中午|早上|早晨|晚上|今晚|明晚|傍晚|夜里|凌晨)?\s*"
                     r"(?:\d{1,2}\s*[:：]\s*\d{1,2}|(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)"
                     r"(?:\s*(?:钟|半|一刻|两刻|二刻|三刻|\d{1,2}\s*分?))?)\s*"
                     r"(?:到|至|-|~|～|—)\s*"
                     r"(?:\d{1,2}\s*[:：]\s*\d{1,2}|(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)"
                     r"(?:\s*(?:钟|半|一刻|两刻|二刻|三刻|\d{1,2}\s*分?))?)" % (CN_DIGIT, CN_DIGIT))
        _rng_m = list(re.finditer(_RANGE_RE, part))
        if _rng_m:
            r0, r1 = _rng_m[0].start(), _rng_m[-1].end()
            segs.append(part)          # 整段作为一条，不拆
            continue
        marks = list(re.finditer(r"\d{1,2}\s*[:：]\s*\d{1,2}|"
                                 r"(?:上午|下午|中午|早上|早晨|晚上|今晚|明晚|傍晚|夜里|凌晨)?\s*"
                                 r"(?:\d{1,2}|[%s]{1,3})\s*(?:点|時|时)" % CN_DIGIT, part))
        if len(marks) >= 2:
            cut = [0] + [m.start() for m in marks[1:]] + [len(part)]
            for i in range(len(cut) - 1):
                piece = part[cut[i]:cut[i + 1]].strip()
                if piece:
                    segs.append(piece)
            continue
        if len(marks) == 1 and marks[0].start() == 0:
            # 形如 "9:30 面试" —— 时间在前，任务在后
            rest = part[marks[0].end():].strip()
            if len(rest) >= 2:
                segs.append(marks[0].group(0) + rest)
                continue
        words = [w for w in re.split(r"\s+", part) if w]
        if len(words) >= 2 and all(len(w) >= 2 for w in words) \
                and not re.match(r"^\d", words[0]):
            # "开会 写方案" 这类空格分隔的多任务
            segs.extend(words)
        else:
            segs.append(part)
    return segs


NOT_TASK_WHOLE = ["你好", "您好", "hi", "hello", "嗨", "哈喽", "在吗", "在么", "谢谢", "多谢",
                  "好的", "好", "嗯", "哦", "ok", "okay", "收到", "明白", "知道了", "你是谁",
                  "怎么用", "帮助", "help", "早上好", "晚上好", "晚安", "再见", "还有", "另外",
                  "然后", "顺便", "马上", "尽快", "今天", "明天", "必须", "记得", "有空", "再说",
    "min", "mins", "minute", "minutes", "h", "hr", "hrs", "hour", "hours"]
MEANINGLESS = ["非常", "特别", "很", "一定", "必须", "务必", "记得", "马上", "立刻", "立即",
               "赶紧", "尽快", "紧急", "重要", "有空", "再说", "还有", "另外", "然后", "今天",
               "明天", "后天", "上午", "下午", "中午", "晚上", "之前", "以后", "一下", "的话",
               "优先级", "重要性", "重要程度", "重", "优先"]

GREET_RE = re.compile(r"(你好|您好|hi|hello|嗨|哈喽|在吗|在么|早上好|晚上好)", re.I)
THANKS_RE = re.compile(r"(谢谢|多谢|感谢|辛苦了)")
# v1.9.9.24：「还没做完 / 没完成 / 未完成」是否定陈述，不是勾选意图——
# 原来会掉进勾选分支，把后半句（「明天继续」）当任务名去找，回「没找到」
DONE_RE = re.compile(r"(?<!还没)(?<!没)(?<!未)(?:做完|完成|搞定|弄好|做好|结束|干完)")
DEL_RE = re.compile(r"(删除|删掉|去掉|取消)")
QUERY_RE = re.compile(r"(还剩|还有几|剩下|几件|多少件|进度|情况如何|怎么样|"
                      r"完成了多少|完成多少|做了多少|还有哪些没|什么没做)")

# v1.9.9.18：语气词/应答词归一化。用户随口打的「嗯嗯」「哦哦哦」
# 「谢谢啦」「可以的」「收到啦」都是对话语气，不是任务。
_TAIL_PARTICLES = "啦了啊呀吧哦喔呗嘛哈嗯哪咯喽"
_REPEAT_RE = re.compile(r"(.)\1+")
# 时间指代整句（「本周」「下周」）：只有时间没有事 → 不是任务
_TIME_ONLY_WORDS = {
    "本周", "这周", "下周", "上周", "本月", "这月", "下月", "上月",
    "今年", "明年", "去年", "本季度", "这个月", "下个星期", "这星期",
}


def _normalize_chat(text):
    """把口头应答压成简形：嗯嗯→嗯，哦哦哦→哦，谢谢啦→谢谢，可以的→可以"""
    t = (text or "").strip()
    t = re.sub(r"[\s，,。.：:;；!！?？~～]+", "", t)
    # 叠字压缩（只对纯口语短句做，避免「妈妈」「爸爸」被压坏）
    if len(t) <= 8:
        t = _REPEAT_RE.sub(r"\1", t)
    # 去掉句尾语气词（同样只对短句）
    if len(t) <= 8:
        t = t.rstrip(_TAIL_PARTICLES)
    return t


def _is_pure_chat(text):
    """整句只是应答/语气/时间指代 → 不该建任务"""
    raw = re.sub(r"[\s，,。.：:;；!！?？~～]+", "", text or "")
    # 先看未归一化的原形：「是啊 / 对啊」被归一化后只剩「是」，就查不到了
    if len(raw) <= 3 and re.fullmatch(r"(?:是|对|好|行|可|能|有|没)[啊呀哦吧呢嘛的了]", raw):
        return True
    # v1.9.9.28：纯语气/应答短句。「算了不用了」「好的」「嗯」「没事」
    # 原来会被切成「算了不用」记成任务——用户在自言自语、在婉拒，
    # 不是在派活。只对短句（≤8 字）生效；长句里的「算了」仍可能真是
    # 任务（「算了明天再买书」），不能一刀切。
    if len(raw) <= 8 and re.fullmatch(
            r"(?:算了|不用|不要|没事|好的|好吧|好|嗯+|哦+|噢+|啊+|呀+|行|可以|"
            r"知道了|明白|收到|谢谢|多谢|辛苦了|没关系|无所谓|都行|随便|"
            r"先这样|就这样)+了?", raw):
        return True
    t = _normalize_chat(text)
    if not t:
        return True
    if t in _TIME_ONLY_WORDS:
        return True
    if t in {_normalize_chat(w) for w in NOT_TASK_WHOLE}:
        return True
    # 「可以的 / 行的 / 没事的」：极短的「X的」且 X 是应答词
    if len(t) <= 4 and re.fullmatch(r"(?:可以|行|好|没事|算了|是的|对的)的?", t):
        return True
    # v1.9.9.24：天气寒暄（「今天天气不错」「外面下雨了」）不是任务；
    # 但带动作/安排的不拦（「下雨天记得带伞」仍可记）
    if re.search(r"天气(不错|很好|真好|挺好|不赖|好棒|太好了)", text or ""):
        return True
    # v1.9.9.25（P1）：问天气、说状态（「今天天气怎么样」「我累了」）也不是任务
    if re.search(r"天气(怎么样|如何|咋样|好吗|冷不冷|热不热)", text or ""):
        return True
    if len(t) <= 8 and re.fullmatch(r"(?:今天|明天)?天气(?:怎么样|如何|真好|不错)?", t):
        return True
    if re.fullmatch(r"(?:我|今天|真的|有点|好|太|很)*(?:累|困|饿|渴|烦|难受|无聊|开心|高兴)"
                    r"(?:了|啊|呀|呢|死)*", t):
        return True
    if len(t) <= 8 and re.fullmatch(r"(?:今天|明天|昨天)?天气(?:真|很|好)?(不错|好|棒)?", t):
        return True
    # v1.9.9.28：身体不适/情绪吐槽（「头疼」「好烦啊」「压力好大」）——
    # 用户是在抱怨，不是在派活。带明确动作的仍可记（「明天去医院看头疼」）。
    if len(t) <= 10 and re.fullmatch(
            r"(?:我|今天|最近|真的|有点|好|太|很|特别|超级|实在是)*"
            r"(?:头疼|头痛|不舒服|难受|累了|困了|烦死|烦|压力大|压力好大|"
            r"心情不好|不开心|沮丧|焦虑|emo)"
            r"(?:了|啊|呀|呢|死|死了|得很)*", t, re.I):
        return True
    # v1.9.9.28：查询语气。「我今天有什么安排」「明天要做什么」「这周还有什么」
    # 「我一共有多少任务」——句中有疑问词（什么/多少/几件…）且没有任何
    # 动作动词的短问句，是查询不是任务。带动作动词的不拦
    # （「明天要交什么报告」仍是任务）。
    if len(t) <= 18 and re.search(r"(什么|啥|多少|几个|几件|哪些|哪[个天条件])", t) \
            and not re.search(r"(买|写|交|去|开|给|发|打|学|看|读|背|练|洗|收|送|"
                              r"整理|准备|预约|联系|回复|提交|完成|带|约|订|修|搬)", t):
        return True
    return False

# 问助手自己是谁 / 让助手介绍自己
SELF_RE = re.compile(r"(你是谁|你叫(什么|啥|嘛)|你的名字|介绍(一下)?(你|你自己)|"
                     r"你能做(什么|啥)|你会(做)?什么|你是干什么的|"
                     r"who\s+are\s+you|your\s+name|introduce\s+yourself|"
                     r"what\s+can\s+you\s+do)", re.I)

# 自我介绍类说法里要剔掉的前后缀（提取昵称用）
_NAME_LEAD = ["你叫我", "你就叫我", "就叫我", "以后叫我", "请叫我", "可以叫我",
              "叫我", "我叫", "我的名字是", "我的名字叫", "名字是", "名字叫",
              "我是", "本人是", "本人叫", "称呼我", "称我", "喊我",
              "call me", "i am", "i'm", "my name is", "name's", "it's"]
_NAME_TAIL = ["吧", "就好", "就行了", "就成", "好了", "哈", "呀", "啊", "哦", "喔", "嘛",
              "同学", "先生", "女士", "小姐", "老师",
              # v1.9.9：「叫我老王就好了」曾被抠成「老王就」
              "就好了", "就行", "就得了", "也可以", "都没问题", "就"]
# 这些不是名字，是被误截进来的词
_NAME_BAD = ["谁", "什么", "啥", "吗", "呢", "你", "我", "他", "她", "它", "怎么", "怎样",
             "hello", "hi", "ok", "okay", "yes", "no", "谢谢", "好的",
             "你好", "您好", "在吗", "在么", "早上好", "中午好", "下午好", "晚上好",
             "晚安", "早安", "再见", "拜拜",
             "嗯", "哦", "嗯嗯", "随便", "都行", "不要", "算了", "不清楚", "不知道"]


def extract_name(text):
    """从「你叫我小李吧 / 我叫小李 / call me Alex」里抠出昵称；抠不到返回 None"""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    for lead in sorted(_NAME_LEAD, key=len, reverse=True):
        idx = low.find(lead)
        if idx < 0:
            continue
        rest = t[idx + len(lead):]
        # 逗号/句号/punctuation 之类直接截断
        rest = re.split(r"[，,。.！!？?；;：:\n\t]", rest)[0]
        rest = rest.strip().strip("\"'“”‘’「」【】《》 ")
        changed = True
        while changed and rest:
            changed = False
            for tail in sorted(_NAME_TAIL, key=len, reverse=True):
                if rest.endswith(tail) and len(rest) > len(tail):
                    rest = rest[:-len(tail)]
                    changed = True
        # 英文名允许间隔空格（Alex Chen），中文名一般 1~6 字
        rest = rest.strip()
        if not rest or len(rest) > 12:
            continue
        if rest.lower() in _NAME_BAD or rest in _NAME_BAD:
            continue
        if re.fullmatch(r"[0-9\W_]+", rest):
            continue
        # 纯英文：首字母大写好看点
        if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{0,11}", rest):
            rest = " ".join(w[:1].upper() + w[1:] for w in rest.split())
        return rest
    # 兜底：整句就是个短名字（用户只回了「小李」）
    # P0 问题4（v1.9.9.22）：含任务词的短句（交作业 / 开会 / 写报告）
    # 不是昵称，别收
    s = re.sub(r"[\s，,。.！!？?；;：:]+", "", t)
    if 1 <= len(s) <= 6 and s not in _NAME_BAD \
            and not re.search(r"[0-9]", s) and not SELF_RE.search(s) \
            and not re.search(r"帮我|记|提醒|开会|报告|作业|周报|邮件|买|写|发|去|做|"
                              r"交|分钟|小时|点|明天|今天|后天|周", s):
        return s
    return None


def _is_noise(title):
    """标题只剩虚词/时间词/指代词（如「这重要」）时视为无意义，并入上一条"""
    if len(title) < 2:
        return True
    rest = _remove_words(title, MEANINGLESS)
    # 指代词+程度词（这/那/它 + 非常重要）之类不是任务
    rest = _remove_words(rest, ["这", "那", "它"])
    rest = re.sub(r"[\s，,。.：:;；!！?？~～]+", "", rest)
    return len(rest) < 2


def _parse_dur_amount(text):
    """把「半小时 / 一个半小时 / 2小时 / 三十分钟 / 两刻钟」这类时长
    解析成 (数量, 单位)。识别不出返回 (0, None)。

    v1.9.9.18：原来用 `group(0)` 里做字符串 replace 判断「半」，
    「半小时」会被当成 0.5 又再 +0.5 变成 1 小时，「一个半小时」则
    完全丢掉那半。这里改成显式分支，顺序从长到短，绝不重叠匹配。"""
    units = r"(?:小时|分钟|秒)"
    # ① 「一个半小时 / 两个半小时 / 一个半钟头」
    m = re.search(r"(?:(\d+(?:\.\d+)?)|([%s]{1,3}))\s*个\s*半\s*(?:小时|钟头)"
                  % CN_DIGIT, text)
    if m:
        n = float(m.group(1)) if m.group(1) else float(_num(m.group(2)) or 0)
        return n + 0.5, "小时"
    # ② 「半小时 / 半钟头」
    if re.search(r"半\s*(?:个\s*)?(?:小时|钟头)", text):
        return 0.5, "小时"
    # ③ 「两刻钟 / 一刻钟」——先于「X分钟」判断，否则会被当成 2 分钟
    m = re.search(r"(?:([\d.]+)|([%s]{1,3}))\s*刻\s*钟" % CN_DIGIT, text)
    if m:
        n = float(m.group(1)) if m.group(1) else float(_num(m.group(2)) or 0)
        return n * 15, "分钟"
    # ④ 普通「数字 + 单位」
    m = re.search(r"([\d.]+)\s*" + units, text)
    if m:
        u = re.search(units, m.group(0)).group(0)
        return float(m.group(1)), u
    # ⑤ 中文数字 + 单位（「三十分钟」「两个小时」）
    m = re.search(r"([%s]{1,3})\s*个?\s*" % CN_DIGIT + units, text)
    if m:
        u = re.search(units, m.group(0)).group(0)
        return float(_num(m.group(1)) or 0), u
    return 0, None


def _is_priority_mod(seg):
    """整段只是一个优先级修饰语（很重要 / 非常紧急 / 马上 / 不急 …）

    v1.9.9.19：「9点开会 很重要」里的「很重要」被空格拆成独立段后，
    原来命中 NOT_TASK_WHOLE 直接丢弃，优先级完全没生效。现在识别出
    这类段，把分数并进上一条任务。"""
    t = re.sub(r"[\s，,。.！!？?~～]+", "", seg or "")
    if not t or len(t) > 6:
        return False
    t = re.sub(r"^(?:这个任务|这件事|这事|它|这个|这个|那个)", "", t)
    for w in list(IMPORTANT_WORDS) + list(URGENT_WORDS) + list(RELAX_WORDS):
        if t == w or t == w + "的" or t == "很" + w or t == "非常" + w \
                or t == "特别" + w or t == "挺" + w or t == "太" + w:
            return True
    return bool(re.fullmatch(r"(?:非常|特别|很|挺|好|太|真的|超)?"
                             r"(?:重要|紧急|要紧|急|火急|加急|不急|马上|立刻|立即|赶紧|尽快)的?", t))


def _soon_bonus(seg, dur):
    """「15分钟后 / 半小时之内 / 2小时内」这类**截止**表达的临近加分。

    v1.9.9.18：只有带「后/之后/以内/之内/内/截止」才算截止；
    「跑30分钟的步」「睡7小时」是纯时长（花多久干这事），不加分，
    否则什么任务一听「半小时」就变紧急，干扰排序。"""
    if not dur or not re.search(r"(?:后|之后|以内|之内|内|截止)", seg or ""):
        return 0
    _amt, _unit = _parse_dur_amount(seg)
    if not _unit:
        return 0
    # 统一折算成分钟再分档，避免「一个半小时」只按 1 小时算
    _mins = _amt * (1 / 60.0 if _unit == "秒"
                    else 1.0 if _unit == "分钟" else 60.0)
    # 加分要够「从 30 分基础分抬进目标档」：紧急≥75、重要≥55
    if _mins <= 30:
        return 50            # 30 分钟内 → 紧急（80）
    if _mins <= 60:
        return 45            # 1 小时内 → 紧急（75）
    if _mins <= 120:
        return 30            # 2 小时内 → 重要（60）
    if _mins <= 240:
        return 26            # 半天内 → 重要（56）
    if _mins <= 720:
        return 6             # 12 小时内 → 略提
    return 0


def parse_tasks(text, fallback=True):
    """解析成任务列表。fallback=True 时，一句朴素的话（如「去超市买牛奶」）
    即使没匹配到时间也当一件任务；fallback=False 用于「这像不像一句话任务」的判断。"""
    text = (text or "").strip()
    if not text:
        return []
    whole = re.sub(r"[\s，,。.：:;；!！?？~～]+", "", text)
    if whole in NOT_TASK_WHOLE:
        return []
    # v1.9.9.18：口头应答与纯时间指代（嗯嗯 / 谢谢啦 / 本周 / 可以的）不建任务
    if _is_pure_chat(text):
        return []
    # P0 问题1（v1.9.9.22）：撤回类指令（撤回一下 / 撤销刚才的 / 说错了）
    # 永远不能成为任务标题，即使主流程的撤回正则没接住
    if re.match(r"^[\s，,。]*(?:撤回|撤销|撤掉|撤消|退回|undo|revert|说错了|打错了|"
                r"输错了|刚才不算|重新记)", text, re.I) and len(whole) <= 12:
        return []
    # v1.9.9.24：进度提问（「今天还有什么没做」「我完成了多少」）是查询
    # 不是任务——否则 QUERY_RE 因 parsed_now 非空永远轮不到。
    # 只拦**疑问句式**（还有什么/哪些没做、完成多少），不拦「作业还没做」
    # 这种陈述
    if len(whole) <= 18 and re.search(
            r"还有什么没|还有什么任务|还有哪些没|哪些任务没|"
            r"完成了多少|完成多少|做了多少|还剩几件|还有几件没",
            text):
        return []
    results, seen = [], set()
    prev = None
    for seg in split_segments(text):
        # 「完成作业的优先级很重要」这类「XX的<评价>」：整体并入任务 XX
        m_de = re.match(r"^(.{1,8}?)的[^，。]{0,10}(?:重要|紧急|要紧|优先级|重要程度)", seg)
        if m_de:
            core = m_de.group(1)
            if prev is not None and _codes(core) and _codes(results[prev][0])[0:2] == _codes(core)[0:2] or prev is not None:
                prev_t = results[prev]
                t0, h0, raw0 = prev_t[0], prev_t[1], prev_t[3]
                d0 = prev_t[4]
                raw_new = raw0 + " " + seg
                results[prev] = (t0, h0, score_task(t0, raw_new, h0), raw_new, d0,
                                 prev_t[5] if len(prev_t) > 5 else None,
                                 prev_t[6] if len(prev_t) > 6 else None)
                continue
            seg = core   # 没有上一条时，把「的」前半段当任务本体
        clean_seg = re.sub(r"[\s，,。.：:；!！?？~～]+", "", seg)
        if len(clean_seg) < 2 or clean_seg in NOT_TASK_WHOLE:
            # v1.9.9.19：单独成段的优先级修饰语（「9点开会 很重要」里的
            # 「很重要」、「写作业 马上」里的「马上」）不丢弃，把分数并进
            # 上一条任务——标题一个字都不动，只改排序。
            if prev is not None and _is_priority_mod(clean_seg):
                prev_t = results[prev]
                t0, h0 = prev_t[0], prev_t[1]
                raw_new = prev_t[3] + " " + clean_seg
                results[prev] = (t0, h0, score_task(t0, raw_new, h0), raw_new,
                                 prev_t[4], prev_t[5],
                                 prev_t[6] if len(prev_t) > 6 else None)
            continue
        times = find_times(seg)
        hhmm, passed, offset = (times[0][0], times[0][1], times[0][3]) if times else (None, False, 0)
        dur, dur_raw = find_duration(seg)
        due_d, due_raw = find_deadline_date(seg)
        # 「两小时后出发」：时长本身要剔，但紧跟的「后」也得一起剔，
        # 否则会剩一句「后出发」。同理「3天后」。
        _hit_extra = []
        if dur_raw:
            _hit_extra.append(dur_raw + "后")
        # v1.9.9.17：时间词前面紧贴的「每」要一起清（每周一 → 周一），
        # 否则 clean_title 只删「周一」，标题里残留「每」
        _t_hits = [t[2] for t in times]
        for _h in list(_t_hits):
            _mh = re.search(r"每" + re.escape(_h), seg)
            if _mh:
                _t_hits.append(_mh.group(0))
        title = clean_title(seg, _t_hits + _hit_extra +
                            [r for r in (dur_raw, due_raw) if r])
        if _is_noise(title):
            # v1.9.9.18：这一段自带明确时间/日期，说明它是独立的一件事
            # （「凌晨两点睡，早上七点起」的后半句），不该并进上一条
            # P2 问题8（v1.9.9.22）：但纯时间（「开会 晚上8点」的
            # 「晚上8点」剔掉时间后一个汉字都不剩）不能独立成任务，
            # 仍并进上一条——只有剔完时间还剩实义字（「睡」「起」）才算独立
            _cn_left = len(re.sub(r"[^\u4e00-\u9fff]", "", title))
            # v1.9.9.25（P1）：「写周报，周五前交」里的「周五前交」只有
            # 「时间 + 单字动词」，没有自己的宾语 → 是前一条的**截止时间**，
            # 该并回上一条而不是新建任务。判定：剔完时间/时长/日期后
            # 剩余汉字 ≤ 2 且属于「交/做/完成/给」这类补语动词。
            _verb_tail = (_cn_left <= 2 and re.fullmatch(
                r"[交做给发写完成为办好弄好备用]", title or ""))
            if prev is not None and _verb_tail:
                prev_t = results[prev]
                _s_times = find_times(seg)
                _s_h = _s_times[0][0] if _s_times else None
                _s_due = find_deadline_date(seg)[0]
                raw_new = prev_t[3] + " " + seg
                results[prev] = (prev_t[0], prev_t[1] or _s_h,
                                 score_task(prev_t[0], raw_new,
                                            prev_t[1] or _s_h),
                                 raw_new, prev_t[4],
                                 prev_t[5] if len(prev_t) > 5 else None,
                                 _s_due or (prev_t[6] if len(prev_t) > 6 else None))
                continue
            if prev is not None and _cn_left >= 1 and (find_times(seg) or find_deadline_date(seg)[0]):
                # 标题太短（只剩一个「起」）就用原段兜底，别让用户看到单字任务
                if len(re.sub(r"[^\u4e00-\u9fff]", "", title)) < 2:
                    title = seg.strip()[:8] or title
                _st_times = find_times(seg)
                _st_hhmm = _st_times[0][0] if _st_times else None
                results.append((title, _st_hhmm,
                                score_task(title, seg, _st_hhmm),
                                seg, find_duration(seg)[0],
                                find_repeat(seg), find_deadline_date(seg)[0]))
                prev = len(results) - 1
                continue
            # v1.9.9.17：整段都是同一字重复（钟钟钟/水水水）→ 纯噪音，
            # 直接丢弃，不并进上一条污染标题
            if len(clean_seg) >= 2 and len(set(clean_seg)) == 1:
                continue
            # v1.9.9.17：标题被清洗成噪音（「凌晨两点睡」→「睡」），
            # 但段里带着有效时间/时长/日期信号 → 不能静默丢弃，
            # 用原段保底成任务，否则用户的合法输入直接消失
            if prev is None:
                _fb_times = find_times(seg)
                _fb_dur = find_duration(seg)[0]
                _fb_due = find_deadline_date(seg)[0]
                # 保底还需满足：时间词之外还有实义内容（如「凌晨两点睡」
                # 的「睡」）。只说「九点」这种纯时间不算任务
                _extra = seg.strip()
                for _h in [t[2] for t in _fb_times] + \
                          [r for r in (find_duration(seg)[1],
                                       find_deadline_date(seg)[1]) if r]:
                    _extra = _extra.replace(_h, "", 1)
                _extra = re.sub(r"[\s，,。.：:；!！?？~～]+", "", _extra)
                # v1.9.9.18：还要把残留的时间量词剔干净（「一刻」「三刻」
                # 里的「刻」原来是实义残留，导致纯时间句被误判成任务）
                _extra = re.sub(r"[刻分点钟時时半秒]", "", _extra)
                # 中文字符算实义（「睡」一个字就够），拉丁字母/数字不算
                _extra_cn = re.sub(r"[^\u4e00-\u9fff]", "", _extra)
                if (_fb_times or _fb_dur or _fb_due) and len(_extra_cn) >= 1:
                    # v1.9.9.18：优先用清洗后的 title（「一个小时内交」→「交」），
                    # 只有 title 实在不能用时才退回原段。单字中文（「交」）在这种
                    # 「时长+截止」句里是有效缩略，不算噪音。
                    _ok1 = (len(title) >= 2 and not _is_noise(title))
                    # 单字标题一律退回原文：清洗把「凌晨两点睡」压成「睡」、
                    # 「一个小时内交」压成「交」都是信息损失，原文更可读
                    _fb_title = (title if _ok1 else (seg.strip()[:10] or "待办"))
                    _fb_hhmm = _fb_times[0][0] if _fb_times else None
                    results.append((_fb_title, _fb_hhmm,
                                    min(100, score_task(_fb_title, seg, _fb_hhmm) +
                                        _soon_bonus(seg, _fb_dur)),
                                    seg, _fb_dur, find_repeat(seg), _fb_due))
                    prev = len(results) - 1
                    continue
            if prev is not None:
                prev_t = results[prev]
                t0, h0, raw0 = prev_t[0], prev_t[1], prev_t[3]
                d0 = prev_t[4]
                raw_new = raw0 + " " + seg
                seg_due = find_deadline_date(seg)[0]
                prev_due = prev_t[6] if len(prev_t) > 6 else None
                # ⚠ 噪音段里带的时间/日期要并入上一条：
                # 「参加舞会，今天上午11点25分之前，A」的 11:25 就丢在这
                # v1.9.9.18：h0 是上一条已有的时间，优先保留它；
                # 只有上一条没时间时才用这一段的时间（原写法反之，
                # 导致「凌晨两点睡，早上七点起」被改成 07:00）
                results[prev] = (t0, h0 or hhmm,
                                 score_task(t0, raw_new, h0 or hhmm, passed, offset),
                                 raw_new, d0 or dur,
                                 prev_t[5] if len(prev_t) > 5 else None,
                                 seg_due or prev_due)
            continue
        title = title[:24]
        if title in seen:
            continue
        seen.add(title)
        # v1.9.9.18：只有「15分钟后 / 半小时之内」这类**截止**表达才加
        # 临近分（纯时长不加），逻辑见 _soon_bonus
        _soon = _soon_bonus(seg, dur)
        results.append((title, hhmm,
                        min(100, score_task(title, seg, hhmm, passed, offset) + _soon),
                        seg, dur, find_repeat(seg), due_d))
        prev = len(results) - 1
    if not results and fallback:
        # 兜底：一句朴素的话（如「去超市买牛奶」）也当一件任务
        times = find_times(text)
        hhmm = times[0][0] if times else None
        dur, dur_raw = find_duration(text)
        due_d, due_raw = find_deadline_date(text)
        title = clean_title(text, [t[2] for t in times] +
                            [r for r in (dur_raw, due_raw) if r])
        title = re.sub(r"^(?:帮我|请|麻烦|记得|别忘了|我要|我想|需要|得|今天)+", "", title)[:24]
        if not _is_noise(title) and len(title) >= 2:
            results.append((title, hhmm, score_task(title, text, hhmm),
                            text, dur, find_repeat(text), due_d))
    return results


def priority_label(score):
    if score >= 75:
        return "紧急", "#E2434B"
    if score >= 55:
        return "重要", "#EE9A2B"
    if score >= 35:
        return "一般", "#3E8ED0"
    return "不急", "#8A8F98"
