"""Chinese (Simplified, Mandarin) quick commands - handled instantly, without waiting for Claude.

  计时器:  "设一个十分钟的计时器"  "煮面计时五分钟"  "计时一个半小时"
  提醒:    "二十分钟后提醒我关火"  "提醒我下午五点给妈妈打电话"  "半小时后提醒我休息"
  闹钟:    "明天早上七点叫醒我"  "设一个六点半的闹钟"
  查看/取消: "计时器还剩多久"  "我有哪些提醒"  "取消计时器"  "取消所有闹钟"
  专注:    "开始专注"  "番茄钟"  "专注五十分钟"  "专注还剩多久"  "结束专注"
  打开:    "打开记事本"  "打开B站"  "百度一下天气"
  例程:    "我有哪些例程"  "删除游戏模式例程"  (创建: "当我说电影时间的时候，打开网飞" -> 交给 Claude)
  后台:    "在后台帮我查一下……"
  简报:    "早上好"  "今日简报"
  反馈:    "我有个建议……"
"""
import datetime as dt
import re
import time
import urllib.parse
import webbrowser

# ---------- Chinese numbers ----------
_DIGITS = {"零": 0, "〇": 0, "一": 1, "幺": 1, "二": 2, "两": 2, "俩": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9}
NUM = r"[0-9零〇一幺二两俩三四五六七八九十百半]+"


