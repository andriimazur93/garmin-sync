"""Local commands. Credentials print only in the explicit init action."""
import argparse
import json
import os
import uvicorn
from .config import load_settings
from .db import Database
from .admin import create_admin_app
from .device import create_device_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "serve-admin", "serve-device"])
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "init":
        identity = Database(settings.database_path).identity()
        print(json.dumps({key: identity[key] for key in ["server_id", "device_token"]}, indent=2))
        return
    admin = args.command == "serve-admin"
    factory = create_admin_app if admin else create_device_app
    # Container deployments opt in; host port publication still stays loopback.
    bind = os.getenv("GARMIN_SYNC_BIND", "127.0.0.1")
    uvicorn.run(factory(settings), host=bind, port=settings.admin_port if admin else settings.device_port, access_log=False)


if __name__ == "__main__":
    main()
