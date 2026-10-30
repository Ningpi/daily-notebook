# -*- coding: utf-8 -*-
"""
每日记事本 —— 哲言库

每完成一项任务，从库里取一句递给你。
取法：把整张表洗牌后按顺序发，发完一轮才重新洗牌，
      因此同一轮内绝不重复；跨轮之间再用「最近若干句」二次避让。

素材参考：人民日报金句、村上春树、杨绛、罗曼·罗兰等常见公开励志语句，
以及「人生缓缓，自有答案」「唯有热爱，能抵岁月漫长」一类流传短句，
经筛选与精简，统一为 8~20 字、偏温柔不说教的语气。
"""
import random

QUOTES = [
    # —— 慢与从容
    "人生缓缓，自有答案。",
    "慢慢来，比较快。",
    "不慌不忙，是一种底气。",
    "以欢喜之心，慢度日常。",
    "心静了，路就清楚了。",
    "稳住，事情会自己变清楚。",
    "日子还长，不必慌张。",
    "万事尽心，余下的交给时间。",
    "所有的好运，都在路上。",
    "急不得的事，就慢慢做。",

    # —— 热爱与坚持
    "唯有热爱，能抵岁月漫长。",
    "热爱可抵岁月漫长，温柔可挡艰难时光。",
    "喜欢的事，做久了会发光。",
    "把喜欢的事做久一点。",
    "星光不问赶路人，时光不负有心人。",
    "那些不起波澜的日复一日，终会让你看到坚持的意义。",
    "坚持不是硬撑，是还想再试一次。",
    "一分耕耘，一分收获，从来不是空话。",
    "路虽远，行则将至；事虽难，做则必成。",
    "山再高，往上攀总能登顶。",
    "先跑起来，再慢慢调整呼吸。",
    "不必完美，先完成。",
    "做完了，就已经赢过昨天的自己。",
    "今天多做一点，明天就轻一点。",

    # —— 行动与答案
    "想，都是问题；做，才有答案。",
    "先开始，剩下的路上再说。",
    "答案不在想里，在做的过程里。",
    "动手之后，焦虑就少了一半。",
    "种一棵树最好的时间是十年前，其次是现在。",
    "与其等风来，不如追风去。",
    "进一寸，有一寸的欢喜。",
    "小事做扎实，大事自然来。",
    "把今天过好，就是最好的规划。",
    "一步一个脚印，也算在往前走。",

    # —— 自我与成长
    "你未必光芒万丈，但始终温暖有光。",
    "你是自己人生的导演，剧本由你写。",
    "接纳不完美的自己，也是一种勇敢。",
    "不必活成别人期待的样子。",
    "成长，是和自己好好相处。",
    "允许自己慢一点，也允许自己累。",
    "你已经比想象中做得更好。",
    "照顾好自己，才有余力照顾别的。",
    "先做自己的太阳，再去照亮别人。",
    "值得被温柔以待，包括被自己。",

    # —— 心态与释然
    "凡是过往，皆为序章。",
    "不乱于心，不困于情。",
    "不念过往，不畏将来。",
    "走过的路，都算数。",
    "一念放下，万般自在。",
    "有些遗憾，是另一种成全。",
    "风来听风，雨来听雨。",
    "尽力就好，其余随缘。",
    "把心放宽，路就宽了。",
    "今天的不开心，到此为止。",
    "太阳下山，还有月光。",
    "能扛住的日子，都会变成底气。",

    # —— 微光与希望
    "万物皆有裂痕，那是光照进来的地方。",
    "黑夜再长，白昼总会到来。",
    "躲起来的星星，也在努力发光。",
    "风吹哪页读哪页。",
    "轻舟已过万重山。",
    "平芜尽处是春山。",
    "每一次归程，都是为了更好出发。",
    "走过的风雨，都会变成故事。",
    "花开有期，你的花期也会来。",
    "生活不是等待暴风雨过去，而是学会在雨中跳舞。",

    # —— 踏实与积累
    "所有向上的生长，都来自向下的扎根。",
    "厚积，才能薄发。",
    "把简单的事做到极致，就是本事。",
    "日拱一卒，功不唐捐。",
    "积累的力量，往往最后才显形。",
    "把每一件小事做好，就是不简单。",
    "不积跬步，无以至千里。",
    "慢慢沉淀，认真生活。",
    "功夫到了，水到渠成。",
    "认真做事的人，运气不会太差。",

    # —— 温柔与关系
    "知世故而不世故。",
    "温柔一点，世界也会温柔一些。",
    "先照顾好自己的情绪，再谈其他。",
    "不苛求别人，不为难自己。",
    "把善意先留给自己一份。",
    "理解别人，也释怀自己。",
    "你值得所有温柔。",

    # —— 收束与自勉
    "今天也算好好活过了。",
    "做完一件，就少一件。",
    "每一步都算数，包括这一步。",
    "把日子过成自己喜欢的样子。",
    "认真生活的人，总会被生活看见。",
    "所有的坚持，最后都会开花。",
    "你正在成为更好的自己。",
    "别急，好的都在后头。",
    "此刻的努力，未来的底气。",
    "辛苦了，这一件做得很好。",
]

