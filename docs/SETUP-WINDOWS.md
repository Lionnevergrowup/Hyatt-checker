# Self-hosted runner setup (Windows)

This turns your Windows PC into the machine that fetches real Hyatt
points data. The PC doesn't need to be on 24/7 — when you open it,
the runner wakes up and picks up any queued jobs.

If you're using a Mac/Linux/Raspberry Pi instead, see
[SELF_HOSTED_RUNNER.md](./SELF_HOSTED_RUNNER.md).

---

## 1. Install Python 3.11

1. Open https://www.python.org/downloads/ in any browser.
2. Click the big yellow **Download Python 3.11.x** button.
3. Run the installer.
4. **Important:** check the box **Add python.exe to PATH** at the
   bottom of the first installer screen.
5. Click **Install Now** and wait.

## 2. Install Git for Windows

1. Open https://git-scm.com/download/win — the download starts
   automatically.
2. Run the installer. Click **Next** on every screen (defaults are
   fine).

## 3. Open PowerShell

Press the Windows key, type `PowerShell`, hit Enter. A blue or black
window appears with a `PS C:\Users\You>` prompt. That's where you'll
type the rest of the commands.

## 4. Get the project and install dependencies

Copy this whole block, paste into PowerShell, hit Enter:

```powershell
cd $env:USERPROFILE
git clone https://github.com/Lionnevergrowup/Hyatt-checker.git
cd Hyatt-checker
pip install --upgrade pip
pip install -e ".[live]"
python -m playwright install chromium
```

This takes 5–10 minutes. Chromium is ~200MB.

## 5. Register the runner with GitHub

1. On your phone or in browser, open
   https://github.com/Lionnevergrowup/Hyatt-checker/settings/actions/runners/new
2. Choose **Windows** and **x64** at the top.
3. GitHub displays a sequence of PowerShell commands like:
   ```
   mkdir actions-runner; cd actions-runner
   Invoke-WebRequest -Uri https://github.com/.../actions-runner-win-x64-X.X.X.zip -OutFile actions-runner-win-x64-X.X.X.zip
   Add-Type -AssemblyName System.IO.Compression.FileSystem ; [System.IO.Compression.ZipFile]::ExtractToDirectory(...)
   ./config.cmd --url https://github.com/Lionnevergrowup/Hyatt-checker --token AAAA...
   ./run.cmd
   ```
4. Copy each command, paste into PowerShell, hit Enter, wait for it
   to finish before pasting the next.
5. When `config.cmd` asks for a name / labels / work folder, hit
   Enter at each prompt to accept defaults.
6. When you reach `./run.cmd`, you'll see **Connected to GitHub.
   Listening for Jobs.** Keep PowerShell open for the next step.

## 6. Make the runner start when Windows boots

So you don't have to remember to launch `run.cmd` every time:

1. Press **Ctrl + C** in PowerShell to stop the runner.
2. Close the PowerShell window. Open a new one **as Administrator**
   (right-click the Start menu → **Windows PowerShell (Admin)** or
   **Terminal (Admin)**).
3. Run:
   ```powershell
   cd $env:USERPROFILE\actions-runner
   ./svc install
   ./svc start
   ```
4. Verify it's running:
   ```powershell
   ./svc status
   ```
   You should see something with `Running`.

The runner now starts automatically every time you turn on your PC.

## 7. Turn on the live workflow

1. On your phone, open the repo → **Actions** tab.
2. Pick **Weekly Hyatt report (live, self-hosted Windows)** on the
   left.
3. Tap **Run workflow** → **Run workflow**.
4. Make sure your PC is on and logged in. The runner picks up the
   job (you can see it light up green at Settings → Actions →
   Runners).
5. After 15–30 minutes the run finishes; reload
   `https://lionnevergrowup.github.io/Hyatt-checker/` and the cells
   should now show real point prices instead of `?`.

## How it works day-to-day

- The schedule runs every Sunday at 13:00 UTC. If your PC is on
  Sunday morning (US Central time), the runner picks it up.
- If your PC is off when the schedule fires, the job queues. Next
  time you turn the PC on, the runner notices and runs it (the
  published page just shows a slightly older "Updated" timestamp).
- You can always force a refresh from your phone: Actions → Run
  workflow.

## If something breaks

- **Runner shows offline at Settings → Actions → Runners**: PC isn't
  on, or the service didn't start. On the PC, open PowerShell as
  Admin and run `cd $env:USERPROFILE\actions-runner; ./svc status`.
  Start it with `./svc start` if needed.
- **Live job still produces `?` cells**: open
  `https://lionnevergrowup.github.io/Hyatt-checker/last-block.png` —
  if that's a Kasada/Hyatt block page, even your residential IP got
  flagged. Restart your router (changes IP for most ISPs) and try
  again.
- **`pip` not found / `python` not found**: PATH didn't get set in
  step 1. Re-run the Python installer with **Add python.exe to
  PATH** checked, or add it manually.
- **`playwright` errors about missing DLLs**: re-run
  `python -m playwright install chromium`.

## Security note

A self-hosted runner runs whatever code your workflow files tell it
to, on your PC. **Don't accept pull requests from strangers** while
the runner is connected — a malicious PR could execute arbitrary code
on your machine. The repo is yours and private contributions only,
so this is fine; if you ever open the repo to the public, see
GitHub's docs on hardening self-hosted runners.