def cn_int(text):
    """'二十五' -> 25, '十' -> 10, '两' -> 2, '15' -> 15. None if it isn't a number."""
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total, current = 0, 0
    for ch in text:
        if ch in _DIGITS:
            current = _DIGITS[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def parse_duration(text):
    """'一个半小时' -> 5400, '二十分钟' -> 1200, '十分半' -> 630, '半小时' -> 1800. Returns (seconds, matched)."""
    t = text
    total, spans = 0, []
    m = re.search(r"([0-9零〇一幺二两俩三四五六七八九十百]*)个?半(个)?(小时|钟头)", t)  # 半小时 / 一个半小时
    if m:
        hours = cn_int(m.group(1)) if m.group(1) else 0
        total += (hours or 0) * 3600 + 1800
        spans.append(m.group(0))
        t = t.replace(m.group(0), " ")
    for m in re.finditer(rf"({NUM})\s*(个)?\s*(小时|钟头|分钟|分|秒钟|秒)(半)?", t):
        n = cn_int(m.group(1))
        if n is None:
            continue
        unit = {"小时": 3600, "钟头": 3600, "分钟": 60, "分": 60, "秒钟": 1, "秒": 1}[m.group(3)]
        total += n * unit + (unit // 2 if m.group(4) else 0)
        spans.append(m.group(0))
    return (total, spans) if total else (None, [])


def parse_clock(text):
    """'明天早上七点半' / '下午5点15分' / '19:30' -> timestamp of the next such time, or None."""
    m = re.search(rf"(今天|明天|后天)?\s*(凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|夜里)?\s*({NUM})\s*[点:：时]\s*(半|一刻|三刻|{NUM})?\s*分?", text)
    if not m:
        return None
    hour = cn_int(m.group(3))
    minute_word = m.group(4)
    if hour is None or hour > 24:
        return None
    minute = {"半": 30, "一刻": 15, "三刻": 45}.get(minute_word or "", None)
    if minute is None:
        minute = cn_int(minute_word) if minute_word else 0
    if minute is None or minute > 59:
        return None
    period = m.group(2) or ""
    if period in ("下午", "傍晚", "晚上", "夜里") and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0
    now = dt.datetime.now()
    target = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    day = m.group(1)
    if day == "明天":
        target += dt.timedelta(days=1)
    elif day == "后天":
        target += dt.timedelta(days=2)
    elif target <= now:
        if not period and hour < 12 and (target + dt.timedelta(hours=12)) > now:
            target += dt.timedelta(hours=12)  # "七点" said at 3pm -> 7pm
        else:
            target += dt.timedelta(days=1)
    return target.timestamp(), m.group(0)


# ---------- Chinese wording for times ----------
def say_duration(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    out = ""
    if h:
        out += f"{h}小时"
    if m:
        out += f"{m}分钟"
    if s and not h:
        out += f"{s}秒"
    return out or "0秒"


def say_time(ts):
    t = dt.datetime.fromtimestamp(ts)
    h = t.hour
    period = "凌晨" if h < 6 else "早上" if h < 9 else "上午" if h < 12 else "中午" if h < 13 else "下午" if h < 18 else "晚上"
    h12 = h if h <= 12 else h - 12
    text = f"{period}{h12}点" + (f"{t.minute}分" if t.minute else "")
    today = dt.date.today()
    if t.date() == today + dt.timedelta(days=1):
        text = "明天" + text
    elif t.date() != today:
        text = f"{t.month}月{t.day}日" + text
    return text


def describe(item):
    name = item["label"] or {"timer": "计时器", "alarm": "闹钟", "reminder": "提醒"}[item["kind"]]
    left = item["due"] - time.time()
    if item["kind"] == "timer":
        return f"{name}还剩{say_duration(left)}"
    return f"{name}：{say_time(item['due'])}"


def fired_message(item):
    late = item.get("late", 0) > 90
    if item["kind"] == "alarm":
        return f"现在是{say_time(item['due'])}，你的闹钟响了。" + ("抱歉，闹钟到时我没在运行。" if late else "")
    if item["kind"] == "reminder":
        return f"提醒：{item['label'] or '你让我提醒你的事'}。" + ("（稍微晚了一点，抱歉。）" if late else "")
    if item["label"]:
        return f"{item['label']}的计时器到时间了。"
    return f"{say_duration(item['length'])}的计时器到时间了。" if item.get("length") else "计时器到时间了。"


def session_text(s):
    left = max(0, s["ends"] - time.time())
    m, sec = divmod(int(left), 60)
    return f"{'专注' if s['phase'] == 'focus' else '休息'} {m}:{sec:02d}  ·  第{s['round']}/{s['rounds']}轮"


def session_message(kind, **kw):
    return {
        "complete": "专注完成！共{rounds}轮，{total}分钟。干得漂亮。",
        "break": "休息{length}分钟吧，离开屏幕活动一下。",
        "long_break": "长休息{length}分钟，好好放松一下。",
        "resume": "休息结束。第{round}/{rounds}轮，{minutes}分钟，开始吧。",
    }[kind].format(**kw)


# ---------- helpers ----------
def _clean(text):
    t = text.strip()
    t = re.sub(r"^(嘿|嗨|哈喽|喂)?[，,\s]*(jarvis|贾维斯|wisp|sidekick)[，,\s]*", "", t, flags=re.I)
    t = re.sub(r"[。！？!?.，,\s]+$", "", t)
    return t.strip()


def _strip_label(text, *remove):
    for r in remove:
        if r:
            text = text.replace(r, "")
    text = re.sub(r"(帮我|请|麻烦|设置|设定|设|定|开始|一个|一下|个|的|计时器|倒计时|定时器|计时|闹钟|提醒我|提醒|之后|以后|后|吧|了|啊|呢)", "", text)
    text = re.sub(r"^(在|为|给我)", "", text)
    return text.strip(" ，,。")


# ---------- the commands ----------
YES = r"(好|好的|好啊|好呀|是|是的|对|可以|要|要的|需要|行|嗯|嗯嗯|没问题|来吧|当然|麻烦了|好的谢谢|好的，谢谢|请讲|说吧)"
NO = r"(不|不用|不要|算了|不需要|以后再说|不了|没事|不必|先不用|下次吧|不用了|不用了谢谢)"


def is_yes(text):
    return bool(re.fullmatch(YES + r"[吧啊呀的，,。！!]*", _clean(text)))


def is_no(text):
    return bool(re.fullmatch(NO + r"[吧啊呀的，,。！!]*", _clean(text)))


def is_briefing(text):
    return bool(re.fullmatch(r"(早上好|早安|早|今日简报|今天的简报|简报|给我简报|今天有什么安排|今天怎么样)[吧啊呀，,。！!]*", _clean(text)))


def background_task(text):
    m = re.match(r"^(请|帮我)?(在后台帮我|后台帮我|在后台|放到后台|后台运行|后台处理)[，,：:\s]*(帮我)?(.+)$", _clean(text))
    return m.group(4).strip() if m else None


def wants_feedback(text):
    m = re.match(r"^(我)?(有个|有一个|想提个|提个|想提一个)?(建议|意见|反馈|问题要反馈)[：:，,\s]*(.*)$", _clean(text))
    if m and (m.group(2) or m.group(1) or "反馈" in m.group(3)):
        return m.group(4) or ""
    m = re.match(r"^(发送|提交|我要|我想)(反馈|建议)[：:，,\s]*(.*)$", _clean(text))
    return (m.group(3) or "") if m else None


def wants_routine_builder(text):
    t = _clean(text)
    return bool(re.search(r"(当|每当|如果|只要|一旦)我(说|讲|喊)|我(一)?说.{1,20}(就|你就)|"
                          r"(创建|新建|添加|做|建|设置)(一个)?(新的)?例程|(修改|改一下|更改|编辑|重命名|更新).{0,20}例程|"
                          r"(把|将).{1,40}(加到|加入|添加到|从).{0,20}例程", t))


OPEN_NAMES = {  # Chinese name -> the English name the shortcut table knows
    "记事本": "notepad", "文本编辑": "notepad", "计算器": "calculator", "设置": "settings", "系统设置": "settings",
    "任务管理器": "task manager", "活动监视器": "task manager", "文件管理器": "file explorer",
    "资源管理器": "file explorer", "文件夹": "file explorer", "访达": "file explorer", "浏览器": "chrome",
    "谷歌浏览器": "chrome", "chrome": "chrome", "edge": "edge", "火狐": "firefox", "终端": "terminal",
    "命令行": "terminal", "word": "word", "excel": "excel", "ppt": "powerpoint", "幻灯片": "powerpoint",
    "邮件": "outlook", "日历": "calendar", "相机": "camera", "时钟": "clock", "应用商店": "store",
    "spotify": "spotify", "steam": "steam", "discord": "discord", "音乐": "music", "备忘录": "notes",
}
OPEN_PROTOCOLS = {"微信": "weixin://", "qq": "tencent://"}
SITES = {"百度": "https://www.baidu.com", "b站": "https://www.bilibili.com", "哔哩哔哩": "https://www.bilibili.com",
         "淘宝": "https://www.taobao.com", "京东": "https://www.jd.com", "知乎": "https://www.zhihu.com",
         "微博": "https://weibo.com", "抖音": "https://www.douyin.com", "小红书": "https://www.xiaohongshu.com",
         "优酷": "https://www.youku.com", "爱奇艺": "https://www.iqiyi.com", "网易云音乐": "https://music.163.com",
         "谷歌": "https://www.google.com", "油管": "https://www.youtube.com", "youtube": "https://www.youtube.com",
         "gmail": "https://mail.google.com", "github": "https://github.com", "网飞": "https://www.netflix.com"}


def _open(text):
    import shortcuts
    import sysplat
    t = _clean(text).lower()
    m = re.match(r"^(百度一下|用百度搜索?|百度搜索?)(.+)$", t)
    if m:
        webbrowser.open("https://www.baidu.com/s?wd=" + urllib.parse.quote(m.group(2).strip()))
        return f"正在百度搜索{m.group(2).strip()}。"
    m = re.match(r"^(谷歌一下|用谷歌搜索?|谷歌搜索?)(.+)$", t)
    if m:
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(m.group(2).strip()))
        return f"正在谷歌搜索{m.group(2).strip()}。"
    m = re.match(r"^(请|帮我)?(打开|启动|开一下|打开一下|运行)(一下)?(.+?)(吧|一下)?$", t)
    if not m or re.search(r"(和|然后|并且|再|接着)", m.group(4)):
        return None  # several steps: Claude handles it
    name = m.group(4).strip()
    shown = _clean(text)[-len(name) - (len(m.group(5)) if m.group(5) else 0):][:len(name)] or name  # original letters
    if name in SITES:
        webbrowser.open(SITES[name])
        return f"正在打开{shown}。"
    if name in OPEN_PROTOCOLS:
        try:
            sysplat.open_target(OPEN_PROTOCOLS[name])
            return f"正在打开{shown}。"
        except Exception:
            return None
    english = OPEN_NAMES.get(name)
    if english and shortcuts.try_shortcut(f"open {english}"):
        return f"正在打开{shown}。"
    return None


def _timers(text):
    import timers
    t = _clean(text)
    if not re.search(r"(计时|倒计时|定时|闹钟|叫醒|提醒|叫我起床)", t):
        return None
    # cancel
    if re.search(r"(取消|关掉|关闭|删除|删掉|停止|停掉|不要)", t):
        items = timers.upcoming()
        if not items:
            return "你现在没有计时器或提醒。"
        if re.search(r"(所有|全部|都)", t) or len(items) == 1:
            timers.cancel("all")
            return "已取消。" if len(items) == 1 else f"已取消全部{len(items)}个。"
        for item in items:
            if item["label"] and item["label"] in t:
                timers.cancel(item["id"])
                return f"已取消{item['label']}。"
        kind = "alarm" if re.search("闹钟|叫醒", t) else "reminder" if "提醒" in t else "timer"
        match = [i for i in items if i["kind"] == kind] or items
        timers.cancel(match[0]["id"])
        return f"已取消{match[0]['label'] or {'timer': '计时器', 'alarm': '闹钟', 'reminder': '提醒'}[match[0]['kind']]}。"
    # status
    if re.search(r"(还剩|还有多久|剩多少|多久|哪些|什么|几个|查看|列出)", t) and not re.search(r"提醒我", t):
        items = timers.upcoming()
        if not items:
            return "你现在没有计时器或提醒。"
        return "；".join(describe(i) for i in items[:4]) + "。"
    # alarm or reminder at a clock time
    clock = parse_clock(t)
    if clock and re.search(r"(闹钟|叫醒|叫我起床|提醒)", t):
        when, matched = clock
        if re.search(r"(闹钟|叫醒|叫我起床)", t):
            timers.add(at=when, kind="alarm")
            return f"闹钟已设在{say_time(when)}。"
        label = _strip_label(t, matched, "提醒我")
        timers.add(at=when, label=label, kind="reminder")
        return f"好的，我会在{say_time(when)}提醒你{label}。" if label else f"好的，我会在{say_time(when)}提醒你。"
    # timer / reminder after a duration
    seconds, spans = parse_duration(t)
    if not seconds:
        return None
    if "提醒" in t:
        label = _strip_label(t, *spans)
        timers.add(seconds=seconds, label=label, kind="reminder")
        return f"好的，{say_duration(seconds)}后提醒你{label}。" if label else f"好的，{say_duration(seconds)}后提醒你。"
    label = _strip_label(t, *spans)
    timers.add(seconds=seconds, label=label, kind="timer")
    return f"{label + '的' if label else ''}计时器已设好，{say_duration(seconds)}。"


def _focus(text):
    import focus
    t = _clean(text)
    if not re.search(r"(专注|番茄钟|番茄工作法|学习时段)", t):
        return None
    if re.search(r"(结束|停止|取消|退出|关掉)", t):
        return "专注已结束。" if focus.stop_session() else "现在没有进行中的专注。"
    if re.search(r"(还剩|多久|状态|第几轮)", t):
        s = focus.get_state().get("session")
        return session_text(s) if s else "现在没有进行中的专注。"
    if re.search(r"今天.*(专注|学)了?多久", t):
        m = int(focus.focus_minutes_today())
        return f"你今天专注了{m}分钟。" if m else "今天还没有专注记录。"
    seconds, _ = parse_duration(t)
    minutes = seconds / 60 if seconds else 25
    rounds = 1 if seconds else 4
    m = re.search(rf"({NUM})\s*(轮|个番茄)", t)
    if m and cn_int(m.group(1)):
        rounds = cn_int(m.group(1))
    focus.start_session(minutes, 5, rounds)
    return f"专注开始：{int(minutes)}分钟" + (f"，共{rounds}轮，每轮休息5分钟。" if rounds > 1 else "。")


def _routines(text):
    import routines
    t = _clean(text)
    if re.search(r"(哪些|什么|列出|看看|我的)例程", t) and not re.search(r"(删除|删掉|去掉)", t):
        data = routines.load()
        if not data:
            return "你还没有例程。试试说「当我说电影时间的时候，打开网飞」。"
        return f"你有{len(data)}个例程：" + "、".join(data) + "。"
    if re.search(r"(删除|删掉|去掉|不要|忘掉|取消)", t) and re.search(r"(例程|当我说)", t):
        name = routines._find_by_mention(routines._norm(t))
        if not name:
            return "没听出是哪个例程。可以说「我有哪些例程」来查看。"
        data = routines.load()
        data.pop(name, None)
        routines.save(data)
        return f"已删除「{name}」例程。"
    return None


def _bare_status(text):
    """ "还剩多久？" with nothing else: answer from whatever is running."""
    if not re.fullmatch(r"(还剩|还有|剩)(多久|多长时间|多少时间|几分钟)(了|呢|啊)?", _clean(text)):
        return None
    import focus
    import timers
    session = focus.get_state().get("session")
    if session:
        return session_text(session)
    items = timers.upcoming()
    if items:
        return "；".join(describe(i) for i in items[:4]) + "。"
    return None


def handle_command(text):
    """Instant Chinese commands. Returns (what to say, feature name) or None."""
    reply = _bare_status(text)
    if reply:
        return reply, "timer"
    for handler, feature in ((_timers, "timer"), (_focus, "focus_session"), (_routines, "routine"), (_open, "shortcut")):
        try:
            reply = handler(text)
        except Exception as exc:
            print(f"(Chinese command error: {exc})")
            reply = None
        if reply:
            return reply, feature
    return None