# ----------------------------------------------------------------- 英文语录
# 与原句一一对应（同一主题、同一语气），保持中英两套语感一致。
QUOTES_EN = [
    # —— Slowness
    "Slow down — the answer will come.",
    "Slow is smooth, smooth is fast.",
    "Calm is its own kind of strength.",
    "Take the ordinary days slowly, with joy.",
    "When the mind quiets, the path clears.",
    "Steady. Things will sort themselves out.",
    "There's a long road ahead. No need to rush.",
    "Do your part; leave the rest to time.",
    "Good things are on their way.",
    "What can't be rushed, do slowly.",

    # —— Love & persistence
    "What you love outlasts the years.",
    "Love outlasts the years; gentleness outlasts hard times.",
    "Do what you love long enough and it begins to shine.",
    "Keep at the thing you love a little longer.",
    "The stars ask nothing of the traveler; time rewards the devoted.",
    "Those uneventful days will one day show you why you kept going.",
    "Persistence isn't gritting your teeth — it's wanting one more try.",
    "No effort, no harvest. That was never just a saying.",
    "The road is long, but walking gets you there; the task is hard, but doing finishes it.",
    "However high the mountain, climbing gets you to the top.",
    "Start running first, then find your breath.",
    "Done beats perfect.",
    "Finishing this already beats yesterday's you.",
    "A little more today makes tomorrow lighter.",

    # —— Action & answers
    "Thinking makes problems; doing makes answers.",
    "Just start. We'll figure out the rest on the way.",
    "The answer isn't in your head — it's in the doing.",
    "Once you begin, half the worry is gone.",
    "The best time to plant a tree was ten years ago. The next best is now.",
    "Don't wait for the wind — chase it.",
    "An inch of progress is an inch of joy.",
    "Do small things well and big things follow.",
    "Live today well; that's the best plan there is.",
    "One footprint at a time is still moving forward.",

    # —— Self & growth
    "You may not blaze, but you always carry light.",
    "You direct your own life; you write the script.",
    "Accepting your imperfect self is a form of courage.",
    "You don't have to become what others expect.",
    "Growing up is learning to live well with yourself.",
    "It's okay to go slower. It's okay to be tired.",
    "You're doing better than you think.",
    "Take care of yourself first — then you'll have more to give.",
    "Be your own sun before you light the way for others.",
    "You deserve gentleness — including your own.",

    # —— Perspective
    "What's past is prologue.",
    "Calm heart, unbound feelings.",
    "Don't dwell on the past; don't fear the future.",
    "Every road you walked still counts.",
    "Let go once, and everything loosens.",
    "Some regrets are another kind of gift.",
    "Let the wind blow; let the rain fall.",
    "Do your best; let the rest be.",
    "Open your heart, and the road widens.",
    "Today's unhappiness ends here.",
    "When the sun sets, the moon is still there.",
    "The days you carry become your strength.",

    # —— Light & hope
    "There's a crack in everything — that's how the light gets in.",
    "However long the night, day always comes.",
    "Even hidden stars are still trying to shine.",
    "Read whichever page the wind turns to.",
    "The light boat has passed ten thousand mountains.",
    "Beyond the flat plains, spring hills await.",
    "Every return is for a better departure.",
    "The storms you walk through become your stories.",
    "Flowers have their season — yours will come.",
    "Life isn't about waiting for the storm to pass; it's learning to dance in the rain.",

    # —— Groundwork
    "All upward growth comes from roots below.",
    "Deep roots, sudden bloom.",
    "Doing simple things supremely well is a skill.",
    "One small step a day; no effort is wasted.",
    "The power of accumulation only shows up at the end.",
    "Do every small thing well — that's not small at all.",
    "No single step covers a thousand miles.",
    "Settle slowly; live deliberately.",
    "When the work is done, the water finds its channel.",
    "People who do things carefully tend to get lucky.",

    # —— Gentleness
    "Know the world, but don't become it.",
    "Be gentle, and the world turns gentler too.",
    "Tend to your own feelings before anything else.",
    "Don't demand of others; don't torment yourself.",
    "Save a share of kindness for yourself.",
    "Understand others; release yourself.",
    "You deserve all the gentleness there is.",

    # —— Closing
    "Today counted as a day well lived.",
    "One done is one less to carry.",
    "Every step counts — including this one.",
    "Live the days the way you like them.",
    "People who live earnestly get noticed by life.",
    "All persistence eventually blooms.",
    "You're becoming a better version of yourself.",
    "No rush — the good part comes later.",
    "Today's effort is tomorrow's confidence.",
    "That was well done. Take a breath.",
]


