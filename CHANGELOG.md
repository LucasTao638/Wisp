# Changelog

## 1.1.0
- **Fixed the grey orb with no text.** In the orb and the full-screen HUD, the letter `t` meant both "the current time" and "translate this text". The orb crashed while showing "Starting" and froze grey with no words, and the full-screen view had the same problem in two places. They now use separate names, and status and hint text show correctly in English and Chinese.
- Windows installer: more reliable handling of pip/winget/Python messages, so harmless progress output is no longer treated as a failure.

## 0.0.1 (first public release)
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
