"""Release publication must stop before writes when evidence is incomplete."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "release_publisher", Path(__file__).resolve().parents[1] / "packaging/publish_test_installers.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

SOURCE = "a" * 40


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.responses = {
            "git/ref/heads/main": {"object": {"sha": SOURCE}},
            "releases?per_page=100": [],
            f"git/commits/{SOURCE}": {"tree": {"sha": "b" * 40}},
        }
        runs = []
        for run_id, name, count in ((1, "installers.yml", 4), (2, "tests.yml", 6)):
            info = {"id": run_id, "path": f".github/workflows/{name}",
                    "head_sha": SOURCE, "conclusion": "success", "event": "pull_request",
                    "head_repository": {"full_name": publisher.REPO}}
            runs.append(info)
            self.responses[f"actions/runs/{run_id}"] = info
            self.responses[f"actions/runs/{run_id}/jobs?per_page=100"] = {
                "jobs": [{"conclusion": "success"} for _ in range(count)]}
        self.responses[f"actions/runs?head_sha={SOURCE}&per_page=100"] = {"workflow_runs": runs}
        self.responses["actions/runs/1/artifacts"] = {"artifacts": []}
        for context in (patch.dict(os.environ, GITHUB_REPOSITORY=publisher.REPO),
                        patch.object(publisher, "SOURCE", SOURCE),
                        patch.object(publisher.subprocess, "check_output", return_value=SOURCE),
                        patch.object(publisher, "api", side_effect=lambda path: self.responses[path])):
            context.start(); self.addCleanup(context.stop)
        context = patch.object(publisher, "command")
        self.write = context.start(); self.addCleanup(context.stop)

    def test_missing_successful_workflow_waits_without_publication(self):
        self.responses[f"actions/runs?head_sha={SOURCE}&per_page=100"]["workflow_runs"].pop()
        publisher.main()
        self.write.assert_not_called()

    def test_failed_individual_job_blocks_publication(self):
        self.responses["actions/runs/2/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
        with self.assertRaisesRegex(RuntimeError, "required build/test job"):
            publisher.main()
        self.write.assert_not_called()

    def test_missing_installer_artifacts_blocks_publication(self):
        with self.assertRaisesRegex(RuntimeError, "Unexpected artifact set"):
            publisher.main()
        self.write.assert_not_called()

    def test_existing_version_cannot_be_replaced_with_another_commit(self):
        self.responses["releases?per_page=100"] = [{"tag_name": publisher.TAG, "draft": False}]
        self.responses[f"commits/{publisher.TAG}"] = {"sha": "c" * 40}
        with self.assertRaisesRegex(RuntimeError, "different commit"):
            publisher.main()
        self.write.assert_not_called()
