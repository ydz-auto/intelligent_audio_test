from sqlalchemy.orm import sessionmaker


def test_taskcase_pending_claim_is_atomic(committed_rows):
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Task, TaskCase, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        try:
            group = TestCaseGroup(id="g-1", name="分组")
            case = TestCase(id="tc-1", name="用例", group_id=group.id, config={})
            task = Task(name="任务", type="api", status="running", total_cases=1, config={})
            db.session.add_all([group, case, task])
            db.session.commit()
            # VEGA-49：本测试真 commit 了，登记自己建的行，收尾按 id 删（不再 drop_all）
            committed_rows(task_id=task.id, case_ids=["tc-1"], group_ids=["g-1"])

            rel = TaskCase(task_id=task.id, test_case_id=case.id, status="pending", execution_status="pending")
            db.session.add(rel)
            db.session.commit()

            Session = sessionmaker(bind=db.engine)
            s1 = Session()
            s2 = Session()
            try:
                claimed1 = (
                    s1.query(TaskCase)
                    .filter(
                        TaskCase.id == rel.id,
                        TaskCase.task_id == task.id,
                        TaskCase.execution_status == "pending",
                    )
                    .update(
                    {TaskCase.execution_status: "queued"},
                        synchronize_session=False,
                    )
                )
                s1.commit()

                claimed2 = (
                    s2.query(TaskCase)
                    .filter(
                        TaskCase.id == rel.id,
                        TaskCase.task_id == task.id,
                        TaskCase.execution_status == "pending",
                    )
                    .update(
                    {TaskCase.execution_status: "queued"},
                        synchronize_session=False,
                    )
                )
                s2.commit()
            finally:
                s1.close()
                s2.close()
        finally:
            db.session.remove()

        assert claimed1 == 1
        assert claimed2 == 0


def test_api_executor_running_transition_is_idempotent(committed_rows):
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Task, TaskCase, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        try:
            group = TestCaseGroup(id="g-2", name="分组")
            case = TestCase(id="tc-2", name="用例", group_id=group.id, config={})
            task = Task(name="任务", type="api", status="running", total_cases=1, config={})
            db.session.add_all([group, case, task])
            db.session.commit()
            # VEGA-49：登记本测试 commit 的行，收尾按 id 删（不再 drop_all）
            committed_rows(task_id=task.id, case_ids=["tc-2"], group_ids=["g-2"])

            rel = TaskCase(task_id=task.id, test_case_id=case.id, status="running", execution_status="queued")
            db.session.add(rel)
            db.session.commit()

            Session = sessionmaker(bind=db.engine)
            s1 = Session()
            s2 = Session()
            try:
                updated1 = (
                    s1.query(TaskCase)
                    .filter(
                        TaskCase.id == rel.id,
                        TaskCase.task_id == task.id,
                        TaskCase.execution_status.in_(["pending", "queued"]),
                    )
                    .update(
                    {TaskCase.execution_status: "running"},
                        synchronize_session=False,
                    )
                )
                s1.commit()

                updated2 = (
                    s2.query(TaskCase)
                    .filter(
                        TaskCase.id == rel.id,
                        TaskCase.task_id == task.id,
                        TaskCase.execution_status.in_(["pending", "queued"]),
                    )
                    .update(
                    {TaskCase.execution_status: "running"},
                        synchronize_session=False,
                    )
                )
                s2.commit()
            finally:
                s1.close()
                s2.close()
        finally:
            db.session.remove()

        assert updated1 == 1
        assert updated2 == 0
