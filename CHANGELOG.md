# Changelog

## 0.2.0
- A whole new look: a holographic design across every window - near-black glass, thin glowing lines, cut corners and corner brackets
  - The orb is now a precise holographic lens instead of a glowing blob: live audio bars while you talk, a radar sweep while it thinks, pulse rings while it speaks. Its faint parts stay visible on any wallpaper
  - The side widget shows a live waveform while listening, a scanning bar while thinking and an equaliser while speaking, with a Stop button
  - Settings has a sidebar with one section at a time instead of one long list
  - New setup screens with a segmented progress bar, and a restyled full-screen HUD and right-click menu
- New "Composed AI" voice style: a little deeper and slower, with a subtle synthetic edge and a sense of space (Settings > Voice > Voice style; "Natural" turns it off)
- Choose Wisp's personality: "Composed butler" (calm, polite, dry wit) or "Friendly" (casual) - in setup and Settings > You
- Dark title bars on Windows; fixed the Save button in Settings so "Restart now" works

## 0.1.4
- Anonymous usage stats and feedback are now switched on for real, so problems and ideas people send actually reach the developer (still optional: turn it off any time in Settings, see PRIVACY.md)
- Uninstaller, Mac permission buttons and installer fixes from 0.1.3 are included

## 0.1.3
- Conversation mode: after each reply Wisp keeps listening for a few seconds, so you can just carry on talking - no "Hey Jarvis" every time. Say "thanks, that's all" (“谢谢，没事了”) or stay quiet to finish. Background noise and coughs don't count
- Talks like a person: Wisp's replies are now casual and natural, react to what you said, remember the conversation ("what about tomorrow?") and sometimes ask something back - no more "Certainly!" or "anything else?"
- Headphones option: wearing headphones? Just start talking while Wisp is speaking and it stops to listen
- Settings for all of these under Settings > Listening
- Easier install: nothing to install first. Windows now gets its own private Python 3.13 too (no winget, no admin, doesn't touch other Pythons), installs Microsoft's Visual C++ runtime if it's missing, and warns if Windows is blocking the microphone
- Uninstall from Settings > System (and on Windows from Settings > Apps), keeping your settings and memory if you like. New Mac uninstaller
- Mac: buttons in the setup screen to open the Microphone, Accessibility, Input Monitoring and Automation settings
- Mac installer and updates accept older downloads that call the package list requirements-mac.txt

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
