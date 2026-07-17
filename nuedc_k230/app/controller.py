"""Top-level application controller for the active development phase."""

from nuedc_k230.platform.capability_probe import run_phase0_probe


def main():
    report = run_phase0_probe()
    return 0 if report.get("status") == "complete" else 1
