# Changelog

## 0.1.2
- New side widget: when you talk, a small panel appears beside the orb instead of the full-screen HUD (no dimming, nothing in the middle of the screen). It shows what Wisp heard, what it's doing and its reply, with a Stop button. Choose widget / full-screen HUD / just the orb in Settings
- Waits until you've really finished talking: a longer, smarter pause (adapts to background noise), a little extra time after short phrases, and it keeps listening if you trail off ("open Spotify and…", "um")
- Interrupt any time: the Stop button, F10, Esc, or just say "stop" / "never mind" (“停” / “别说了”). Talking over Wisp with a new request stops the old one instead of queuing it
- Stopping is clean now: no "something went wrong" afterwards, and anything Claude was doing in your apps stops too

## 0.1.1
- Choose where to install Wisp (Windows and Mac); updates go to the same folder
- One-click Claude Code setup: the setup screen and Settings find, install and test Claude Code for you (no terminal commands); Wisp finds Claude Code even when it isn't on PATH
- Mac: double-click `Install Wisp.command` installs everything (private Python 3.13, packages, Claude Code, Wisp.app) with no admin password
- Windows 10/11, plus a **Mac version (beta)** for macOS 12+ (Apple Silicon and Intel)
- Voice assistant for Windows powered by Claude: wake phrase, push-to-talk, natural voices, follow-up listening
- App control (Windows-MCP), web research, background jobs, multi-step projects
- Screen and clipboard understanding
- Timers, reminders, alarms, focus sessions, routines you create by talking
- Floating orb, full-screen HUD, tray icon, auto-hide during fullscreen games
- Phone remote (paired with a PIN)
- Memory, morning briefing
- Setup screen, Settings window, encrypted API key storage
- Automatic update checks with one-click updates
- Anonymous usage stats (on by default, can be turned off; see PRIVACY.md)
- **Chinese (Simplified)**: speak and get answers in Chinese, Chinese voices, Chinese quick commands (timers, reminders, focus, opening apps and sites, routines), and a translated interface. Choose it at setup or in Settings > Language
- **Feedback**: send ideas or bug reports from the menu, the phone app, or by voice ("I have a suggestion…" / "我有个建议……"), with optional rating, email and log; works offline and retries later
