"""Validate and summarize a Phase 0 report on the development host."""

import argparse
import json
from pathlib import Path


REQUIRED_STEPS = (
    "runtime",
    "module_inventory",
    "sensor_modes",
    "camera_1920x1080_rgb888",
    "display_800x480_touch",
    "combined_display_ch0_algorithm_ch1",
    "image_primitives",
)


def validate(report):
    problems = []
    if report.get("schema_version") != 1:
        problems.append("unsupported schema_version")
    if report.get("probe") != "nuedc_k230_phase0":
        problems.append("unexpected probe name")
    steps = {item.get("name"): item for item in report.get("steps", [])}
    for name in REQUIRED_STEPS:
        if name not in steps:
            problems.append("missing step: " + name)
        elif steps[name].get("status") != "ok":
            problems.append(
                "%s: %s (%s)"
                % (
                    name,
                    steps[name].get("status"),
                    steps[name].get("error", steps[name].get("reason", "")),
                )
            )

    modules = steps.get("module_inventory", {}).get("data", {})
    for name in (
        "media.sensor",
        "media.display",
        "media.media",
        "image",
        "cv_lite",
        "ulab.numpy",
        "machine",
        "nncase_runtime",
    ):
        if modules and not modules.get(name, {}).get("available"):
            problems.append("required module unavailable: " + name)

    camera = steps.get("camera_1920x1080_rgb888", {}).get("data", {})
    if camera and (
        camera.get("actual_width") != 1920 or camera.get("actual_height") != 1080
    ):
        problems.append(
            "camera output is not 1920x1080: %sx%s"
            % (camera.get("actual_width"), camera.get("actual_height"))
        )

    touch = steps.get("display_800x480_touch", {}).get("data", {})
    if touch and not touch.get("touch_observed"):
        problems.append("display initialized but no touch point was observed")

    combined = steps.get("combined_display_ch0_algorithm_ch1", {}).get("data", {})
    if combined:
        algorithm = combined.get("algorithm_channel", {})
        display = combined.get("display_channel", {})
        if (algorithm.get("width"), algorithm.get("height")) != (1920, 1080):
            problems.append("combined algorithm channel is not 1920x1080")
        if (display.get("width"), display.get("height")) != (800, 480):
            problems.append("combined display channel is not 800x480")

    primitives = steps.get("image_primitives", {}).get("data", {})
    for benchmark in primitives.get("benchmarks", []):
        if benchmark.get("error"):
            problems.append(
                "image primitive failed: %s (%s)"
                % (benchmark.get("name"), benchmark.get("error"))
            )
    return problems, steps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    problems, steps = validate(report)

    print("status:", report.get("status"))
    print("elapsed_ms:", report.get("elapsed_ms"))
    for name in REQUIRED_STEPS:
        step = steps.get(name, {})
        print(
            "%-42s %-8s %s ms"
            % (name, step.get("status", "missing"), step.get("elapsed_ms", "-"))
        )
    if problems:
        print("\nblocking findings:")
        for problem in problems:
            print("-", problem)
        return 1
    print("\nPhase 0 short probe passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
