from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release-candidate.yml"


def workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    document = yaml.load(text, Loader=yaml.BaseLoader)
    if not isinstance(document, dict):
        raise AssertionError("release candidate workflow must be a mapping")
    return text, document


def step_run(job: dict[str, object], name: str) -> str:
    steps = job.get("steps")
    if not isinstance(steps, list):
        raise AssertionError("workflow job must contain steps")
    for step in steps:
        if isinstance(step, dict) and step.get("name") == name:
            run = step.get("run")
            if isinstance(run, str):
                return run
    raise AssertionError(f"workflow job has no run step named {name!r}")


class ReleaseCandidateWorkflowTests(unittest.TestCase):
    def test_requires_exact_current_main_with_successful_push_ci(self) -> None:
        _, document = workflow()
        jobs = document["jobs"]
        assert isinstance(jobs, dict)
        validate = jobs["validate"]
        assert isinstance(validate, dict)
        run = step_run(validate, "Validate protected-main source and release identity")

        self.assertIn('"${GITHUB_REF}" != "refs/heads/main"', run)
        self.assertIn("refs/remotes/origin/main", run)
        self.assertIn("actions/workflows/ci.yml/runs?head_sha=${GITHUB_SHA}", run)
        self.assertIn('.event == "push"', run)
        self.assertIn('scripts/check-release-pins.py "${REGISTRY_STACK_TAG}"', run)
        self.assertIn(
            'candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-${GITHUB_SHA:0:12}',
            run,
        )

    def test_keeps_one_first_run_smoke_without_repeating_ci(self) -> None:
        text, document = workflow()
        jobs = document["jobs"]
        assert isinstance(jobs, dict)
        candidate = jobs["candidate"]
        assert isinstance(candidate, dict)

        smoke = step_run(candidate, "Run one first-start smoke")
        self.assertIn("just up", smoke)
        self.assertIn("just smoke", smoke)
        self.assertNotIn("portal-live-e2e", text)
        self.assertNotIn("home-live-e2e", text)
        self.assertNotIn("just lint", text)
        self.assertNotIn("just test", text)
        self.assertNotIn("contract-generation-proof", text)

    def test_builds_scans_and_reports_current_hosted_images(self) -> None:
        text, _ = workflow()
        for image in (
            "solmara-lab-registry-evidence",
            "solmara-lab-registry-mint",
            "solmara-lab-relay",
            "solmara-lab-postgres",
            "solmara-lab-static-metadata",
            "solmara-lab-scenario-runner",
            "solmara-lab-home",
            "solmara-lab-portal",
        ):
            with self.subTest(image=image):
                self.assertIn(image, text)
        self.assertIn("grype", text)
        self.assertIn("--fail-on high", text)
        self.assertIn("docker buildx imagetools inspect", text)

    def test_retired_notary_is_absent_from_the_release_path(self) -> None:
        text, _ = workflow()
        release_files = (
            text,
            (ROOT / "scripts" / "check-release-pins.py").read_text(encoding="utf-8"),
            (ROOT / "scripts" / "smoke-hosted.py").read_text(encoding="utf-8"),
        )
        self.assertFalse((ROOT / "docker" / "notary").exists())
        for content in release_files:
            self.assertNotIn("notary", content.lower())


if __name__ == "__main__":
    unittest.main()
