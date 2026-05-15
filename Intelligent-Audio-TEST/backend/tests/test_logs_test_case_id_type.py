from datetime import datetime


def test_get_logs_allows_uuid_test_case_id():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Log

    app = create_app("testing")
    unique_keyword = "pytest_uuid_test_case_id_keyword"
    test_case_id = "80a79d19-1177-447d-8674-f0f510c8bd87"

    with app.app_context():
        log = Log(
            time=datetime.now(),
            level="INFO",
            category="test",
            module="Pytest",
            source="pytest",
            content=unique_keyword,
            test_case_id=test_case_id,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    client = app.test_client()
    resp = client.get(f"/api/v1/logs?keyword={unique_keyword}&page=1&perPage=10")
    assert resp.status_code == 200

    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["code"] in (0, 200)

    items = payload["data"]["items"]
    assert any(item["id"] == log_id and item["testCaseId"] == test_case_id for item in items)
