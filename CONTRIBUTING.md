# Contributing

Read the [README](README.md) first. Keep desired
membership separate from complete reported inventory and preserve the protocol's
atomic publication, idempotency, auth and path-safety invariants.

The initial scope is one owner, one watch and one configured local MP3 folder.
Keep administration on host loopback port 8000 and the device API on loopback
port 8001; expose only the device API through HTTPS. Every device data/media
endpoint requires its bearer token. Protect local mutations against CSRF and
untrusted hosts/origins; do not enable permissive CORS.

Never infer deletion from an incomplete report or unavailable PC source. Watch
removal must leave PC originals unchanged and retain unknown cache references.
Validate paths beneath the music root and never serve changed bytes under an
old digest identity. Keep responses within the protocol's entry/byte budgets.
Downloads must be sequential through Garmin's media cache; preserve completed
work across interruptions and suppress late callbacks after cancellation.

Use Python 3.12+ and a project-local virtual environment; follow
the README setup. Run `.venv/bin/python -m pytest -q`. Add a meaningful
failing regression before behavioral changes, then verify the relevant suite.
Protocol changes update the README's protocol summary and both clients.
Documentation/configuration changes use proportionate direct checks.

For frontend changes, run the optional browser checks with Node.js 22+ and
Playwright 1.64.1. These are development tools; the application still needs no
frontend build or Node runtime:

```bash
npm install --prefix .local/browser --no-save playwright@1.64.1
.local/browser/node_modules/.bin/playwright install chromium
PLAYWRIGHT_MODULE="$PWD/.local/browser/node_modules/playwright" \
  node --test tests/browser-ui.cjs
```

The runner serves the real static assets with fixture API responses on an
ephemeral loopback port, then checks browser choices and CSRF rejection against
an isolated FastAPI server using a temporary MP3 folder and database. It uses
the project `.venv/bin/python` by default; `UI_PYTHON` can select another project
virtual environment. The full server integration/security suite remains in pytest.
Set `UI_SCREENSHOTS=assets/screenshots` when running the browser command to
refresh fixture-only screenshots. `CHROMIUM_PATH` can select an already installed
Chromium executable. The current CI workflow runs Python/package/container
checks; browser checks run separately.

Watch builds require the separately installed SDK/device package and external
signing key described in the README. Simulator evidence never
establishes physical decoding or headphone playback.

Contributions are under Apache-2.0. Preserve third-party notices and document
provenance; do not copy GPL reference-project code into this repository. Never
include tokens, private settings, keys, databases, personal music, SDK binaries,
virtual environments or private smoke PRGs. Do not publish or submit to the
Connect IQ Store without explicit owner authorization.
