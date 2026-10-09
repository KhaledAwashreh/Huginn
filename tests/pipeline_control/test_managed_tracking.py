from uuid import uuid4

import pytest

from huginn.elt.stage_runner import Stage, run_stages
from huginn.ops.job_runs import JobRunStatus, finish_job_run, start_job_run


class Writer:
    def __init__(self, fail_at=None):
        self.runs = []
        self.fail_at = fail_at

    def write(self, run):
        if len(self.runs) == self.fail_at:
            raise RuntimeError("private database failure")
        self.runs.append(run)


def test_managed_start_failure_prevents_work_and_terminal_uncertainty_stops_next_stage():
    called = []
    invocation_id = uuid4()
    for fail_at, expected in ((0, []), (1, ["first"])):
        writer = Writer(fail_at)
        called.clear()
        with pytest.raises(RuntimeError):
            run_stages(
                [
                    Stage("first", lambda: called.append("first") or 2),
                    Stage("second", lambda: called.append("second") or 1),
                ],
                writer,
                invocation_id=invocation_id,
                strict_tracking=True,
            )
        assert called == expected


def test_lineage_is_stable_through_terminal_update_and_context_is_exact():
    writer = Writer()
    observed = []
    invocation_id = uuid4()
    run_stages(
        [
            Stage(
                "gold.company",
                lambda: 0,
                run_managed=lambda context: observed.append(context) or 3,
            )
        ],
        writer,
        invocation_id=invocation_id,
        strict_tracking=True,
    )
    started, finished = writer.runs
    assert started.invocation_id == str(invocation_id)
    assert started.execution_kind == "stage"
    assert finished.id == started.id
    assert finished.invocation_id == started.invocation_id
    assert str(observed[0].stage_job_run_id) == started.id
    assert observed[0].stage_name == "gold.company"
    source = start_job_run(
        "hn",
        invocation_id=str(invocation_id),
        parent_job_run_id=started.id,
        execution_kind="source",
    )
    terminal = finish_job_run(source, JobRunStatus.SUCCEEDED, 4)
    assert terminal.parent_job_run_id == started.id
    assert terminal.invocation_id == source.invocation_id
