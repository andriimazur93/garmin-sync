import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize("summary,status,expected", [
    ("PASSED (passed=1, failed=0, errors=0)", 1, 0),
    ("FAILED (passed=0, failed=1, errors=0)", 1, 1),
    ("Error: could not connect", 2, 2),
])
def test_runner_preserves_failure_and_recognizes_sdk_success(tmp_path, summary, status, expected):
    sdk = tmp_path / "sdk"
    (sdk / "bin").mkdir(parents=True)
    tool = sdk / "bin/monkeydo"
    tool.write_text(f"#!/bin/sh\nprintf '%s\\n' '{summary}'\nexit {status}\n")
    tool.chmod(0o755)
    prg = tmp_path / "test.prg"
    prg.write_bytes(b"fixture")
    result = subprocess.run(["bash", "scripts/run-simulator.sh", str(prg), "--tests"], env=os.environ | {"CIQ_SDK_HOME": str(sdk)}, capture_output=True)
    assert result.returncode == expected
