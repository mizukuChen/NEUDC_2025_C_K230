import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nuedc_k230.platform.capability_probe import ProbeReport, _merge, _safe_value
from tools.validate_phase0_report import REQUIRED_STEPS, validate


class CapabilityProbeHostTest(unittest.TestCase):
    def test_merge_recursively_overrides_configuration(self):
        merged = _merge(
            {"camera": {"width": 1920, "height": 1080}, "enabled": True},
            {"camera": {"width": 1280}, "enabled": False},
        )
        self.assertEqual(
            merged,
            {"camera": {"width": 1280, "height": 1080}, "enabled": False},
        )

    def test_safe_value_normalizes_non_json_values(self):
        value = _safe_value({"items": (b"ok", object())})
        self.assertEqual(value["items"][0], "ok")
        self.assertIsInstance(value["items"][1], str)

    def test_report_survives_a_failed_step(self):
        def fail():
            raise RuntimeError("expected failure")

        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime" / "probe.json"
            report = ProbeReport(str(path), {"board": "host"})
            report.run("successful", lambda: {"value": 3})
            report.run("failed", fail)
            completed = report.finish()

            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(completed["status"], "complete_with_errors")
            self.assertEqual(persisted["error_count"], 1)
            self.assertEqual(persisted["steps"][0]["status"], "ok")
            self.assertEqual(persisted["steps"][1]["status"], "error")

    def test_validator_checks_semantic_hardware_results(self):
        steps = []
        for name in REQUIRED_STEPS:
            steps.append({"name": name, "status": "ok", "data": {}})
        by_name = {item["name"]: item for item in steps}
        by_name["module_inventory"]["data"] = {
            name: {"available": True}
            for name in (
                "media.sensor",
                "media.display",
                "media.media",
                "image",
                "cv_lite",
                "ulab.numpy",
                "machine",
                "nncase_runtime",
            )
        }
        by_name["camera_1920x1080_rgb888"]["data"] = {
            "actual_width": 1920,
            "actual_height": 1080,
        }
        by_name["display_800x480_touch"]["data"] = {"touch_observed": True}
        by_name["combined_display_ch0_algorithm_ch1"]["data"] = {
            "algorithm_channel": {"width": 1920, "height": 1080},
            "display_channel": {"width": 800, "height": 480},
        }
        by_name["image_primitives"]["data"] = {
            "benchmarks": [{"name": "binary", "elapsed_ms": 1}]
        }
        report = {
            "schema_version": 1,
            "probe": "nuedc_k230_phase0",
            "steps": steps,
        }

        problems, _ = validate(report)
        self.assertEqual(problems, [])

        by_name["display_800x480_touch"]["data"]["touch_observed"] = False
        problems, _ = validate(report)
        self.assertIn("display initialized but no touch point was observed", problems)


if __name__ == "__main__":
    unittest.main()
