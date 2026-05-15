def _reset_engine_state(engine):
    with engine.queue_lock:
        engine.task_queue.clear()
        engine.running_tasks.clear()
        engine.running_apis.clear()
        engine.running_e2e = False
    engine.workers.clear()
    engine.stop_flags.clear()
    engine.pause_flags.clear()


def test_control_stop_updates_taskcase_statuses():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Task, TaskCase, TestCase, TestCaseGroup
    from backend.utils.execution_engine import execution_engine

    app = create_app("testing")

    with app.app_context():
        _reset_engine_state(execution_engine)

        group = TestCaseGroup(id="g-stop", name="分组")
        case = TestCase(id="tc-stop", name="用例", group_id=group.id, config={})
        task = Task(name="任务", type="api", status="queued", total_cases=1, config={})
        db.session.add_all([group, case, task])
        db.session.commit()

        rel = TaskCase(task_id=task.id, test_case_id=case.id, execution_status="pending", evaluation_status="pending")
        db.session.add(rel)
        db.session.commit()

        ok, _ = execution_engine.control_task(app, task.id, "stop")
        assert ok is True

        db.session.expire_all()
        task2 = db.session.get(Task, task.id)
        rel2 = db.session.get(TaskCase, rel.id)
        assert task2.status == "stopped"
        assert rel2.execution_status == "stopped"
        assert rel2.evaluation_status == "stopped"
        assert rel2.status == "skipped"


def test_control_pause_on_queued_removes_from_queue_and_pauses():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Task
    from backend.utils.execution_engine import execution_engine

    app = create_app("testing")

    with app.app_context():
        _reset_engine_state(execution_engine)

        task = Task(name="任务", type="api", status="queued", total_cases=0, config={})
        db.session.add(task)
        db.session.commit()

        with execution_engine.queue_lock:
            execution_engine.task_queue.append({"id": task.id, "type": "api", "api_ids": [], "app": app})

        ok, _ = execution_engine.control_task(app, task.id, "pause")
        assert ok is True

        with execution_engine.queue_lock:
            assert all(t["id"] != task.id for t in execution_engine.task_queue)

        db.session.expire_all()
        task2 = db.session.get(Task, task.id)
        assert task2.status == "paused"


def test_control_resume_without_worker_requeues_task():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import API, Task, TaskAPI
    from backend.utils.execution_engine import execution_engine

    app = create_app("testing")

    with app.app_context():
        _reset_engine_state(execution_engine)

        api = API(name="a", vendor=None, api_url="http://x", description="", meta={}, api_endpoints=[])
        db.session.add(api)
        db.session.commit()

        task = Task(name="任务", type="api", status="paused", total_cases=0, config={})
        db.session.add(task)
        db.session.commit()

        rel = TaskAPI(task_id=task.id, api_id=api.id)
        db.session.add(rel)
        db.session.commit()

        execution_engine.running_apis.add(api.id)

        ok, _ = execution_engine.control_task(app, task.id, "resume")
        assert ok is True

        db.session.expire_all()
        task2 = db.session.get(Task, task.id)
        assert task2.status == "queued"

