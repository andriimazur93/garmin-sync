# Garmin Sync

Garmin Sync is a self-hosted music manager for the Garmin Forerunner 955. Choose
MP3s from a folder on your PC, request downloads or removals in a local browser,
then start **Sync** on the watch. Downloaded tracks play offline through Garmin's
native music player.

It supports one owner, one watch and one MP3 directory. The PC shows the watch's
last **complete reported inventory** and its timestamp; a disconnected watch is
not treated as empty. Removing a watch copy never deletes the PC original.

The ordinary release was tested on a Forerunner 955 running firmware 29.05:
download, complete inventory, offline headphone playback before and after a
restart, removal, and recovery from an unavailable HTTPS endpoint worked. A
repeat Sync through a stable HTTPS address completed without another download.
Physical interrupted-transfer recovery and storage/battery impact were not
measured. Results on other firmware or MP3 files may differ.

## Run the PC server

Tested on Ubuntu 24.04 with Python 3.12. Use a project-local environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.lock
.venv/bin/python -m pip install --no-build-isolation -r requirements-dev.lock
cp .env.example .env
```

Edit `.env`: set `GARMIN_SYNC_MUSIC` to an existing MP3 directory and
`GARMIN_SYNC_DATA` to a private persistent directory. Quote paths with spaces.
Keep `.env` private. In one terminal:

```bash
set -a
. ./.env
set +a
.venv/bin/python -m garmin_sync.cli serve-admin
```

In a second terminal, load `.env` the same way and run
`.venv/bin/python -m garmin_sync.cli serve-device`. Open the management page at
**http://127.0.0.1:8000**. The separate device API listens at
**http://127.0.0.1:8001**. Both default to loopback; expose only port 8001
through HTTPS. There is no frontend build step, Garmin OAuth login or phone
companion app.

For Docker Compose, set `GARMIN_SYNC_MUSIC` in `.env` to an **absolute, existing**
directory readable by the container, then run:

```bash
docker compose config --quiet
docker compose up --build -d --wait
```

Compose publishes both ports on PC loopback only. Music is mounted read-only;
the named `state` volume holds the database and credentials. The `scratch` volume
may temporarily contain audio bytes during delivery. `docker compose stop` and
`docker compose start` preserve state. Do not use `docker compose down --volumes`
unless you intend to delete the state volume.

## Give the watch a private connection

Generate the server's device token once and save it outside Git:

```bash
mkdir -p .local
(
  umask 077
  .venv/bin/python -m garmin_sync.cli init > .local/device-settings.json
)
```

For Compose, replace the final command with
`docker compose exec -T admin python -m garmin_sync.cli init`. Keep the output
file private; it contains the device token. The watch needs that token and the
public HTTPS root URL of the device API.

For a free stable URL without a purchased domain, install
[Tailscale](https://tailscale.com/docs/install/linux) on the machine running the
device listener, sign in to its Personal plan, then run:

```bash
sudo tailscale up
tailscale funnel --bg 8001
tailscale funnel status
```

Funnel may first prompt you to enable it in your account. Its status shows an
`https://…ts.net` URL. It exposes local port **8001**, never the management page
on 8000. Keep the PC server and Funnel running when you sync. Funnel currently
has [bandwidth limits](https://tailscale.com/docs/features/tailscale-funnel),
so check a full MP3 transfer on your setup.

For temporary testing, a [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/concepts/)
can expose `http://127.0.0.1:8001`; its URL changes after a restart. Update the
watch settings whenever the URL changes. A browser login challenge cannot be
used for the device API because the watch sends a bearer token directly.

## Build and configure the watch app

Install [Garmin Connect IQ SDK](https://developer.garmin.com/connect-iq/connect-iq-basics/getting-started/)
9.3.0, Java 17 and the `fr955` device package separately. You also need your own
private DER developer signing key. These tools and keys are not bundled. From
the repository root:

```bash
export CIQ_SDK_HOME=/absolute/path/to/sdk-9.3.0
export GARMIN_SIGNING_KEY=/private/path/developer.der
export PATH=/absolute/path/to/java-17/bin:$PATH
bash scripts/build-watch.sh
```

The ordinary output is `dist/garmin-sync-fr955.prg`. Copy it to
`GARMIN/Apps` on the watch over USB, then safely eject. In the app's **Settings**,
enter the HTTPS root URL and device token. The token editor does not display a
saved token. Keep configuration files containing these values private. Builds
made with `--tests` or `--smoke` are development artifacts; use the ordinary PRG
for the watch.

## Sync and manage music

1. Rescan the music folder in the PC page after changing its files.
2. Choose **Download to watch** for a track. The request stays pending until
   the watch reports a complete inventory.
3. Choose **Sync** in the watch playback menu. After first contact, confirm the
   watch/server association in the PC page before requesting removals.
4. Review the last reported inventory and time. Choose **Remove watch copy** and
   Sync again to remove a track from the watch while retaining the PC original.

The watch downloads sequentially through Garmin's media cache. Completed work
and cache mappings survive restarts. Missing PC source files do not request
watch deletion, and unknown cache entries are retained. If a plan or cache
capacity limit is reported, remove known tracks or sync smaller batches.

## Back up and recover

Back up the PC music directory separately. For a native installation, stop both
services and copy the **entire** `GARMIN_SYNC_DATA` directory, including any
SQLite `state.db-wal` and `state.db-shm` files. Restore it with both services
stopped. Treat the backup as a secret: it contains identity, token, membership,
sessions and reported inventory.

For Compose, stop both services, archive the named state volume into a private
local directory, then start them again:

```bash
mkdir -p .local/backups
chmod 700 .local/backups
docker compose stop
(
  umask 077
  docker compose run --rm --no-deps -T admin tar -C /data -cf - . > .local/backups/state.tar
)
docker compose start
```

Restore only into a fresh empty state volume; do not merge databases. After any
restore, review desired music choices and run a manual Sync. If server state was
lost, a new identity/token is created, inventory is initially unknown, and the
watch/server association must be confirmed again before removals.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) for development rules. The device API uses
bearer authentication, immutable sync plans, idempotent operation results and
atomic complete inventory reports. JSON pages are limited to 20 entries and
8192 UTF-8 bytes including their envelopes. Server endpoints are implemented
under `src/garmin_sync/`; the watch client is under `watch/source/`.

Project code is [Apache-2.0](LICENSE); see [third-party notices](THIRD_PARTY.md).
Accounts, payments, browser uploads, transcoding, streaming and music from
other providers are outside this project's scope.
