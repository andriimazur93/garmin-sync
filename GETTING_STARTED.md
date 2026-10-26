# Getting started with Local Music Sync

Use this guide to get one MP3 from your PC onto your Garmin Forerunner 955.
You run the server yourself; there is no hosted account or music subscription.
The tested watch is a Forerunner 955 running firmware 29.05. Other watches and
firmware versions have not been verified.

## What you need

- A Forerunner 955 with Wi-Fi configured, Bluetooth headphones and a USB data
  cable for installing the watch app manually.
- A PC with an internet connection and a folder containing your own MP3 files.
  Keep it awake while syncing. The tested server environment is Ubuntu 24.04;
  Windows and macOS setup have not been validated.
- Git and [Docker Engine with the Compose plugin](https://docs.docker.com/engine/install/)
  on the PC. If you prefer Python 3.12, complete step 1 to clone and enter the
  repository, then follow the [native server instructions](README.md#run-the-pc-server)
  instead of Docker steps 2–3. Continue at step 4 using your native
  installation's token command.
- [Tailscale](https://tailscale.com/docs/install/linux) installed on the PC and
  an account that can enable Funnel. The watch does not need Tailscale.

## Where each part happens

| Where | What you do |
| --- | --- |
| PC terminal | Install and run the server, save its token and start the HTTPS tunnel. |
| Browser on the same PC | Open `http://127.0.0.1:8000` to select music and view sync results. |
| Watch | Configure the connection, start Sync and play downloaded music. |
| Phone | For a Store-installed copy, use Connect IQ settings to enter the URL and token. |

During sync the connection is:

```text
Watch → Wi-Fi → public HTTPS address → tunnel on PC → device API on port 8001
```

## 1. Get the server files — PC terminal

```bash
git clone https://github.com/andriimazur93/local-garmin-music-sync.git
cd local-garmin-music-sync
cp -n .env.example .env
```

If you already downloaded or cloned the repository, open a terminal in its root
folder. Create `.env` only if you do not already have one. Run the remaining
Docker commands from this folder.

## 2. Choose your music folder — PC text editor

Open `.env` and set `GARMIN_SYNC_MUSIC` to the **absolute path of an existing
folder**, for example:

```dotenv
GARMIN_SYNC_MUSIC="/home/YOUR_USER/Music"
```

Replace that example with your real path and put one MP3 in the folder for your
first test. Keep the default ports, 8000 and 8001. Docker stores server state in
its persistent `state` volume; `GARMIN_SYNC_DATA` in `.env` is for native Python
installations. Music is mounted read-only.

## 3. Start the server — PC terminal and browser

```bash
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Both `admin` and `device` should be healthy. Open
[the management page](http://127.0.0.1:8000) in a browser **on this PC**.
Before the watch's first complete report, its inventory is unknown.

If startup fails, inspect `docker compose logs admin device`. Check that Docker
is running, the music folder exists and is readable, and the ports are free.

## 4. Save the device token — PC terminal

```bash
mkdir -p .local
(
  umask 077
  docker compose exec -T admin python -m garmin_sync.cli init > .local/device-settings.json
)
```

Open `.local/device-settings.json` privately in a text editor. Copy its
`device_token` value when configuring the watch later. The file also contains a
`server_id`; you do not enter that in the watch settings. It does **not** contain
your HTTPS URL. Keep this file and token out of posts, screenshots and Git.

For a native Python installation, load your `.env` in the terminal and use the
[native token command](README.md#give-the-watch-a-private-connection).

## 5. Create the HTTPS connection — PC terminal

With Tailscale installed on the same PC as the server, run:

```bash
sudo tailscale up
tailscale funnel --bg 8001
tailscale funnel status
```

Complete the sign-in and any Funnel enablement prompts. Copy the public
`https://…ts.net` address shown by Funnel. In your browser, open that address
with `/health` appended and confirm the health check succeeds.

The watch's server setting uses the **root address only**, such as
`https://YOUR-NAME.YOUR-TAILNET.ts.net`, with no `/health` or `/api` suffix.
Expose only the device API on **8001**; keep the management page on **8000** local.
A browser login page in front of the device API will prevent watch sync.

[Funnel documentation](https://tailscale.com/docs/features/tailscale-funnel)
describes its requirements and bandwidth limits. Keep Funnel and the PC server
running during sync.

## 6. Install and configure the app — watch, optionally phone

Get `garmin-sync-fr955.prg` and its `.sha256` file from
[GitHub Releases](https://github.com/andriimazur93/local-garmin-music-sync/releases).
Check the downloaded PRG against the matching checksum. For example, on Ubuntu,
run `sha256sum garmin-sync-fr955.prg` in your downloads folder and compare its
output with the checksum file.

Connect the watch to your PC by USB, copy the `.prg` into `GARMIN/Apps` on the
watch, then safely eject it. Open **Local Music Sync** from the watch's music
provider menu. You do not need the Connect IQ SDK or a signing key to install
the released PRG. If you prefer building it yourself, see
[the build instructions](README.md#build-and-configure-the-watch-app).

In the app's **Settings**, enter:

| Setting | Where its value comes from |
| --- | --- |
| Server URL | Public HTTPS root address from step 5. |
| Device token | `device_token` from the private JSON file in step 4. |

The saved token is not displayed again in the watch editor.

For a copy installed through the Connect IQ Store, you can enter these properties
in the phone's Connect IQ app settings and save them to the watch. This phone
settings flow has not yet been verified for our Store build; the watch Settings
menu is the tested configuration path. This guide does not assume Store
availability.

## 7. Download one track — PC browser, then watch

1. On the PC, open `http://127.0.0.1:8000` and choose **Rescan PC music**.
2. Find your test MP3 and choose **Download to watch**. This requests a download;
   it does not mean the track is already on the watch.
3. On the watch, open Local Music Sync and choose **Sync**. Leave the watch on
   Wi-Fi until it finishes.
4. If the PC page prompts you to confirm the watch connection, check it is your
   watch and confirm. Removals stay paused until this association is confirmed.
   Start another Sync if changes remain pending.
5. Check the PC page for a complete inventory report with a recent timestamp
   and your track present on the watch.
6. Pair Bluetooth headphones with the watch and play the track through Garmin's
   native music player. Turn watch Wi-Fi off to check offline playback.

See the [PC and watch screenshots](README.md#screenshots) for the management
page, music-provider list and watch Sync/Settings menu. The browser images use
sample data; the provider-list image shows an earlier app icon.

The PC and tunnel are needed for sync. Downloaded music plays without them.

## Next time

Add files to your music folder, rescan on the PC page and request downloads.
To remove a downloaded track, choose **Remove watch copy**. Start **Sync on the
watch** to apply either choice; removal keeps the PC original.

For Docker, `docker compose stop` and `docker compose start` stop and restart
the server while retaining its state. Avoid `docker compose down --volumes`:
it deletes persistent server state. See [backup and recovery](README.md#back-up-and-recover).

If sync fails, check the local management page, the public `/health` URL, watch
Wi-Fi, and the saved URL/token. A successful health check confirms reachability,
not token validity. A disconnected watch keeps its last reported inventory; the
PC page is not a live view of its storage.

For tested firmware and outstanding hardware limitations, see
[the README](README.md) and [release notes](CHANGELOG.md).
