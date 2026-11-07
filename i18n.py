# -*- coding: utf-8 -*-
"""
每日记事本 —— 界面文案（中 / 英）

用法：
    import i18n
    i18n.set_lang("en")
    i18n.t("send")                      -> "Send"
    i18n.t("counter", left=2, done=1)   -> "2 to do · 1 done"
    i18n.tl("greet")                    -> 随机取一句（列表型文案）
"""

LANG = "zh"

STRINGS = {
    # —— 品牌 / 标题栏
    "app_name": ("每日记事本", "Daily Note"),
    "lang_btn": ("中", "EN"),
    "lang_tip": ("切换成英文", "Switch to Chinese"),

    # —— 底栏
    "history_btn": ("≡ 历史", "≡ History"),
    "today_fmt": ("今天 {date}", "Today {date}"),

    # —— 进度条
    "no_task": ("还没有任务", "No tasks yet"),
    "no_task_tip": ("今天还没有任务，说一句就记下来", "No tasks yet — just tell me one"),
    "bar_tip_full": ("全部 {n} 件都完成了，今天收工", "All {n} done. That's a wrap"),
    "bar_tip_left": ("已完成 {done} / {total}，还剩 {left} 件（{pct}%）",
                     "{done} of {total} done, {left} left ({pct}%)"),
    "encourage": (
        ["全部搞定，今天你赢了。", "收工！这一天很扎实。",
         "件件清零，睡个好觉。", "全清空，给自己鼓个掌。"],
        ["All done — today is yours.", "That's a wrap. Solid day.",
         "Every box checked. Rest well.", "Clean slate. Give yourself a hand."],
    ),

    # —— 任务区
    "counter": ("待办 {left} · 已完成 {done}", "{left} to do · {done} done"),
    "clear_done": ("清理已完成", "Clear done"),
    "cleared_n": ("已清理 {n} 条", "Cleared {n}"),
    "no_cleared": ("没有已完成的任务", "Nothing finished yet"),

    # —— 输入区
    "input_ph": ("说说今天要做什么…", "What's on for today…"),
    "send": ("发送", "Send"),

    # —— 首句问候
    "hello_first": ("早，今天想先干哪几件事？直接说给我就行。",
                    "Morning. What's on your plate today? Just tell me."),

    # —— 回复
    "left_none": ("现在一条待办都没有，可以安心喘口气。",
                  "Nothing left to do. Breathe easy."),
    "left_some": ("还剩 {n} 件没做，最要紧的是「{title}」。",
                  "{n} left. Most pressing: \"{title}\"."),
    "done_ok": ("好，已经勾掉「{title}」，辛苦。", "Done — checked off \"{title}\"."),
    "done_notfound": ("没找到「{title}」这条，是不是已经勾过了？",
                      "Couldn't find \"{title}\". Already checked?"),
    "deleted": ("已删除「{title}」。", "Deleted \"{title}\"."),
    "greet": (["在的，今天想先安排哪件事？", "嗨，说几件今天要做的事吧。", "来了。今天的任务直接报给我。"],
              ["Here. What's first today?", "Hi — give me a few things for today.",
               "Ready. Fire away with today's tasks."]),
    # 按系统时段选的问候（main.greeting() 会挑对应组）
    "greet_morning": (["早上好，今天先安排哪件事？", "早，把今天要做的事报给我吧。", "新的一天，先记一件最重要的事？"],
                      ["Good morning. What's first?", "Morning — tell me today's tasks.",
                       "A new day. Start with the big one?"]),
    "greet_noon": (["中午好，上午的事都顺吗？下午的安排说一下。", "午安，有什么要记的？"],
                   ["Good afternoon. How's it going?", "Afternoon — anything to note?"]),
    "greet_evening": (["晚上好，今天还剩哪些事？", "晚上了，明天的事也可以先记上。", "辛苦一天了，说说什么没做完。"],
                      ["Good evening. What's left today?", "Evening — planning tomorrow already?",
                       "Long day. What's still open?"]),
    "thanks": (["不客气，继续加油。", "小事，记得勾掉哦。"],
               ["Anytime. Keep going.", "No problem — don't forget to tick them off."]),
    "no_parse": (["这句我没听出具体要做的事。加任务可以说「下午3点交周报」。",
                  "没抓到任务，说得再具体点，比如「明天上午10点体检」。"],
                 ["I didn't catch a task. Try \"submit the report before 3pm\".",
                  "Not specific enough — e.g. \"checkup tomorrow at 10am\"."]),
    "added": ("{hey}记下了{names}{extra}。",
              "{hey}Noted {names}{extra}, sorted by priority."),
    "added_more": ("等 {n} 件", " and {n} more"),
    "hey_name": ("{name}，", "{name}, "),
    "duplicated": ("这几件之前就记着了，我把时间更新了一下。",
                   "Already had those — I updated the times."),
    "task_done_push": ("【{title}】完成", "【{title}】done"),
    "menu_priority": ("调整优先级", "Set priority"),
    "pri_label": ("优先级", "Priority"),
    "quote_wrap": ("◆ {q}", "◆ {q}"),
    # v1.9.9.32：对话不再打勾，引导去清单手动勾
    "checkin_hint": ("打卡不用打字啦——直接在下面清单里点一下方框就行 ✅",
                     "No need to type it — just tick the box in the list below ✅"),
    "dup_times_fmt": ("{t}（第{n}次）", "{t} (#{n})"),
    "dup_ask": ("已有相似任务「{title}」。\n"
                "· 回复【就这个】，我会记成「{new}」\n"
                "· 或者换个说法，告诉我要做什么（比如书名/章节）",
                "Similar task \"{title}\" already exists.\n"
                "Reply [same] to log it as \"{new}\", or tell me the specifics."),
    "dup_added": ("好的，已记为「{title}」。", "Done, logged as \"{title}\"."),
    "clock_btn": ("时钟", "Clock"),
    "cal_btn_s": ("日历", "Cal"),
    "hist_btn_s": ("历史", "Hist"),
    "alpha_btn_s": ("透明", "Opac"),
    "bubble_btn_s": ("气泡", "Pop"),
    "clock_left": ("时钟 %s", "Clock %s"),
    "spent": ("用时：{d}", "Spent {d}"),
    "tab_todo": ("待办", "To-do"),
    "tab_note": ("便签", "Notes"),
    "note_ph": ("记点事情…", "Jot something..."),
    "note_saved": ("便签已贴好", "Note saved"),
    "note_del": ("删除", "Delete"),
    "note_deleted": ("便签已删除", "Note deleted"),
    "cal_btn": ("日历", "Calendar"),
    "cal_jump": ("跳到：", "Jump to:"),
    "cal_jump_go": ("跳转", "Go"),
    "ask_meridiem": ("「{t}」是凌晨还是下午？回「凌晨」或「下午」就行。",
                     "Is \"{t}\" in the morning or the afternoon? Reply \"am\" or \"pm\"."),
    "meridiem_ok": ("好的，按{p}的「{t}」记下了。", "Got it — {p} for \"{t}\"."),
    "meridiem_skip": ("好的，这条就不记了。", "Okay, skipped."),
    # v1.9.9.43：不在今天到期的日常打卡提示
    "daily_not_today": ("【{t}】是{r}的任务，到那天再打卡吧，今天打卡不会计入完成度。",
                        "\"{t}\" is due {r}. Check it off on that day instead."),
    # v1.9.9.40：日历圆点图例
    "cal_legend_daily": ("日常", "Daily"),
    "cal_legend_temp": ("待办", "One-off"),
    # v1.9.9.40：桌面气泡右键菜单
    "bubble_toggle": ("展开 / 收起任务", "Expand / Collapse tasks"),
    "cal_today": ("今天", "Today"),
    "cal_off": ("放假", "Off"),
    "cal_work": ("调休上班", "Workday"),
    "cal_day_tasks": ("共 {n} 件（已完成 {d}）", "{n} tasks ({d} done)"),
    "cal_day_empty": ("这天没有安排", "Nothing scheduled"),
    "alpha_btn": ("透明度", "Opacity"),
    "alpha_title": ("透明度：拖到左边更透，右边更实", "Opacity (drag left)"),
    "cal_title": ("日历 · 每日记事本", "Calendar · Daily Note"),
    "ask_remind_short": ("需要我提前多久提醒？{opts}",
                         "Remind you early? {opts}"),
    "ask_remind": ("【{t}】时间是 {d}，想让我提前多久提醒你？{opts}",
                   "When should I remind you about \"{t}\" ({d})? {opts}"),
    "opt_5": ("A.提前5分钟", "A. 5 min"),
    "opt_15": ("B.提前15分钟", "B. 15 min"),
    "opt_30": ("C.提前30分钟", "C. 30 min"),
    "opt_60": ("D.提前1小时", "D. 1 hour"),
    "opt_off": ("E.不用提醒", "E. No reminder"),
    "opt_at": ("F.指定时刻", "F. Type a time"),
    "opt_at_hint": ("（如「08:00」或「前一晚21点」）", " (e.g. 08:00)"),
    "remind_too_soon": ("截止时间就在眼前啦，就不设提前提醒了，到点我直接叫你。",
                        "That deadline is right now — no early reminder, I'll ping you on time."),
    "remind_set": ("好的，会提前 {d} 提醒你【{t}】的截止时间", "OK, I'll remind you {d} before \"{t}\" is due"),
    "remind_at": ("好的，{d} 提醒你【{t}】", "OK, I'll remind you about \"{t}\" at {d}"),
    "remind_off": ("好，【{t}】不设提醒", "OK, no reminder for \"{t}\""),
    "remind_push": ("⏰ 提醒：【{t}】还有 {d} 截止（{h}）",
                    "⏰ Reminder: \"{t}\" is due in {d} (at {h})"),
    "remind_now": ("⏰ 提醒：【{t}】到点了（{h}）", "⏰ Reminder: \"{t}\" — now ({h})"),
    "remind_5": ("5分钟", "5 min"), "remind_15": ("15分钟", "15 min"),
    "remind_30": ("30分钟", "30 min"), "remind_60": ("1小时", "1 hour"),
    "remind_bad_time": ("没看懂这个时间，直接回「A/B/C/D/E」，或写成「08:00」「前一晚21点」这样",
                        "I didn't catch that time. Reply A/B/C/D/E, or type something like \"08:00\""),
    "ask_remind_at": ("好，几点提醒你？直接写时间就行，比如「08:00」「早上7点半」「前一晚21点」",
                      "What time should I remind you? Type it, e.g. \"08:00\" or \"21:00 the night before\""),
    "clock_title": ("时钟 · 每日记事本", "Clock · Daily Note"),
    "clock_sw": ("正计时", "Stopwatch"),
    "clock_cd": ("倒计时", "Countdown"),
    "clock_start": ("开始", "Start"),
    "clock_pause": ("暂停", "Pause"),
    "clock_resume": ("继续", "Resume"),
    "clock_reset": ("清零", "Reset"),
    "clock_done": ("时间到！", "Time's up!"),
    "clock_top": ("窗口置顶", "Always on top"),
    "clock_min": ("分钟", "min"),
    "clock_hr": ("小时", "hours"),
    "clock_sec": ("秒", "sec"),
    "ask_pri": ("{hey}记下了【{t}】，你认为该任务的优先级为：A.紧急 B.重要 C.一般 D.不急；有截止时间吗？（如「晚上8点」，没有可回「无」）",
                "Noted \"{t}\". How important is it? A. Urgent B. Important C. Normal D. Low; any deadline? (e.g. \"8pm\", or reply \"no\")"),
    "ask_pri_only": ("{hey}记下了【{t}】，你认为该任务的优先级为：A.紧急 B.重要 C.一般 D.不急（直接回字母即可）",
                     "Noted \"{t}\". How important is it? A. Urgent B. Important C. Normal D. Low (reply a letter)"),
    "ask_dl_only": ("{hey}记下了【{t}】，有截止时间吗？（如「晚上8点」，没有可回「无」）",
                    "Noted \"{t}\". Any deadline? (e.g. \"8pm\", or reply \"no\")"),
    "ask_dl_short": ("有截止时间吗？（如「晚上8点」，没有可回「无」）",
                     "Any deadline? (e.g. \"8pm\", or reply \"no\")"),
    "pri_set": ("好的，【{t}】优先级：{p}", "Got it, \"{t}\" priority: {p}"),
    "dl_set": ("【{t}】截止时间：{d}", "\"{t}\" deadline: {d}"),
    "dl_none": ("【{t}】不设截止时间", "\"{t}\" has no deadline"),
    "dl_expired": ("【{t}】的时间已经过截止日期咯，确认要加入待办吗？（确认 / 不用）",
                   "That time has already passed. Add \"{t}\" anyway? (yes / no)"),
    "dl_expired_added": ("好的，【{t}】已加入待办，马上提醒你一次。",
                         "Added \"{t}\". Reminding you right away."),
    "dl_expired_skip": ("好的，【{t}】就不加入待办了。",
                        "Okay, \"{t}\" was not added."),
    # 一句话里有多条过期任务时，告知还有几条要确认（v1.9.9）
    "dl_expired_more": ("（另外还有 {n} 条待确认）",
                        " ({n} more to confirm)"),
    # v1.9.9.40：任务已在待办里时，「已过时间」确认的准确问法——
    # 问的是「时间设不设」，不是「加不加入」（旧文案让用户以为
    # 回「不用」能不建任务，结果任务还在，非常困惑）
    "dl_expired_keep": ("【{t}】的时间已经过了今天，还要按这个时间设吗？（确认 / 不用）",
                        "That time has already passed today. Keep it for \"{t}\"? (yes / no)"),
    # v1.9.9.40：回答/改时间带「每天/每周X」→ 任务转日常
    "dl_set_rep": ("好的，【{t}】已改为{r} {d} 的日常任务。",
                   "Done, \"{t}\" is now a {r} task at {d}."),
    # 追问环节（任务已在待办里）拒绝过期时间：只清时间，任务保留（v1.9.5）
    "dl_expired_task_kept": ("好的，【{t}】的时间已经过截止日期，先不设这个截止时间，任务已留在待办里。说「撤回」可以撤销刚才的设置。",
                             "That time has passed, so \"{t}\" stays in the list without a deadline. Say \"undo\" to revert."),
    "dl_expired_ask_more": ("【{t}】的时间已经过截止日期咯，是重新说一个时间，还是不用设时间？（可直接回新时间，或回「不用」）",
                            "That deadline has passed. Give me a new time, or say \"none\" to skip it."),
    # 撤回（v1.9.5）
    # P2 问题9：撤回提示与实现一致（v1.9.9.22）
    "undo_none": ("现在没有可撤回的操作。要改时间可以直接说新时间，或右键任务选「编辑内容」。",
                  "Nothing to undo. Just type a new time, or right-click a task to edit it."),
    # v1.9.9.22：撤回在待确认流程中 = 取消当前问答（不消耗撤回栈）
    "undo_cancelled": ("好，已取消当前的操作，之前记的内容都没动。需要修改的话直接说新的就行。",
                       "Okay, the pending question is cancelled. Nothing else was changed."),
    # v1.9.9.22：UI 操作（勾选/优先级/删除/改名）撤回成功
    "undo_generic_done": ("已撤回：{label}。",
                          "Undone: {label}."),
    "undo_dl_done": ("已经把【{t}】的截止时间撤掉了。请重新说一个时间（例如「明天下午三点」），直接说就行。",
                     "Cleared the deadline of \"{t}\". Tell me the new time."),
    "undo_task_done": ("已经把【{t}】从待办里撤掉了。",
                       "Removed \"{t}\" from your list."),
    "undo_no_dl": ("【{t}】本来就没设截止时间，没有时间可以撤回。想删掉它的话，说「撤回任务」或右键任务选「删除」。",
                   "\"{t}\" has no deadline to undo. Say \"undo task\" or right-click it to delete."),
    "undo_remind_done": ("已撤回刚才设定的提醒时间。",
                         "Removed the reminder time you just set."),
    # 任务详情窗（v1.9.7）
    "detail_left": ("剩余时间", "Time left"),
    "detail_left_hm": ("还有 %d 小时 %d 分钟", "%dh %dm left"),
    "detail_left_dm": ("还有 %d 天 %d 小时", "%dd %dh left"),
    "detail_left_m": ("还有 %d 分钟", "%d min left"),
    "detail_left_over": ("已过截止时间", "Overdue"),
    "rep_daily": ("每天", "daily"),
    "rep_weekly": ("每周", "weekly"),
    "rep_monthly": ("每月", "monthly"),
    "pri_a": ("紧急", "Urgent"), "pri_b": ("重要", "Important"),
    "pri_c": ("一般", "Normal"), "pri_d": ("不急", "Low"),
    "clock_again": ("重新计时", "Restart"),
    "clock_close_cd": ("关闭", "Close"),
    "clock_link": ("关联任务", "Link"),
    "clock_linked": ("→ {t}", "→ {t}"),
    "clock_wrote": ("已把 {d} 记到「{t}」", "Logged {d} to \"{t}\""),
    "clock_finish": ("结束并完成", "Finish & Done"),
    "sw_done": ("【{t}】完成！实际用时 {d}", "\"{t}\" done! Time spent: {d}"),
    "sw_lt1": ("不到 1 分钟", "under 1 min"),
    "clock_done_title": ("倒计时结束", "Countdown finished"),
    "clock_body": ("倒计时 {d} 时间到！", "Countdown {d} is up!"),
    "clock_unit": ("单位", "Unit"),
    "clock_bell": ("铃声", "Sound"),
    "clock_quick": ("快捷", "Quick"),
    "clock_cancel": ("取消倒计时", "Cancel"),
    "menu_auto": ("恢复自动判断", "Auto by rules"),
    "task_done_all": ("今天 {n} 件全部收工。", "All {n} cleared for today."),
    "new_day": ("新的一天，昨天的未完成还留着，今天想先做什么？",
                "New day. Yesterday's unfinished items are still here — what's first?"),

    # —— 右键菜单
    "menu_toggle": ("标记完成/未完成", "Toggle done"),
    "menu_edit": ("编辑内容", "Edit text"),
    # v1.9.9.35：右键「修改时间」
    "menu_time": ("修改时间", "Change time"),
    "time_ask": ("【{t}】改成什么时间？", "New time for \"{t}\"?"),
    "time_hint": ("如 21:30 / 晚上九点半 / 明天下午3点 / 每天早上七点", "e.g. 21:30 / 9:30pm / 3pm tomorrow / 7am every day"),
    "time_bad": ("没看懂「{s}」，再试一次如「21:30」或「明天下午3点」",
                 "Didn't get \"{s}\" — try like 21:30 or 3pm tomorrow"),
    "menu_delete": ("删除", "Delete"),

    # —— 历史窗口
    "hist_title": ("历史记录", "History"),
    "hist_close": ("关闭", "Close"),
    "hist_sum": ("记录 {days} 天 · 任务 {tasks} 件 · 完成 {done} 件 · 完成率 {pct}%",
                 "{days} days · {tasks} tasks · {done} done · {pct}% complete"),
    "hist_empty": ("还没有历史记录。\n今天记几条任务，明天就能在这里回看。",
                   "No history yet.\nAdd a few tasks today — they'll appear here tomorrow."),
    "hist_none_day": ("（这天没有记录）", "(no records)"),
    "day_today": ("今天", "Today"),
    "day_yesterday": ("昨天", "Yesterday"),

    # —— 优先级标签（顺序：紧急 / 重要 / 一般 / 不急）
    "prio": (["紧急", "重要", "一般", "不急"], ["Urgent", "Important", "Normal", "Later"]),
    "weekdays": (["一", "二", "三", "四", "五", "六", "日"],
                 ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
    "day_head": ("{md} 周{wd}", "{wd}, {md}"),
    "day_head_today": ("{md} 周{wd} · 今天", "{wd}, {md} · Today"),
    "day_head_yesterday": ("{md} 周{wd} · 昨天", "{wd}, {md} · Yesterday"),
    "day_head_full": ("{y}年{m}月{d}日 周{wd}", "{wd}, {y}"),
    "month_day": ("{m}月{d}日", "{mon} {d}"),
    "month_names": (["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
                    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]),

    # —— 调色盘
    "palette_title": ("便签颜色", "Sticky color"),
    "theme_changed": ("换成「{name}」了", "Switched to {name}"),
    "theme_names": (
        ["奶油黄", "米白", "薄荷", "雾蓝", "藕粉", "浅杏", "鼠尾草绿", "淡紫"],
        ["Cream", "Rice", "Mint", "Mist", "Lotus", "Apricot", "Sage", "Lilac"],
    ),

    # —— 提示
    "pinned_on": ("已置顶", "Always on top"),
    "pinned_off": ("取消置顶", "Not on top"),

    # —— 首次见面：问昵称 / 问助手名
    "ask_user_name": ("初次见面，你希望我怎么称呼您呢？（比如「你叫我小李吧」）\n"
                      "不想设也行，直接说事情就好，比如「明天下午3点开会」。",
                      "Nice to meet you. What should I call you? (e.g. \"call me Alex\")\n"
                      "No nickname needed — just tell me a task, e.g. \"meeting at 3pm\"."),
    "enter_send_hint": ("回车发送", "Enter to send"),
    "focus_hint": ("在下面输入要做的事，回车即可记录",
                   "Type below and press Enter"),
    "empty_hint": ("今天还没有任务", "No tasks yet"),
    "empty_add": ("＋ 记一条", "+ Add one"),
    "to_tray": ("已收进系统托盘，提醒照常，点托盘图标可打开。",
                "Minimized to tray — reminders still work. Click the tray icon to reopen."),
    "to_tray_notify": ("在后台继续守着你的提醒，点图标可打开。",
                       "Still watching your reminders. Click the icon to open."),
    # v1.9.9.34：托盘气泡只弹一次；开关入口在右键菜单/对话
    "tray_menu_notify": ("后台气泡提示：{st}", "Tray bubble: {st}"),
    "state_on": ("开", "on"),
    "state_off": ("关", "off"),
    "tray_notify_off": ("好的，后台气泡不再弹了。想开回来说「打开托盘提示」或用托盘右键菜单。",
                        "OK — no more tray bubbles. Say \"open tray notification\" or use the tray menu to turn it back on."),
    "tray_notify_on": ("已打开：下次收进托盘时会再提示一次。",
                       "On — you'll get one bubble next time you minimize."),
    "tray_show": ("显示主窗口", "Show window"),
    "quote_roll": ("换一句", "Another one"),
    "tray_quit": ("退出", "Quit"),
    # v1.9.9.23：托盘真的不可用（非 Windows / 初始化失败）时点 ✕ 的交代
    "tray_unavailable": ("系统托盘不可用，已退出。下次打开继续记。",
                         "System tray is unavailable here, so the app exited."),
    # v1.9.9.24：✕ 一律只藏窗口（托盘不可用时也没有托盘菜单，靠
    # 重新双击应用图标唤回窗口）
    "tray_hidden_fallback": ("已收进后台，提醒照常。重新打开本应用或点托盘图标可回到窗口。",
                             "Minimized — reminders still run. Reopen the app to get the window back."),
    "export_btn": ("导出", "Export"),
    "export_json": ("导出 JSON（完整备份）", "Export JSON (full backup)"),
    "export_md": ("导出 Markdown（可读归档）", "Export Markdown (readable)"),
    "export_ics": ("导出日历 ICS（可导入系统日历）",
                   "Export calendar ICS (import to your calendar)"),
    "export_open_dir": ("打开数据文件夹", "Open data folder"),
    "export_ok": ("已导出到：{p}", "Exported to: {p}"),
    "export_fail": ("导出失败：{e}", "Export failed: {e}"),
    "export_dir_fail": ("打不开文件夹，数据在这里：{d}",
                        "Couldn't open the folder. Data is at: {d}"),
    "onboard_skipped": ("好，称呼先不设，随时可以说「叫我小李」补上。",
                        "Sure, no nickname for now. Say \"call me Alex\" anytime to set it."),
    "onboard_as_task": ("称呼先放一边，这件事我先记下了：",
                        "Never mind the nickname — got this task down:"),
    "onboard_no_name_ok": ("没关系，先这样用着，随时可以说「叫我小李」补上。",
                           "No problem, let's just get started. Say \"call me Alex\" anytime."),
    "ask_user_name_again": ("没太听清，你希望我怎么称呼您呢？直接说名字就行，比如「小李」",
                            "I didn't catch that. What should I call you? Just the name, e.g. \"Alex\""),
    "name_ok": ("{name}，记住了。", "Got it, {name}."),
    # v1.9.9.25：追问被「确认/好的/算了」这类应答收尾时，明确交代任务还在
    "pri_skipped": ("好，【{t}】先按默认优先级记着，之后想调整随时说。",
                    "Okay — \"{t}\" is saved with the default priority."),
    # v1.9.9.25（P0-1）：第一句就是任务 → 先记账，再补问称呼
    "onboard_task_first": ("先帮你记下了——这件事不会丢。顺便问一句：你希望我怎么称呼你？（不想设就直接继续说要做什么）",
                           "Noted that first — nothing gets lost. By the way, what should I call you?"),
    # v1.9.9.25：对话里查列表（P0-5）
    "list_report": ("现在有 {n} 件没做：\n{lines}{more}",
                    "You have {n} open task(s):\n{lines}{more}"),
    "list_more": ("\n  …还有 {n} 件", "\n  …and {n} more"),
    # v1.9.9.28：对话里问「今天做了什么」
    "done_today_report": ("今天完成了 {n} 件：\n{lines}", "Done today ({n}):\n{lines}"),
    "done_today_none": ("今天还没有勾掉的任务。想看看每天的习惯，可以说「我的任务」。",
                        "Nothing checked off today yet."),
    # v1.9.9.23：任何时候改昵称（跳过取名后也能补）
    "user_name_changed": ("好，以后就叫你{name}了（原来叫{old}）。",
                          "Okay, I'll call you {name} from now on (was {old})."),
    "usage_guide": (
        "小技巧：\n"
        "· 直接打字就能建任务，如「明天下午3点前交报告」\n"
        "· 说「列表」看待办，「今天做了什么」看完成；日常任务说「背单词打卡了」即可打卡\n"
        "· 建错了说「撤回」\n"
        "· 双击任务可改名，右键有更多操作",
        "Tips:\n"
        "· Just type to add a task, e.g. \"submit report by 3pm tomorrow\"\n"
        "· Say \"list\" for to-dos, \"what did I do today\" for done; daily tasks: \"checked in vocabulary\"\n"
        "· Made a mistake? Say \"undo\"\n"
        "· Double-click a task to rename; right-click for more"),
    "font_size": ("字体大小", "Font size"),
    "text_dark": ("字体深浅", "Text shade"),
    "save_warn": ("⚠️ 提醒一下：当前目录没有写入权限，任务可能存不下来。"
                  "建议把程序放到「文档」或桌面这类可以写入的位置。",
                  "⚠️ Heads-up: this folder isn't writable, so tasks may not be saved. "
                  "Please move the app to Documents or Desktop."),
    "ask_bot_name": ("你好，{name}，您希望我叫什么呢？（比如「小宁同学」）",
                     "Hi {name}, what would you like to call me? (e.g. \"Ning\")"),
    "ask_bot_name_again": ("那我该叫什么名字好呢？给我起一个吧，比如「小宁同学」",
                           "So what should my name be? Pick one for me, e.g. \"Ning\""),
    "bot_name_ok": ("好，以后我就是{bot}。有事随时说，我会帮你记下来、排好优先级。",
                    "Great, I'm {bot} from now on. Tell me what's on your plate and I'll keep track."),
    "intro_self": (
        "我是{bot}，你的每日记事本助手。可以做这些：\n"
        "· 记任务并按重要性排序，完成打勾\n"
        "· 识别截止时间和提醒，到点弹窗提醒你\n"
        "· 有正计时、倒计时和日历，能看每天做了什么\n"
        "{name}，直接说「明天下午三点前交报告」这种句子就行。",
        "I'm {bot}, your daily-notes assistant. I can:\n"
        "· capture tasks, rank them by importance, tick them off\n"
        "· spot deadlines and remind you right on time\n"
        "· run a stopwatch, countdown and calendar of what you did\n"
        "{name}, just say things like \"finish the report by 3pm tomorrow\".",
    ),
    # v1.9.9.35：无名版也要带功能清单——用户实测反馈只回一句话，
    # 功能和用法没人告诉
    "intro_self_noname": (
        "我是{bot}，你的每日记事本助手。可以做这些：\n"
        "· 记任务并按重要性排序，完成在清单里打勾\n"
        "· 识别截止时间和提醒，到点弹窗提醒你\n"
        "· 有正计时、倒计时和日历，能看每天做了什么\n"
        "直接说「明天下午三点前交报告」这种句子就行。",
        "I'm {bot}, your daily-notes assistant. I can:\n"
        "· capture tasks, rank them by importance, tick them off\n"
        "· spot deadlines and remind you right on time\n"
        "· run a stopwatch, countdown and calendar of what you did\n"
        "Just say things like \"finish the report by 3pm tomorrow\".",
    ),
    "intro_first": (
        "我是{bot}，你的每日记事本助手：\n"
        "· 记任务并按重要性排序，完成打勾\n"
        "· 识别截止时间，到点弹窗提醒你\n"
        "· 有正计时、倒计时和日历，能看每天做了什么\n"
        "先从称呼开始吧——",
        "I'm {bot}, your daily-notes assistant:\n"
        "· capture tasks, rank them by importance, tick them off\n"
        "· spot deadlines and remind you right on time\n"
        "· run a stopwatch, countdown and calendar of what you did\n"
        "First things first —"),

    # —— 右下角截止提醒悬浮窗
    "due_win_title": ("任务提醒", "Task reminder"),
    "due_left_hm": ("离截止还有 {h}", "{h} left"),
    "due_left_min": ("离截止还有 {m} 分钟", "{m} min left"),
    "due_left_soon": ("马上就到截止时间了", "Due right about now"),
    "due_over": ("已超过截止时间 {t}", "{t} past the deadline"),
    "over_hm": ("{h}小时{m}分钟", "{h} hr {m} min"),
    "over_min": ("{m}分钟", "{m} min"),
    "due_at": ("截止 {d}", "Due {d}"),
    "due_detail": ("查看详情", "Details"),
    "due_ignore": ("知道了", "Dismiss"),
    "due_done": ("标记完成", "Mark done"),
    "due_detail_head": ("【{t}】", "\"{t}\""),
    "hi_again": ("{name}，{g}", "{name}, {g}"),

    # —— 每日问候轮换池（按天取，一天一句、循环不重样）
    "daily_greet": (
        ["{name}，早上好，今天想先做点什么？",
         "{name}，来啦，把今天的事交给我吧。",
         "{name}，新的一天，先记一件最重要的事？",
         "{name}，今天有什么安排？说给我听听。",
         "{name}，欢迎回来，昨天的事都收尾了吗？",
         "{name}，今天从哪件要紧事开始？",
         "{name}，来了，任务随时报给我。",
         "{name}，今天想怎么安排？我来帮你记。",
         "{name}，有事说一声，我一直都在。",
         "{name}，新的一天开始啦，先列个清单？"],
        ["{name}, morning — what's on today?",
         "{name}, you're back. Tell me about today.",
         "{name}, a new day — start with the big one?",
         "{name}, any plans today? I'm listening.",
         "{name}, welcome back. Did yesterday's items wrap up?",
         "{name}, where do we start today?",
         "{name}, here. Just say the word.",
         "{name}, how do you want to plan today?",
         "{name}, I'm here whenever something comes up.",
         "{name}, fresh day — shall we list things out?"],
    ),

    # —— 详情页字段
    "detail_due_date": ("截止日期", "Due date"),
    "detail_remind": ("提醒", "Remind"),
    "detail_spent": ("用时", "Spent"),
    # v1.9.9.44：「重复」改叫「频率」，值已是「每周四」式描述
    "detail_repeat": ("频率", "Frequency"),
    # 日常任务的「下次到期」替代一次性截止日期
    "detail_next": ("下次", "Next"),
    # 提醒行说清「提前多久 + 实际提醒时刻」
    "detail_remind_plan": ("提前{m} · {t} 提醒您", "{m} early · at {t}"),
    "detail_done": ("完成于", "Done at"),

    # —— 未完成任务气泡（屏幕右下角）
    "bubble_left": ("未完成任务", "To-do"),
    "bubble_expand": ("展开", "Expand"),
    "bubble_collapse": ("收起", "Collapse"),
    "bubble_btn": ("气泡", "Bubble"),
    "bubble_on": ("已开启右下角未完成气泡", "Bubble on"),
    "bubble_off": ("已关闭右下角未完成气泡", "Bubble off"),
    "bubble_empty": ("都做完啦，休息一下吧", "All done — take a break"),
    "bubble_none": ("暂无任务", "No tasks"),

    # —— 日常任务（v1.9.9.27：每天/每周X 重复的任务）
    "grp_daily": ("日常任务", "Daily"),
    "grp_tmp": ("临时任务", "One-off"),
    "grp_done": ("已完成", "Done"),
    # v1.9.9.32：两处计数统一口径（今天该做的日常里完成几件），
    # 文案把「谁除以谁」说破，不再出现裸的 1/3
    "daily_progress": ("今日完成 {d}/{n}", "{d}/{n} done today"),
    "daily_checked": ("打卡了：{t}", "Checked in: {t}"),
    "daily_unchecked": ("已取消今天的打卡：{t}", "Undid today's check-in: {t}"),
    # v1.9.9.41：两段统一「名称 已完成/总数」，措辞改为 日常任务/临时任务
    "daily_left": ("日常任务 {d}/{n} · 临时任务 {td}/{tt}",
                   "Daily {d}/{n} · One-off {td}/{tt}"),
    "daily_only": ("日常任务 {d}/{n}", "Daily {d}/{n}"),
    "counter_plain": ("临时任务 {td}/{tt}", "One-off {td}/{tt}"),
    "daily_tip": ("这是每天都要做的事", "This is a daily task"),
}


def set_lang(code):
    global LANG
    LANG = code if code in ("zh", "en") else "zh"


# —— 双语支持：respond 期间记录每条 tr 的 (key, kw, 渲染结果)，
#    让「已发出的对话」在切换语言时能整体换语言 ——
_REC = None


def record_start():
    global _REC
    _REC = []


def record_drain():
    """取走本轮记录并结束记录模式"""
    global _REC
    r = _REC or []
    _REC = None
    return r


def render(key, kw, lang):
    """强制按指定语言渲染一条文案（kw 为占位参数 dict）"""
    item = STRINGS.get(key)
    if item is None:
        return key
    val = item[1] if lang == "en" else item[0]
    if isinstance(val, (list, tuple)):
        val = val[0] if val else ""
    if kw:
        try:
            return val.format(**kw)
        except Exception:
            return val
    return val


def render_list(key, lang):
    """强制按指定语言取列表型文案"""
    item = STRINGS.get(key)
    if item is None:
        return []
    val = item[1] if lang == "en" else item[0]
    return list(val) if isinstance(val, (list, tuple)) else [val]


def get_lang():
    return LANG


def is_en():
    return LANG == "en"


def t(key, **kw):
    """取文案，支持 {name} 占位符"""
    item = STRINGS.get(key)
    if item is None:
        return key
    val = item[1] if LANG == "en" else item[0]
    if isinstance(val, (list, tuple)):
        return val
    if kw:
        try:
            out = val.format(**kw)
        except Exception:
            return val
    else:
        out = val
    # 记录模式：把 (key, kw, 渲染结果) 存起来供双语回放
    if _REC is not None:
        _REC.append((key, dict(kw), out))
    return out


def tl(key):
    """列表型文案，返回列表副本"""
    v = t(key)
    return list(v) if isinstance(v, (list, tuple)) else [v]


def pick(rng, key, **kw):
    """列表型文案随机取一句"""
    pool = tl(key)
    if not pool:
        return ""
    return rng.choice(pool).format(**kw) if kw else rng.choice(pool)
