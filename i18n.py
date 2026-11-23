"""Translations. Set "language" in config.json (or Settings): "en" (English) or "zh" (Simplified Chinese).

Use:  from i18n import t;  t("timer_set", label="Pasta", duration="10 minutes")
To add a language: add its code to LANGUAGES and a translation next to each "en" below.
Anything missing falls back to English.
"""
import json
from pathlib import Path

LANGUAGES = {"en": "English", "zh": "中文 (简体)"}
LANG = "en"


def load_language():
    """Read the language from config.json (called once at startup)."""
    global LANG
    try:
        cfg = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8"))
        LANG = cfg.get("language", "en") if cfg.get("language", "en") in LANGUAGES else "en"
    except (OSError, json.JSONDecodeError):
        LANG = "en"
    return LANG


def is_zh():
    return LANG == "zh"


def t(name, /, **kw):
    entry = STRINGS.get(name)
    if entry is None:
        return name.format(**kw) if kw else name
    text = entry.get(LANG) or entry["en"]
    return text.format(**kw) if kw else text


# Per-language defaults applied when someone switches language
LANGUAGE_DEFAULTS = {
    "en": {"whisper_model": "base.en", "edge_voice": "en-GB-RyanNeural", "mac_voice": "Daniel", "windows_voice": "",
           "thinking_acks": ["One moment.", "Right away.", "On it.", "Just a moment."]},
    "zh": {"whisper_model": "small", "edge_voice": "zh-CN-YunxiNeural", "mac_voice": "Tingting",
           "windows_voice": "Microsoft Huihui Desktop", "thinking_acks": ["稍等。", "马上。", "好的，这就去办。", "请稍候。"]},
}

