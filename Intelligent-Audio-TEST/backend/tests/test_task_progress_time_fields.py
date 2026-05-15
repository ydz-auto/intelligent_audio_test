import re
from datetime import datetime, timedelta


def test_task_progress_used_time_is_string_when_not_started(monkeypatch):
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Task, TaskCase, TestCase, TestCaseGroup
    from backend.utils.event_manager import EventManager

    app = create_app("testing")

    emitted = {}

    def fake_emit(event, data, *args, **kwargs):
        emitted["event"] = event
        emitted["data"] = data

    monkeypatch.setattr("backend.utils.event_manager.socketio.emit", fake_emit)

    with app.app_context():
        try:
            group = TestCaseGroup(id="g-tp-1", name="分组")
            case = TestCase(id="tc-tp-1", name="用例", group_id=group.id, config={})
            task = Task(name="任务", type="api", status="running", total_cases=1, config={})
            db.session.add_all([group, case, task])
            db.session.commit()

            rel = TaskCase(task_id=task.id, test_case_id=case.id, status="pending", execution_status="pending")
            db.session.add(rel)
            db.session.commit()

            manager = EventManager(execution_engine=object())
            manager.emit_progress(task.id, force=True)
        finally:
            db.session.remove()
            db.drop_all()

    assert emitted["event"] == "task_progress"
    assert emitted["data"]["taskId"] == str(task.id)
    assert emitted["data"]["usedTime"] == "0分钟"


def test_task_progress_expected_times_are_emitted_after_first_completion(monkeypatch):
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Task, TaskCase, TestCase, TestCaseGroup
    from backend.utils.event_manager import EventManager

    app = create_app("testing")

    emitted = {}

    def fake_emit(event, data, *args, **kwargs):
        emitted["event"] = event
        emitted["data"] = data

    monkeypatch.setattr("backend.utils.event_manager.socketio.emit", fake_emit)

    with app.app_context():
        try:
            group = TestCaseGroup(id="g-tp-2", name="分组")
            case1 = TestCase(id="tc-tp-2-1", name="用例1", group_id=group.id, config={})
            case2 = TestCase(id="tc-tp-2-2", name="用例2", group_id=group.id, config={})
            task = Task(
                name="任务",
                type="api",
                status="running",
                total_cases=2,
                completed_cases=1,
                started_at=datetime.now() - timedelta(minutes=2),
                config={},
            )
            db.session.add_all([group, case1, case2, task])
            db.session.commit()

            rel1 = TaskCase(task_id=task.id, test_case_id=case1.id, status="completed", execution_status="completed")
            rel2 = TaskCase(task_id=task.id, test_case_id=case2.id, status="pending", execution_status="pending")
            db.session.add_all([rel1, rel2])
            db.session.commit()

            manager = EventManager(execution_engine=object())
            manager.emit_progress(task.id, force=True)
        finally:
            db.session.remove()
            db.drop_all()

    assert emitted["event"] == "task_progress"
    data = emitted["data"]
    assert data["taskId"] == str(task.id)
    assert isinstance(data["usedTime"], str)
    assert isinstance(data["expectedTotalTime"], str)
    assert re.search(r"(秒|分钟|小时)$", data["usedTime"])
    assert re.search(r"(秒|分钟|小时)$", data["expectedTotalTime"])
    assert isinstance(data["expectedCompleteTime"], str)
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", data["expectedCompleteTime"])
