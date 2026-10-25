# Third-party material and references

Project source and original icon are licensed under Apache-2.0; see [LICENSE](LICENSE).
No Garmin example source has been copied or modified in this implementation,
so there are no reused Garmin files, upstream revisions or modification notices
to list. Garmin MonkeyMusic informed API research only. SubMusic is a behavioral
reference only; none of its GPL source or assets is included.

The proprietary Connect IQ SDK, device packages, simulator and signing keys must
be acquired separately and are excluded from source, Docker context and release
artifacts. Optional local SDK-manager/simulator wrappers are development tools,
not redistributable project assets.

`tests/fixtures/tone-440hz.mp3` is original generated audio dedicated under CC0
1.0; [fixture provenance](tests/fixtures/README.md) documents generation. The
generator itself is Apache-2.0 project code.

The server installs these separately distributed dependencies from pinned locks:

| Distribution | License |
|---|---|
| FastAPI, anyio, pydantic, pydantic-core, h11 | MIT |
| Starlette, Uvicorn, click, idna | BSD-3-Clause |
| annotated-types | MIT |
| annotated-doc | MIT |
| typing-extensions | PSF-2.0 |
| typing-inspection | MIT |
| opentelemetry-api | Apache-2.0 |
| Python / standard-library SQLite interface | Python Software Foundation License |
| SQLite engine | Public domain |

The Docker base retains its upstream Debian/Python and installed dependency
license files. Development-only dependencies are listed in
`requirements-dev.lock`; their installed distribution metadata remains the
authoritative license record. This table does not relicense third-party code.
Before redistributing a packaged image or changing dependencies, inspect its
actual installed licenses and carry required notices.