STRINGS = {
    # ---------- status words (HUD) ----------
    "status_starting": {"en": "INITIALISING", "zh": "启动中"},
    "status_ready": {"en": "ONLINE", "zh": "在线"},
    "status_listening": {"en": "LISTENING", "zh": "聆听中"},
    "status_thinking": {"en": "PROCESSING", "zh": "处理中"},
    "status_speaking": {"en": "SPEAKING", "zh": "说话中"},

    # ---------- engine messages ----------
    "app_control_missing": {"en": "App control (Windows-MCP) isn't installed, so I can't click around in apps. Run setup.bat.",
                            "zh": "未安装应用控制（Windows-MCP），我暂时无法操作其他应用。请运行 setup.bat。"},
    "stopped": {"en": "Stopped.", "zh": "已停止。"},
    "new_chat": {"en": "Started a fresh conversation. (Things saved to memory are kept.)",
                 "zh": "已开始新对话。（记忆中的内容会保留。）"},
    "queued": {"en": "Queued - I'll do it after the current task.", "zh": "已排队，完成当前任务后马上处理。"},
    "error_generic": {"en": "Error: {error}", "zh": "出错了：{error}"},
    "briefing_offer": {"en": "Good morning{name}. Would you like your briefing?", "zh": "早上好{name}。需要听今天的简报吗？"},
    "very_well": {"en": "Very well.", "zh": "好的。"},
    "background_started": {"en": "Okay, I'm working on that in the background. Job {job}.",
                           "zh": "好的，我在后台处理这件事。任务编号 {job}。"},
    "conversation_reset": {"en": "It's been a while, so I started a fresh conversation. (Memory is kept.)",
                           "zh": "隔了一段时间，所以我开始了新对话。（记忆会保留。）"},
    "something_wrong": {"en": "Something went wrong, sorry. The details are in wisp.log.",
                        "zh": "抱歉，出了点问题。详情见 wisp.log。"},
    "usage_limit": {"en": "You've hit your Claude usage limit, so I can't think for a bit.{when} Timers, routines and quick commands still work.",
                    "zh": "你的 Claude 用量已达上限，我暂时无法思考。{when}计时器、例程和快捷指令仍然可用。"},
    "usage_limit_when": {"en": " It resets at {time}.", "zh": "将在 {time} 重置。"},
    "not_logged_in": {"en": "Claude isn't connected. Open Settings and add your Anthropic API key.",
                      "zh": "Claude 未连接。请打开设置，填写你的 Anthropic API 密钥。"},
    "no_internet": {"en": "I couldn't reach Claude. Check your internet connection.", "zh": "无法连接 Claude，请检查网络。"},
    "loading_speech": {"en": "Loading speech model '{model}' (the first run downloads it)...",
                       "zh": "正在加载语音识别模型「{model}」（首次运行需要下载）……"},
    "voice_off": {"en": "Voice is off ({error}). You can still type.", "zh": "语音不可用（{error}），你仍然可以打字。"},
    "voice_ready": {"en": "Voice ready: hold {key} (or click the orb) to talk.", "zh": "语音已就绪：按住 {key}（或点击光球）说话。"},
    "hotkeys_off": {"en": "Hotkeys are off ({error}). Use the mic button instead.", "zh": "快捷键不可用（{error}），请点击光球说话。"},
    "wake_missing": {"en": "Wake word is off: the openwakeword package isn't installed.", "zh": "唤醒词未启用：缺少 openwakeword 组件。"},
    "wake_off": {"en": "Wake word is off ({error}).", "zh": "唤醒词未启用（{error}）。"},
    "wake_ready": {"en": "Say “{phrase}” any time to talk.", "zh": "随时说 “{phrase}” 即可开始对话。"},
    "didnt_catch": {"en": "Didn't catch that.", "zh": "没听清。"},
    "yes": {"en": "Yes?", "zh": "我在。"},
    "click_to_talk": {"en": "Click the orb or hold {key} to talk.", "zh": "点击光球或按住 {key} 说话。"},
    "working_in_apps": {"en": "Working in your apps…", "zh": "正在操作你的应用……"},
    "update_available": {"en": "{app} {version} is available. Right-click the orb > Update now.",
                         "zh": "{app} {version} 已发布。右键点击光球 > 立即更新。"},
    "update_notify": {"en": "Version {version} is available. Right-click the orb to update.",
                      "zh": "新版本 {version} 已发布，右键点击光球即可更新。"},
    "job_done_title": {"en": "Wisp job done", "zh": "Wisp 后台任务完成"},
    "job_failed_title": {"en": "Wisp job failed", "zh": "Wisp 后台任务失败"},
    "job_failed": {"en": "The background job failed.", "zh": "后台任务失败了。"},
    "screen_note": {"en": "Looking at your screen…", "zh": "正在查看你的屏幕……"},
    "clipboard_note": {"en": "Reading your clipboard…", "zh": "正在读取剪贴板……"},
    "image_note": {"en": "Looking at the image you copied…", "zh": "正在查看你复制的图片……"},
    "routine_building": {"en": "setting it up", "zh": "正在设置"},
    "feedback_opened": {"en": "I've opened the feedback form. Check it, then press Send.", "zh": "已打开反馈表，确认后点击发送即可。"},

    # ---------- steps shown while working ----------
    "step_WebSearch": {"en": "Searching the web", "zh": "正在搜索网络"},
    "step_WebFetch": {"en": "Reading", "zh": "正在阅读"},
    "step_Bash": {"en": "Running", "zh": "正在运行"},
    "step_PowerShell": {"en": "Running", "zh": "正在运行"},
    "step_Read": {"en": "Reading", "zh": "正在读取"},
    "step_Write": {"en": "Writing", "zh": "正在写入"},
    "step_Edit": {"en": "Editing", "zh": "正在编辑"},
    "step_Glob": {"en": "Finding files", "zh": "正在查找文件"},
    "step_Grep": {"en": "Searching files", "zh": "正在搜索文件"},
    "step_TodoWrite": {"en": "Planning", "zh": "正在规划"},
    "step_Task": {"en": "Delegating", "zh": "正在分派任务"},
    "step_App": {"en": "Opening app", "zh": "正在打开应用"},
    "step_Click": {"en": "Clicking", "zh": "正在点击"},
    "step_Type": {"en": "Typing", "zh": "正在输入"},
    "step_Snapshot": {"en": "Looking at the screen", "zh": "正在查看屏幕"},
    "step_Screenshot": {"en": "Looking at the screen", "zh": "正在查看屏幕"},
    "step_Routine": {"en": "Routine", "zh": "例程"},
    "took": {"en": "took {seconds}s", "zh": "用时 {seconds} 秒"},

    # ---------- menu ----------
    "menu_update": {"en": "Update now to {version}", "zh": "立即更新到 {version}"},
    "menu_settings": {"en": "Settings", "zh": "设置"},
    "menu_hud": {"en": "Open full HUD", "zh": "打开全屏界面"},
    "menu_conversation": {"en": "Show conversation", "zh": "查看对话"},
    "menu_phone": {"en": "Connect phone", "zh": "连接手机"},
    "menu_routines": {"en": "Routines", "zh": "例程"},
    "menu_feedback": {"en": "Send feedback", "zh": "发送反馈"},
    "menu_jobs": {"en": "Background jobs", "zh": "后台任务"},
    "menu_new_chat": {"en": "New chat", "zh": "新对话"},
    "menu_mute": {"en": "Mute voice", "zh": "静音"},
    "menu_listen_for": {"en": "Listen for “{phrase}”", "zh": "监听 “{phrase}”"},
    "menu_on_top": {"en": "Always on top", "zh": "始终置顶"},
    "menu_autostart": {"en": "Start when I log in", "zh": "登录时启动"},
    "menu_stop": {"en": "Stop", "zh": "停止"},
    "menu_corner": {"en": "Move back to corner", "zh": "移回角落"},
    "menu_log": {"en": "Open log (for problems)", "zh": "打开日志（排查问题）"},
    "menu_hide": {"en": "Hide", "zh": "隐藏"},
    "menu_quit": {"en": "Quit Wisp", "zh": "退出 Wisp"},
    "tray_show_hide": {"en": "Show / hide", "zh": "显示 / 隐藏"},
    "tray_talk": {"en": "Talk", "zh": "说话"},
    "type_placeholder": {"en": "Type a command…", "zh": "输入指令……"},

    # ---------- full-screen HUD ----------
    "hud_system": {"en": "System", "zh": "系统"},
    "hud_activity": {"en": "Activity", "zh": "动态"},
    "hud_conversation": {"en": "Conversation", "zh": "对话"},
    "hud_timers_jobs": {"en": "Timers & jobs", "zh": "计时器与任务"},
    "hud_cpu": {"en": "CPU", "zh": "处理器"},
    "hud_memory": {"en": "MEMORY", "zh": "内存"},
    "hud_battery": {"en": "BATTERY", "zh": "电池"},
    "hud_charging": {"en": " (CHARGING)", "zh": "（充电中）"},
    "hud_nothing_yet": {"en": "Nothing yet - ask me something.", "zh": "暂无动态，跟我说点什么吧。"},
    "hud_no_timers": {"en": "None. Try “set a timer for 10 minutes”", "zh": "暂无。试试说「设一个十分钟的计时器」"},
    "hud_type_hint": {"en": "Type here, or just talk  ·  Esc to close", "zh": "在此输入，或直接说话  ·  Esc 关闭"},
    "hud_open_close": {"en": "{key}  open / close", "zh": "{key}  打开 / 关闭"},
    "hud_say_to_talk": {"en": "Say “{phrase}” to talk", "zh": "说 “{phrase}” 开始对话"},
    "hud_focus_today": {"en": "{minutes} MIN FOCUS TODAY", "zh": "今日专注 {minutes} 分钟"},
    "hud_you": {"en": "YOU", "zh": "你"},
    "greet_morning": {"en": "Good morning", "zh": "早上好"},
    "greet_afternoon": {"en": "Good afternoon", "zh": "下午好"},
    "greet_evening": {"en": "Good evening", "zh": "晚上好"},

    # ---------- feedback ----------
    "fb_title": {"en": "Send feedback", "zh": "发送反馈"},
    "fb_intro": {"en": "Ideas, problems, or something you love? It goes straight to the developer.",
                 "zh": "有想法、遇到问题，或者有喜欢的功能？反馈会直接发送给开发者。"},
    "fb_type": {"en": "What kind?", "zh": "反馈类型"},
    "fb_idea": {"en": "Idea / suggestion", "zh": "建议 / 想法"},
    "fb_problem": {"en": "Something's not working", "zh": "遇到问题"},
    "fb_praise": {"en": "Something I like", "zh": "喜欢的地方"},
    "fb_other": {"en": "Other", "zh": "其他"},
    "fb_rating": {"en": "How's Wisp going overall?", "zh": "总体来说，Wisp 用得怎么样？"},
    "fb_message": {"en": "Tell us more:", "zh": "具体说说："},
    "fb_email": {"en": "Email (optional, only if you'd like a reply):", "zh": "邮箱（选填，需要回复时填写）："},
    "fb_attach_log": {"en": "Attach the last 60 lines of the log (helps fix problems; check it below first)",
                      "zh": "附上最近 60 行日志（有助于排查问题，可先在下方查看）"},
    "fb_includes": {"en": "Also sent: Wisp version, operating system, language. Nothing else.",
                    "zh": "同时发送：Wisp 版本、操作系统、语言。不会发送其他内容。"},
    "fb_send": {"en": "Send", "zh": "发送"},
    "fb_github": {"en": "Post publicly on GitHub instead", "zh": "改为在 GitHub 公开发帖"},
    "fb_cancel": {"en": "Cancel", "zh": "取消"},
    "fb_empty": {"en": "Please write something first.", "zh": "请先写点内容。"},
    "fb_sent": {"en": "Thanks! Your feedback was sent.", "zh": "谢谢！反馈已发送。"},
    "fb_queued": {"en": "Thanks! You're offline, so it'll be sent automatically later.", "zh": "谢谢！当前离线，稍后会自动发送。"},
    "fb_not_setup": {"en": "Feedback isn't set up in this copy of Wisp. Use “Post publicly on GitHub” instead.",
                     "zh": "此版本的 Wisp 未配置反馈功能，请使用「在 GitHub 公开发帖」。"},
    "fb_nudge": {"en": "You've been using Wisp for a week. How's it going? Right-click the orb > Send feedback.",
                 "zh": "你已经使用 Wisp 一周了，感觉怎么样？右键点击光球 > 发送反馈。"},
}


def L(en, zh):
    """Inline translation for one-off text: L("Settings", "设置")."""
    return zh if LANG == "zh" else en


def apply_language(lang, save):
    """Switch language: sets LANG and saves the language plus its default voice / speech model / phrases.
    save(changes) writes to config.json."""
    global LANG
    LANG = lang if lang in LANGUAGES else "en"
    save(dict(LANGUAGE_DEFAULTS[LANG], language=LANG))
