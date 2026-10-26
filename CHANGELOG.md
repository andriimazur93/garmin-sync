# Changelog

User-visible changes to Local Music Sync are recorded here. This project has not yet
published a Connect IQ Store release.

## [Unreleased]

### Changed

- Add reusable GitHub bug-report and feature-request forms, with guidance for
  relevant environment details and redacting private configuration.
- Add an ordered first-time setup guide, a prominent README entry point and
  watch-menu screenshots. Clarify released-PRG installation and the separate
  sources of the device token and HTTPS URL.
- Redesign the PC page with an iTunes-inspired toolbar, sidebar and responsive
  song list, combining catalog and reported watch contents in one library.
- Add filename search, On watch / Pending / Needs attention views, a pending
  changes summary, connection retry and setup guidance.
- Preserve search and keyboard focus across status polling, and keep requested
  changes separate from the last complete watch report.

### Validation

- Browser interaction checks cover choices, filters, report preservation,
  association confirmation, errors, keyboard focus and mobile layouts.
- Screenshots in the README use fixture data. This frontend change does not
  establish new watch hardware or firmware compatibility.

## [0.1.1] - 2026-10-25

### Changed

- Rename the product display to Local Music Sync.
- Use the owner-generated icon for the Forerunner 955 launcher and Store cover.

### Validation

- CI passed server tests, Python wheel build and Docker build for the source
  commit.
- The FR955 package compiled with Connect IQ SDK 9.3.0. The updated icon and
  branding build have not yet been retested on physical hardware; the hardware
  results below are from the prior release.

## [0.1.0] - 2026-10-25

### Added

- Self-hosted Python server and local browser interface for managing an MP3
  library and requesting track downloads or removals on a Garmin watch.
- Connect IQ audio content provider for the Forerunner 955, with user-initiated
  sync and playback through Garmin's native music player.
- Bearer-authenticated device API, HTTPS tunnel setup guidance, and private
  watch configuration using an endpoint URL and device token.
- Persistent sync sessions, sequential media delivery, and complete inventory
  reporting so interrupted or repeated syncs can recover without treating a
  disconnected watch as empty.
- Setup instructions and a first-sync checklist in the README.

### Verified

- Ordinary app build and hardware workflow on a Forerunner 955 running firmware
  29.05: download, complete inventory, playback through headphones, removal,
  and recovery after the HTTPS endpoint becomes unavailable.
- Offline playback before and after a watch restart.
- Download and playback of a three-minute stereo MP3, plus repeat sync without
  another download.

### Known limitations

- Forerunner 955 is the only hardware target verified so far.
- Physical recovery from an interrupted media transfer and storage or battery
  impact have not been measured.
- A private simulator driver crashes during a removal scenario; the ordinary
  release simulator and the tested hardware workflow did not reproduce it.
- The v0.1.0 GitHub release uses the former Garmin Sync display name; the Store
  candidate uses Local Music Sync. The Store package has not been submitted.
