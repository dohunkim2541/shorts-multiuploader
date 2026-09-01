from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from shorts_distributor import runner
from shorts_distributor.uploaders.base import Outcome, StepFailure


class _Page:
    def close(self) -> None:
        pass


class _Context:
    def new_page(self) -> _Page:
        return _Page()


class PlatformIsolationTest(TestCase):
    def test_blocked_platform_does_not_stop_next_platform_lane(self) -> None:
        blocked = Mock()
        blocked.upload.side_effect = StepFailure(
            "open",
            "login required",
            blocker=True,
        )
        healthy = Mock()
        healthy.upload.return_value = Outcome(
            "published",
            posted_text="Example title",
            evidence="published",
        )
        modules = {"blocked-platform": blocked, "healthy-platform": healthy}
        prepared = {
            "youtube_id": "video-id",
            "title": "Example title",
            "title_text": "Example title",
            "post_text": "Example title",
            "file_path": "/tmp/video.mp4",
            "upload_date": "20260818",
            "timestamp": 1,
        }
        cfg = SimpleNamespace(
            target_platforms=list(modules),
            profile_strategy="shared",
            youtube_handle="@example-channel",
        )

        with (
            patch.object(runner, "_new_run_dir", return_value=("run-id", Path("/tmp/run-id"))),
            patch.object(runner, "prepare_video", return_value=prepared),
            patch.object(runner, "ensure_h264", return_value=(Path("/tmp/video.mp4"), "h264")),
            patch.object(runner, "get_uploader", side_effect=lambda platform: modules[platform]),
            patch.object(runner, "platform_context", return_value=nullcontext(_Context())),
            patch.object(runner.state, "is_uploaded", return_value=False),
            patch.object(runner.state, "mark_uploaded"),
            patch.object(runner, "_write_report"),
            patch.object(runner.time, "sleep"),
        ):
            report = runner.run_batch(cfg, video_ids=["video-id"], do_verify=False)

        statuses = {cell["platform"]: cell["status"] for cell in report["cells"]}
        self.assertEqual(statuses["blocked-platform"], "blocked")
        self.assertEqual(statuses["healthy-platform"], "published")
        healthy.upload.assert_called_once()

    def test_policy_excluded_platform_is_skipped_without_stopping_others(self) -> None:
        instagram = Mock()
        instagram.upload.return_value = Outcome(
            "published", posted_text="#ad\n\nFull description", evidence="published"
        )
        facebook = Mock()
        modules = {"instagram": instagram, "facebook": facebook}
        prepared = {
            "youtube_id": "video-id",
            "title": "Campaign video",
            "title_text": "Campaign video",
            "post_text": "#ad\n\nFull description",
            "file_path": "/tmp/video.mp4",
            "upload_date": "20260818",
            "timestamp": 1,
            "policy_names": ["campaign-example"],
            "allowed_platforms": ["instagram"],
            "disclosures": {"instagram": ["paid-partnership"]},
        }
        cfg = SimpleNamespace(
            target_platforms=list(modules),
            profile_strategy="shared",
            youtube_handle="@example-channel",
        )

        with (
            patch.object(runner, "_new_run_dir", return_value=("run-id", Path("/tmp/run-id"))),
            patch.object(runner, "prepare_video", return_value=prepared),
            patch.object(runner, "ensure_h264", return_value=(Path("/tmp/video.mp4"), "h264")),
            patch.object(runner, "get_uploader", side_effect=lambda platform: modules[platform]),
            patch.object(runner, "platform_context", return_value=nullcontext(_Context())),
            patch.object(runner.state, "is_uploaded", return_value=False),
            patch.object(runner.state, "mark_uploaded"),
            patch.object(runner, "_write_report"),
            patch.object(runner.time, "sleep"),
        ):
            report = runner.run_batch(cfg, video_ids=["video-id"], do_verify=False)

        statuses = {cell["platform"]: cell["status"] for cell in report["cells"]}
        self.assertEqual(statuses["instagram"], "published")
        self.assertEqual(statuses["facebook"], "skipped-policy")
        job = instagram.upload.call_args.args[1]
        self.assertEqual(job.disclosures, ("paid-partnership",))
        facebook.upload.assert_not_called()