class QuoteDeck(object):
    """洗牌发牌式抽取：一轮内绝不重复，跨轮避开最近若干句"""

    def __init__(self, quotes=None, avoid_recent=18):
        self.quotes = list(quotes or QUOTES)
        self.avoid = min(avoid_recent, max(0, len(self.quotes) - 3))
        self.recent = []          # 最近发出的（末尾最新）
        self.pool = []            # 本轮剩余
        self._reshuffle()

    def _reshuffle(self, first=None):
        pool = list(self.quotes)
        if first is not None and first in pool:
            pool.remove(first)
        random.shuffle(pool)
        self.pool = pool

    def draw(self):
        if not self.quotes:
            return ""
        if not self.pool:
            # 新一轮：把最近几句排到末尾，避免刚说完又说一遍
            tail = [q for q in self.quotes if q in self.recent[-self.avoid:]]
            head = [q for q in self.quotes if q not in tail]
            if len(head) <= 2:
                # 句子太少时退化为完全洗牌
                self._reshuffle()
            else:
                random.shuffle(head)
                random.shuffle(tail)
                self.pool = head + tail
        q = self.pool.pop(0)
        self.recent.append(q)
        if len(self.recent) > max(self.avoid * 2, 30):
            self.recent = self.recent[-self.avoid * 2:]
        return q


class DeckSet(object):
    """中英各一副牌，互不干扰：中文模式下只发中文，英文模式下只发英文"""

    def __init__(self, avoid_recent=18):
        self.avoid = avoid_recent
        self.decks = {
            "zh": QuoteDeck(QUOTES, avoid_recent),
            "en": QuoteDeck(QUOTES_EN, avoid_recent),
        }

    def deck(self, lang):
        return self.decks.get("en" if lang == "en" else "zh")

    def draw(self, lang):
        return self.deck(lang).draw()

    def seed_recent(self, lang, items):
        """把历史发过的句子塞回去，避免重启后又重复"""
        d = self.deck(lang)
        for q in (items or []):
            if q in d.quotes:
                d.recent.append(q)


def all_quotes(lang="zh"):
    return list(QUOTES_EN if lang == "en" else QUOTES)
