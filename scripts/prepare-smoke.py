"""Prepare private, test-only watch resources from a local JSON configuration.

Configuration fields: url, token, track_id, session_id. Never print their values or commit
the configuration, generated resources or smoke PRG.
"""
import argparse
import json
from pathlib import Path
import shutil
import uuid
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("configuration", type=Path)
parser.add_argument("--flow", action="store_true", help="Use the production sync engine integration entry point")
args = parser.parse_args()
config = json.loads(args.configuration.read_text())
if args.flow:
    config.setdefault("session_id", str(uuid.uuid4()))
uuid.UUID(config["session_id"])
parts = urlsplit(config["url"])
config["base_url"] = parts.scheme + "://" + parts.netloc
if not config["url"].startswith("https://"):
    raise SystemExit("Smoke URL must use HTTPS")
if not config["token"] or len(config["track_id"]) != 64:
    raise SystemExit("Missing credential or invalid track identity")
root = Path(__file__).resolve().parents[1]
target = root / ".local/watch-smoke"
target.mkdir(parents=True, exist_ok=True, mode=0o700)
shutil.copytree(root / "watch/resources", target / "resources", dirs_exist_ok=True)
manifest = ET.parse(root / "watch/manifest.xml")
ET.register_namespace("iq", "http://www.garmin.com/xml/connectiq")
manifest.find("{http://www.garmin.com/xml/connectiq}application").set("entry", "ProtocolFlowApp" if args.flow else "SmokeApp")
manifest.write(target / "manifest.xml", encoding="utf-8", xml_declaration=True)
properties = ET.parse(target / "resources/strings/strings.xml").getroot()
for placeholder in list(properties):
    if placeholder.get("id", "").startswith("Smoke"):
        properties.remove(placeholder)
ET.SubElement(properties, "string", {"id": "SmokeRunId"}).text = uuid.uuid4().hex
for key, source in [("SmokeUrl", "url"), ("SmokeToken", "token"), ("SmokeTrackId", "track_id"), ("SmokeSessionId", "session_id"), ("SmokeBaseUrl", "base_url")]:
    ET.SubElement(properties, "string", {"id": key}).text = config[source]
# Resource strings update on each build; stored property defaults do not.
private = target / "resources/strings/strings.xml"
ET.ElementTree(properties).write(private, encoding="utf-8", xml_declaration=True)
private.chmod(0o600)
(target / "monkey.jungle").write_text(
    f"project.manifest = {target / 'manifest.xml'}\n"
    f"base.sourcePath = {root / 'watch/source'};{root / 'watch/tests'};{root / 'watch/smoke-tests'}\n"
    f"base.resourcePath = {target / 'resources'}\n"
)
print("Prepared test-only smoke resources under ignored .local/watch-smoke/")
