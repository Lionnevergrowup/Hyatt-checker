# Self-hosted runner setup (Raspberry Pi)

Why: Hyatt's site is fronted by Kasada bot detection. Datacenter IPs
(including GitHub-hosted runners) get blocked, so the default workflow
publishes a deeplink-only calendar with no real points data. A
self-hosted runner on your home network has a residential IP, which
Kasada usually lets through — so Playwright can actually fetch real
prices.

This guide walks you through buying a Raspberry Pi, installing the
GitHub Actions runner on it, and turning on the live workflow.

If you have a Mac/Linux PC/Mini PC instead of a Pi, skip step 1 and
adapt the commands (most are Linux but Mac is similar).

---

## 1. Buy a Raspberry Pi 5 starter kit (~$80–100)

Search Amazon (or Adafruit / Canakit / Vilros) for:
**"Raspberry Pi 5 starter kit 4GB"**

A good kit includes:
- Raspberry Pi 5 (4GB or 8GB) board
- Case with fan
- Official USB-C power supply (27W)
- microSD card pre-flashed with Raspberry Pi OS (32GB+)
- HDMI cable (micro-HDMI → HDMI)

You'll also need (probably already have):
- A TV or monitor with HDMI input (only for first-time setup)
- USB keyboard + mouse (only for first-time setup)

## 2. First boot

1. Plug the SD card into the Pi.
2. Connect HDMI to TV/monitor, USB keyboard, USB mouse.
3. Plug in power. Pi boots into Raspberry Pi OS.
4. Walk through the setup wizard: language, password, Wi-Fi.
5. Open Terminal (top bar, the icon that looks like a black box).

Once Terminal is open, you can do everything else by typing commands.

## 3. Install Python + Playwright dependencies

In Terminal:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git
```

Playwright needs a bunch of shared libs Chrome uses:

```bash
sudo apt install -y \
  libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2
```

(If apt complains about a missing package name, it's fine — the
Playwright installer in step 5 will pull in what's missing.)

## 4. Register the runner with GitHub

1. On your phone (or any browser): go to
   `https://github.com/Lionnevergrowup/Hyatt-checker/settings/actions/runners/new`
2. Pick **Linux** and **ARM64** (Pi 5 is ARM64).
3. GitHub shows ~5 commands. They look something like:
   ```
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-linux-arm64-X.X.X.tar.gz -L https://github.com/.../actions-runner-linux-arm64-X.X.X.tar.gz
   tar xzf ./actions-runner-linux-arm64-X.X.X.tar.gz
   ./config.sh --url https://github.com/Lionnevergrowup/Hyatt-checker --token AAAA...
   ./run.sh
   ```
4. Copy each command and paste into your Pi's Terminal, hit Enter,
   wait for it to finish before pasting the next.
5. When `./config.sh` asks for the runner name, labels, work folder —
   just hit Enter to accept defaults.
6. When you run `./run.sh`, you'll see "Connected to GitHub. Listening
   for Jobs." Keep this terminal open for now.

## 5. Make the runner start on boot (always-on)

So you don't have to keep the terminal open and so the runner survives
reboots:

1. Hit **Ctrl+C** in the terminal to stop `./run.sh`.
2. Install the runner as a system service:
   ```bash
   cd ~/actions-runner
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```
3. Verify it's running:
   ```bash
   sudo ./svc.sh status
   ```
   You should see "active (running)".

Now the runner starts automatically whenever the Pi boots, and the Pi
can sit in a corner with the cable plugged in.

## 6. Install Playwright's browsers (one time)

Still in Terminal:

```bash
cd ~
git clone https://github.com/Lionnevergrowup/Hyatt-checker.git
cd Hyatt-checker
pip install -e ".[live]"
python -m playwright install --with-deps chromium
```

This downloads Chromium into a cache the workflow can reuse.

## 7. Trigger a refresh

There is no auto-schedule — the workflow runs only when you ask.

- **From any browser/phone**: open the repo → **Actions** → **Weekly
  Hyatt report (live, self-hosted Windows)** → tap **Run workflow**.
- **From the Pi (or any computer)**: run `scripts/run-hyatt.ps1`
  (PowerShell) or call the GitHub API directly with a Personal
  Access Token. See `scripts/run-hyatt.ps1` for the request shape;
  on Linux/macOS you can replicate it with `curl -X POST`.

After ~15–30 minutes (Playwright is slow against Hyatt), the page at
`https://lionnevergrowup.github.io/Hyatt-checker/` should show real
point prices, not `?`.

## Troubleshooting

- **Runner shows offline (gray dot)**: SSH/Terminal into the Pi and
  run `sudo ~/actions-runner/svc.sh status`. If it's not running:
  `sudo ~/actions-runner/svc.sh start`.
- **Live job still produces `?` cells**: Hyatt may be blocking your
  IP. Check `public/last-block.png` on Pages to see what they served.
  If it's a Kasada challenge, ISPs sometimes change IPs that get
  flagged. Try restarting your router.
- **Playwright errors about missing libraries**: re-run `python -m
  playwright install --with-deps chromium` to pull in the dependency
  list it knows about.
- **The Pi is slow / overheats**: make sure the case has its fan
  installed. The first Playwright install also pulls 200MB+ of
  Chromium — give it time.

## Security note

A self-hosted runner runs whatever code your workflow files tell it
to, on your home machine. **Don't accept pull requests from
strangers** while a self-hosted runner is connected — a malicious PR
could run arbitrary code on the Pi. For a private personal repo this
is fine; for a public repo, see GitHub's guidance on hardening
self-hosted runners.
