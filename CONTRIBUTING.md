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

Watch builds require the separately installed SDK/device package and external
signing key described in the README. Simulator evidence never
establishes physical decoding or headphone playback.

Contributions are under Apache-2.0. Preserve third-party notices and document
provenance; do not copy GPL reference-project code into this repository. Never
include tokens, private settings, keys, databases, personal music, SDK binaries,
virtual environments or private smoke PRGs. Do not publish or submit to the
Connect IQ Store without explicit owner authorization.
