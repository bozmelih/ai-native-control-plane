from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "skills/ai-native-control-plane/scripts/validate_artifacts.py"
TASK_TEMPLATE = ROOT / "skills/ai-native-control-plane/assets/task-packet.template.json"
GRANT_TEMPLATE = ROOT / "skills/ai-native-control-plane/assets/authority-grant.template.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(VALIDATOR), *args], cwd=ROOT, text=True, capture_output=True, check=False)


class ValidatorTests(unittest.TestCase):
    def test_package_templates_pass(self) -> None:
        result = run_validator("--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS errors=0", result.stdout)

    def test_high_risk_requires_red_team_and_high_compute(self) -> None:
        task = json.loads(TASK_TEMPLATE.read_text(encoding="utf-8"))
        task["risk_tier"] = "high"
        task["compute_route"] = "standard"
        task["method_packs"] = [pack for pack in task["method_packs"] if pack != "red-team"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-task.json"
            path.write_text(json.dumps(task), encoding="utf-8")
            result = run_validator("--task", str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_RISK_COMPUTE_TOO_LOW", result.stdout)
        self.assertIn("ERR_RISK_RED_TEAM_REQUIRED", result.stdout)

    def test_active_grant_requires_explicit_approval_record(self) -> None:
        grant = json.loads(GRANT_TEMPLATE.read_text(encoding="utf-8"))
        grant["status"] = "active"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-grant.json"
            path.write_text(json.dumps(grant), encoding="utf-8")
            result = run_validator("--grant", str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERR_OBJECT_REQUIRED", result.stdout)


if __name__ == "__main__":
    unittest.main()
