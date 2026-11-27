# Maintainer guide: publishing Wisp and checking how it's doing

> ⚠️ **Keep two separate folders:** your *source* folder (this one, which goes on GitHub) and your *personal install* (the one you actually use). Never upload your install folder: it has your memory, settings and API key in it. The `.gitignore` blocks those files, but keeping the folders separate is the real protection.

---

## One-time setup (about 20 minutes)

### 1. Create the GitHub repository
1. Go to <https://github.com/new>.
2. Repository name: **wisp** · **Public** · don't add a README (we have one) · **Create repository**.

### 2. Put your username into the code
In these files, replace `YOUR-GITHUB-USERNAME` with your GitHub username:
- `app_info.py` → `GITHUB_REPO = "yourname/wisp"`
- `install.ps1` → `$Repo = "yourname/wisp"`
- `install.sh` → `REPO="yourname/wisp"`
- `README.md` → both install commands near the top

### 3. Set up anonymous stats (PostHog, free)
1. Sign up at <https://posthog.com> (free plan: 1 million events a month, far more than you'll need).
2. Create a project. Copy its **Project API key** (starts with `phc_`) into `app_info.py` → `POSTHOG_KEY`. This key is safe to publish: it can only *send* events, not read them.
3. If your PostHog project is in the EU region, change `POSTHOG_HOST` to `https://eu.i.posthog.com`.
4. In PostHog: **Settings → Project → IP data capture** → turn on **Discard client IP data** (extra privacy).

### 4. Upload the code
Easiest: **GitHub Desktop** (<https://desktop.github.com>)
1. File → **Add local repository** → choose this source folder → it'll offer to "create a repository": do that.
2. **Publish repository**, choosing your existing `wisp` repo (untick "Keep this code private").
3. In the "Changes" list, make sure **none** of these appear: `config.json`, `secrets.bin`, `telemetry.json`, `phone.json`, `MEMORY.md`, `*.log`. If one does, stop and ask for help.

### 5. Publish the first release
1. On GitHub: your repo → **Releases** → **Draft a new release**.
2. **Choose a tag** → type `v0.1.6` → *Create new tag on publish*.
3. Title: `Wisp 0.1.6`. Description: paste the 0.1.6 section from `CHANGELOG.md`.
4. **Publish release**. Within a minute or two, the **Actions** tab builds **`wisp-v0.1.6-windows.zip`** and **`wisp-v0.1.6-mac.zip`** and attaches both to the release automatically. (To build them on your own PC instead: `py build_release.py v0.1.6` → they appear in `build/`.)
5. Test the one-line install on your own PC (or a friend's).

---

## Shipping an update
1. Make your changes in the source folder and test them.
2. In `app_info.py`, bump `VERSION`, e.g. `"1.0.1"` (bug fixes) / `"1.1.0"` (new features).
3. Add a section to the top of `CHANGELOG.md`.
4. GitHub Desktop: **Commit** → **Push**.
5. GitHub: Releases → Draft a new release → tag `v1.0.1` (must match VERSION, or the build stops and tells you) → paste the changelog → **Publish**.

Everyone's Wisp checks twice a day (Windows copies download the Windows zip, Macs the Mac zip), says *"Wisp 1.0.1 is available"*, and updates with one click. Updates never touch anyone's settings, memory, routines or paired phones. If you add a new setting, put it in `config.default.json`; it'll be added to everyone's config automatically.

If you remove a file, add its name to `REMOVED_FILES` in `updater.py` so old copies get cleaned up.

---

## Checking retention in PostHog
- **Product analytics → New insight → Retention.** Set *"Start event"* = `app_installed` and *"Return event"* = `daily_active`, period **Day** or **Week**. This shows what % of people who installed in a given week are still using Wisp 1, 2, 3… weeks later.
- **Trends**: `daily_active` with *unique users* = your daily active users. Change to weekly for WAU.
- **Feature use**: Trends → `feature_used`, broken down by the `feature` property. This shows which features people actually use (and which aren't worth more work).
- **Versions**: break any chart down by `app_version` to see how quickly people update and whether a release changed anything.
- **GitHub → Insights → Traffic** and the download count on each release show how many people found and downloaded it.

Good early signals: week-1 retention above ~20% is decent for a free desktop tool; if most people drop off on day 1, the setup experience (API key, installing) is usually why.

---

## Reading feedback

Feedback arrives in the same PostHog project as the stats:

- **Activity → Events**, filter by event = `feedback_submitted`. Click an event to see `kind` (idea / problem / praise / other), `message`, and, if the person added them, `rating`, `email` and `log`.
- For an inbox-style view: **Product analytics → New insight → SQL** and run
  `select timestamp, properties.kind, properties.rating, properties.message, properties.email, properties.app_version, properties.language from events where event = 'feedback_submitted' order by timestamp desc`
- Save that as a dashboard tile, or set up an **Alert / Destination** (e.g. to email or Discord) on `feedback_submitted` so you hear about it straight away.
- People who choose "Post on GitHub instead" open a normal GitHub issue with the `feedback`, `enhancement` or `bug` label.

Everything here is something the person wrote and chose to send; treat emails as private and don't publish messages without asking.

## The Mac version
- It's the same code: anything specific to Windows or Mac lives in `sysplat.py` (opening apps, sounds, clipboard, media keys…), `hotkeys.py` and `credentials.py`. Fix a Mac-only problem there.
- It's labelled **beta** because it hasn't been tested on many Macs yet. Before you announce it, ask someone with a Mac to run the one-line install and try: talking (hold Right Option), the wake phrase, a timer, "what's on my screen?", the full HUD (Ctrl+Option+J) and the phone remote. Bug reports from Mac users are the fastest way to get it out of beta.
- Mac users don't need to do anything extra for updates: Wisp downloads the Mac zip by itself.

## Things to keep in mind
- **Anthropic's rules:** apps you distribute must use API key login, not people's Claude Pro/Max subscriptions. Wisp's setup screen asks for an API key for this reason. Don't add a "log in with your Claude account" option.
- **Don't** call it "Jarvis" in the name, logo or descriptions: that's Marvel's trademark. Offering "Hey Jarvis" as one of several wake phrases is fine.
- **Security reports:** if someone reports a security problem, fix it before talking about it publicly.
- **Privacy:** if you ever change what `telemetry.py` sends, update `PRIVACY.md` in the same release and mention it in the changelog.

## The phone app (GitHub Pages) - once
The phone app works away from home by being served from GitHub Pages:
1. Repo **Settings > Pages > Build and deployment**: "Deploy from a branch", branch `main`, folder `/docs`, Save.
2. After a minute, https://lucastao638.github.io/Wisp/ should show the app (it says "Connect to Wisp").
Whenever `remote_page.html` changes, copy it to `docs/index.html` too.

