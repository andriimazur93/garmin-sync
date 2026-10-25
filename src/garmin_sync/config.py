"""Explicit local paths and listener configuration."""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    music_root: Path
    data_dir: Path
    admin_port: int = 8000
    device_port: int = 8001

    @property
    def database_path(self) -> Path:
        return self.data_dir / "state.db"


def load_settings() -> Settings:
    return Settings(
        music_root=Path(os.getenv("GARMIN_SYNC_MUSIC", "music")).expanduser().resolve(),
        data_dir=Path(os.getenv("GARMIN_SYNC_DATA", "data")).expanduser().resolve(),
        admin_port=int(os.getenv("GARMIN_SYNC_ADMIN_PORT", "8000")),
        device_port=int(os.getenv("GARMIN_SYNC_DEVICE_PORT", "8001")),
    )
