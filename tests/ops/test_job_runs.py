from datetime import datetime

from huginn.ops.job_runs import JobRunStatus, finish_job_run, start_job_run


def test_start_job_run_is_running_with_a_started_at():
    job_run = start_job_run("hn")

    assert job_run.source == "hn"
    assert job_run.status == JobRunStatus.RUNNING
    assert isinstance(job_run.started_at, datetime)
    assert job_run.finished_at is None
    assert job_run.rows_written == 0
    assert job_run.error is None


def test_start_job_run_assigns_an_id():
    job_run = start_job_run("hn")

    assert job_run.id


def test_start_job_run_ids_are_unique_per_call():
    first = start_job_run("hn")
    second = start_job_run("hn")

    assert first.id != second.id


def test_finish_job_run_succeeded_sets_finished_at_and_rows_written():
    started = start_job_run("yc")

    finished = finish_job_run(started, JobRunStatus.SUCCEEDED, rows_written=42)

    assert finished.status == JobRunStatus.SUCCEEDED
    assert isinstance(finished.finished_at, datetime)
    assert finished.rows_written == 42
    assert finished.error is None


def test_finish_job_run_does_not_mutate_the_original():
    started = start_job_run("yc")

    finish_job_run(started, JobRunStatus.SUCCEEDED, rows_written=42)

    assert started.status == JobRunStatus.RUNNING
    assert started.finished_at is None
    assert started.rows_written == 0


def test_finish_job_run_preserves_id_and_source_and_started_at():
    started = start_job_run("yc")

    finished = finish_job_run(started, JobRunStatus.SUCCEEDED, rows_written=1)

    assert finished.id == started.id
    assert finished.source == started.source
    assert finished.started_at == started.started_at


def test_finish_job_run_failed_sets_error_and_failed_status():
    started = start_job_run("yc")

    finished = finish_job_run(started, JobRunStatus.FAILED, error="Algolia timeout")

    assert finished.status == JobRunStatus.FAILED
    assert finished.error == "Algolia timeout"
    assert finished.rows_written == 0
    assert isinstance(finished.finished_at, datetime)


def test_started_at_and_finished_at_are_timezone_aware():
    started = start_job_run("hn")
    finished = finish_job_run(started, JobRunStatus.SUCCEEDED)

    assert started.started_at.utcoffset() is not None
    assert finished.finished_at.utcoffset() is not None
