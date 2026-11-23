# Wisp privacy

Wisp runs on your PC. This page lists everything that leaves it.

## 1. Anonymous usage stats (on by default, easy to turn off)

To find out whether people keep using Wisp and which features are worth improving, Wisp sends a few anonymous events to [PostHog](https://posthog.com) (an analytics service).

**Exactly what's sent:**

| Event | When | Extra details |
|---|---|---|
| `app_installed` / `app_updated` | First run / first run after an update | the previous version |
| `app_opened` | Wisp starts | the look you use (orb or classic) |
| `daily_active` | Once per day that Wisp runs | none |
| `feature_used` | You use a feature | the feature's *type* only, one of: ask_claude, background_job, timer, routine, routine_created, focus_session, screen, clipboard, briefing, wake_word, push_to_talk, phone_remote, full_hud, shortcut |

Every event also includes: a **random ID** created on your PC (`telemetry.json`), not linked to your name, account, email, hardware or API key; Wisp's **version**; and your **Windows version**.

**Never sent:** anything you say or type, Claude's replies, timer or routine names, file names or contents, screenshots, clipboard contents, memory, your API key, or your location. IP-based location lookup is switched off in every event (`$geoip_disable`), and no user profiles are created (`$process_person_profile: false`).

**Turn it off:** right-click the orb > **Settings** > System > *Share anonymous usage stats*, or set `"share_usage_stats": false` in `config.json`. Nothing more is sent after that. Deleting `telemetry.json` gives you a new random ID.

You can check all of this in [`telemetry.py`](telemetry.py): it's short and it's the only place stats are sent from.

### Feedback you choose to send

When you send feedback (the **Send feedback** window, the phone app's Feedback card, or saying "I have a suggestion: …"), Wisp sends a `feedback_submitted` event to the same PostHog project with:

- the **type** (idea / problem / praise / other) and the **message you wrote**
- your **star rating** and **email**, only if you filled them in
- the **end of the log**, only if you ticked *Attach the end of the log* (you can read it in the window first)
- the Wisp version, your operating system, your language setting, and the same random ID as above

You see and can edit everything before it's sent, and nothing is sent unless you press **Send**. Because it's something you send on purpose, feedback goes even if anonymous usage stats are off. If you're offline it waits in `feedback_outbox.json` and is retried later; delete that file to cancel. Prefer it public? Every feedback window has a **Post on GitHub instead** button.

## 2. Things that leave your PC so Wisp can work

- **Anthropic (Claude):** your requests, and whatever Claude reads to answer them (web pages, files or screenshots you ask about, your clipboard if you mention it), are sent to Anthropic using your API key. See [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy).
- **Microsoft voices (edge-tts):** the text being spoken is sent to Microsoft's speech service to create the audio. Switch to the offline Windows voice with `"voice_engine": "windows"` in `config.json`.
- **GitHub:** Wisp checks GitHub twice a day for a newer version (GitHub sees a normal web request from your IP).
- **Websites** Claude visits while researching for you.

## 3. Things that stay on your PC

Your voice recordings (turned into text locally, then discarded), wake-phrase listening, memory (`workspace/MEMORY.md`), settings, timers, routines, conversation state, background job results, the log, and your encrypted API key (`secrets.bin`).

The **phone remote** only works on your own network (or your private Tailscale network) and only for phones you've paired with a PIN.

## Questions

Open an issue on the GitHub repository.
