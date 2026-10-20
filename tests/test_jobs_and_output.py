from __future__ import annotations

import threading

import pytest

from app.models import ConversionRequest, ErrorCode, FileType, JobStatus, QuickConvertError
from app.services import conversion
from app.services.jobs import JobManager
from app.services.output import default_output_path, sanitize_stem, unique_path
from app.storage.settings import UserSettings
from tests.conftest import assert_no_temp_files


@pytest.fixture
def manager():
    m = JobManager()
    yield m
    m.shutdown()


def test_job_completes(manager, jpeg_file, out_dir):
    updates = []
    manager._on_update = lambda job: updates.append(job.status)
    job_id = manager.submit(ConversionRequest(jpeg_file, FileType.PNG, out_dir / "a.png"))
    job = manager.wait(job_id, timeout=30)
    assert job.status is JobStatus.COMPLETED
    assert job.result.output_paths == [out_dir / "a.png"]
    assert job.progress == 1.0
    assert updates[-1] is JobStatus.COMPLETED


def test_submit_validates_synchronously(manager, png_file, out_dir):
    with pytest.raises(QuickConvertError) as err:
        manager.submit(ConversionRequest(png_file, FileType.PNG, out_dir / "a.png"))
    assert err.value.code is ErrorCode.UNSUPPORTED_PAIR


def test_cancel_mid_job_removes_partial_output(jpeg_file, out_dir):
    holder = {}

    def runner(request, check_cancel, job_id):
        calls = 0

        def cancelling_check():
            nonlocal calls
            calls += 1
            if calls == 2:  # after the temp file exists
                holder["m"].cancel(job_id)
            check_cancel()

        return conversion.run(request, cancelling_check, job_id)

    m = holder["m"] = JobManager(runner=runner)
    try:
        job_id = m.submit(ConversionRequest(jpeg_file, FileType.PNG, out_dir / "a.png"))
        job = m.wait(job_id, timeout=30)
    finally:
        m.shutdown()
    assert job.status is JobStatus.CANCELLED
    assert not (out_dir / "a.png").exists()
    assert_no_temp_files(out_dir)


def test_cancel_queued_job(jpeg_file, out_dir):
    gate = threading.Event()

    def blocking_runner(request, check_cancel, job_id):
        gate.wait(10)
        return conversion.run(request, check_cancel, job_id)

    m = JobManager(max_workers=1, runner=blocking_runner)
    try:
        first = m.submit(ConversionRequest(jpeg_file, FileType.PNG, out_dir / "1.png"))
        second = m.submit(ConversionRequest(jpeg_file, FileType.PNG, out_dir / "2.png"))
        assert m.cancel(second)
        assert m.get_job(second).status is JobStatus.CANCELLED
        gate.set()
        assert m.wait(first, timeout=30).status is JobStatus.COMPLETED
    finally:
        gate.set()
        m.shutdown()
    assert not (out_dir / "2.png").exists()


def test_failed_job_reports_error_code(manager, encrypted_pdf, out_dir):
    from app.models import ConversionOptions

    req = ConversionRequest(encrypted_pdf, FileType.PNG, out_dir / "a.png",
                            ConversionOptions(password="wrong"))
    job = manager.wait(manager.submit(req), timeout=30)
    assert job.status is JobStatus.FAILED
    assert job.error_code is ErrorCode.PASSWORD_REQUIRED


def test_unique_path(tmp_path):
    p = tmp_path / "photo.png"
    assert unique_path(p) == p
    p.touch()
    assert unique_path(p).name == "photo (2).png"
    (tmp_path / "photo (2).png").touch()
    assert unique_path(p).name == "photo (3).png"


def test_default_output_path_next_to_source(jpeg_file):
    assert default_output_path(jpeg_file, ".png") == jpeg_file.with_suffix(".png")


@pytest.mark.parametrize("stem,expected", [("a/b:c", "a_b_c"), ("CON", "_CON"), ("  ", "output"),
                                           ("trailing.", "trailing")])
def test_sanitize_stem(stem, expected):
    assert sanitize_stem(stem) == expected


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    UserSettings(default_quality=75, theme="dark").save(path)
    loaded = UserSettings.load(path)
    assert loaded.default_quality == 75 and loaded.theme == "dark"


def test_settings_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert UserSettings.load(path) == UserSettings()
