# Wisp

**A free, open-source voice assistant that actually uses your computer for you.** For Windows 10/11 and macOS 12+ (Mac version in beta).

Talk to it (or type), and Wisp searches the web properly, opens and controls apps, runs long jobs in the background while you keep working, sets timers, runs your own routines, and lets you control your PC from your phone. Its brain is Claude, by Anthropic.

- 🎙️ **Hands-free**: say a wake phrase (e.g. "Hey Jarvis") or hold a key. It answers out loud with a natural voice, and keeps listening when it asks you a question.
- 🖥️ **Does things, not just talks**: opens apps, clicks and types in them, manages files, runs commands (Windows-MCP on Windows, AppleScript on Mac).
- 🔎 **Real research**: reads actual web pages, checks dates, keeps digging until it has the answer.
- ⏳ **Background jobs**: "in the background, compare the best budget laptops", and keep gaming. You get a notification when it's done. Background jobs can't touch your mouse or keyboard.
- 🗂️ **Big projects**: plans them in a checklist and can pick up where it left off days later.
- 👀 **Sees your screen and clipboard**: "explain this error", "summarise what I copied".
- ⏱️ **Timers, reminders, alarms and focus sessions**: instant, no AI needed.
- 🔁 **Routines you make by talking**: "when I say movie night, open Netflix and turn the volume down".
- 📱 **Phone remote**: chat, media keys, screenshots, timers and routines from your phone's browser.
- 🧠 **Memory**: remembers what you ask it to (in a file on your PC you can read and edit).
- ✨ **Floating orb + full-screen HUD**, tray icon (Windows) / Dock icon (Mac), hides itself during fullscreen games on Windows.

## Install

**You need:** an **Anthropic API key** ([get one here](https://console.anthropic.com/settings/keys)) and, optionally, a microphone.

### Windows 10 / 11
Open **PowerShell** and paste:
```powershell
irm https://raw.githubusercontent.com/LucasTao638/Wisp/main/install.ps1 | iex
```
**Or** download `wisp-v…-windows.zip` from [Releases](../../releases), unzip it, and double-click **`setup.bat`**.

### macOS 12 or newer (beta)
Open **Terminal** and paste:
```bash
curl -fsSL https://raw.githubusercontent.com/LucasTao638/Wisp/main/install.sh | bash
```
**Or** download `wisp-v…-mac.zip` from [Releases](../../releases), unzip it, and double-click **`Install Wisp.command`** (if macOS blocks it: right-click > Open > Open).
Wisp appears in your **Applications** folder (in your home folder). The first time, macOS asks to allow the **Microphone**, **Accessibility / Input Monitoring** (for the talk key and shortcuts) and **Automation** (when Wisp controls an app). Allow them, then reopen Wisp.

The installers set up Python 3.13, Wisp's packages and Claude Code (plus Windows-MCP for app control on Windows), then open a short setup screen.

### What does it cost?
Wisp is free. Claude is pay-as-you-go through your own Anthropic API key: you pay Anthropic only for what you use. Quick requests usually cost around a cent or less; big research or coding tasks cost more. **Set a monthly spending limit** in the [Anthropic Console](https://console.anthropic.com/settings/limits) so there are no surprises. Choosing the Haiku model in Settings makes it cheaper still. Timers, routines, shortcuts and the phone controls don't use Claude at all.

## Using it

| Do this | To |
|---|---|
| Do this (Windows) | Mac | To |
|---|---|---|
| Say **"Hey Jarvis"** (or your wake phrase), hold **F9**, or click the orb | Wake phrase, hold **Right Option**, or click the orb | Talk |
| Type in the box under the orb | same | Type instead |
| **Right-click the orb** | **Right-click** (or Ctrl-click) the orb | Menu: Settings, Routines, Connect phone, Update… |
| **Ctrl+Shift+J** | **Ctrl+Option+J** | Full-screen HUD |
| **Ctrl+Shift+Space** or the tray icon | **Ctrl+Option+Space** or the Dock icon | Hide / show |
| **Esc** / **F10** | **Esc** / **Ctrl+Option+X** | Stop |

All shortcuts can be changed in Settings.

Things to try:
- "What's on my screen?" · "Summarise this page" · "Summarise what I copied"
- "In the background, research the best phones under $800 and save a comparison"
- "Start a project to build me a personal website" → later: "continue the website project"
- "Set a timer for 10 minutes for the pasta" · "Remind me at 5pm to call mum" · "Start a focus session"
- "When I say gaming mode, open Steam and Discord" · "What routines do I have?"
- "Remember that my favourite team is…" · "Good morning" (daily briefing)

**Phone remote:** right-click the orb > **Connect phone**, open the address on your phone (same Wi-Fi) and enter the PIN. Add it to your home screen to use it like an app. Away from home? Use [Tailscale](https://tailscale.com) (free); don't open ports on your router.

## Privacy

- Everything runs on your PC. Your voice is turned into text **on your PC**; the wake phrase is detected **on your PC**.
- What you ask is sent to **Anthropic** (that's how Claude answers). Replies are read aloud with Microsoft's online neural voices (just the text being spoken is sent), falling back to the built-in Windows voice offline.
- Your API key is stored **encrypted**: Windows' own protection (DPAPI) or the macOS Keychain.
- **Anonymous usage stats are on by default** to help improve Wisp: a random ID, the version, that it was used today, and which *kinds* of features were used. Never what you say, files, screenshots or your location. Turn it off any time in **Settings**. Full details: [PRIVACY.md](PRIVACY.md).

## Safety

Wisp can run commands and control apps on your PC. It's instructed to ask before deleting files, sending messages, buying anything, installing software or changing system settings, and the most destructive commands are blocked. Still: **review what it's about to do for anything important**, and keep backups. See the `workspace/CLAUDE.md` file for its rules.

## Updating

Wisp checks for updates twice a day and tells you when one's available: right-click the orb > **Update now**. Updates never touch your settings, memory, timers, routines or paired phones.

## Troubleshooting

- **Nothing happens / errors:** right-click the orb > **Open log**, or run `start-text-version.bat` to see messages.
- **"Claude Code isn't logged in" / key errors:** Settings > Claude > Change API key.
- **Wake phrase doesn't hear me:** Settings > Listening > lower the sensitivity. Check Windows' microphone permission for desktop apps.
- **Phone can't connect:** allow Python through the firewall (Windows: *Private* networks; Mac: allow incoming connections when asked), and make sure both are on the same Wi-Fi.
- **Mac: the talk key or shortcuts do nothing:** System Settings > Privacy & Security > **Accessibility** and **Input Monitoring** > turn on Wisp, then quit and reopen it.
- **Mac: Wisp can't control an app:** System Settings > Privacy & Security > **Automation** (and Accessibility) > allow Wisp.

Found a bug? [Open an issue](../../issues) and include the end of the log.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits & legal

MIT licensed, see [LICENSE](LICENSE). Built on [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) by Anthropic, [Windows-MCP](https://github.com/CursorTouch/Windows-MCP), [openWakeWord](https://github.com/dscripka/openWakeWord), [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [edge-tts](https://github.com/rany2/edge-tts).
Wisp is an independent project and isn't affiliated with or endorsed by Anthropic, Microsoft, Apple or Marvel. "Hey Jarvis" is simply one of openWakeWord's built-in wake phrases.
