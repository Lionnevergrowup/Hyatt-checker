# Residential proxy setup (no PC needed)

Hyatt's site is fronted by Kasada bot detection, which blocks
datacenter IPs — including GitHub Actions runners. A residential
proxy routes the fetcher's traffic through a real home IP, which
usually passes. This is the only way to get real points data without
running anything on your own hardware.

Trade-off: it costs money (a few dollars a month at our volume), and
scraping hyatt.com is gray-area under their terms of service. Keep
volume low (the weekly schedule is fine; don't run it hourly).

## 1. Pick a provider

You want **rotating residential** proxies, paid by bandwidth. Cheap
options that work from a phone signup:

| Provider    | Rough price       | Notes                          |
|-------------|-------------------|--------------------------------|
| DataImpulse | ~$1/GB pay-as-go  | Cheapest entry, no minimum     |
| IPRoyal     | ~$7/GB pay-as-go  | No expiry on traffic           |
| Webshare    | ~$7/mo plans      | Monthly plan, simple dashboard |

A weekly run uses roughly 0.3–1 GB (we block images/fonts to keep it
down). Budget $2–10/month depending on provider and how often you
trigger manual runs.

## 2. Get your proxy credentials

After signing up, the provider's dashboard shows connection details
like:

- **Host/port:** `gw.dataimpulse.com:823` (every provider differs)
- **Username / password:** generated for you
- Choose **United States** as the location/geo if asked. Rotating
  sessions (new IP per connection) is fine.

## 3. Add them as GitHub secrets

1. Open the repo on your phone →
   `https://github.com/Lionnevergrowup/Hyatt-checker/settings/secrets/actions`
2. Tap **New repository secret** three times, adding:
   - Name: `HYATT_PROXY_SERVER` — Value: `http://HOST:PORT`
     (e.g. `http://gw.dataimpulse.com:823`)
   - Name: `HYATT_PROXY_USERNAME` — Value: your proxy username
   - Name: `HYATT_PROXY_PASSWORD` — Value: your proxy password

## 4. Run it

Actions → **Weekly Hyatt report** → Run workflow. The workflow
detects the secret and switches to live mode automatically. The run
takes 20–40 minutes for the full hotel list.

If cells still come back `?`, check
`https://lionnevergrowup.github.io/Hyatt-checker/last-block.png` —
if it's a Kasada challenge page, the proxy IP pool you bought is
flagged too; try a different provider or switch the proxy location.

## Notes

- Secrets never appear in logs or in the published page.
- To turn live mode off, just delete the `HYATT_PROXY_SERVER` secret;
  the workflow falls back to the deeplink-only calendar.
- The self-hosted runner path (docs/SETUP-WINDOWS.md) does the same
  thing for free, using your PC's home IP instead of a paid proxy.
