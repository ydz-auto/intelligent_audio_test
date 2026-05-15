from backend.app import create_app
from backend.models.database import db
from backend.models.models import Report


def test_report_update_persists_headers_and_names():
    app = create_app("testing")
    client = app.test_client()

    with app.app_context():
        report = Report(
            name="r1",
            type="comparison",
            status="draft",
            summary={
                "resource_headers": [],
                "case_categories": [{"id": "g1", "name": "分组A"}],
                "all_case_tags": [{"id": 1, "name": "标签A"}],
            },
        )
        db.session.add(report)
        db.session.commit()
        report_id = report.id

    resp = client.put(
        f"/api/v1/reports/{report_id}",
        json={
            "summary": {
                "resourceHeaders": [
                    {
                        "key": "t1-202601010000-2-mock1",
                        "label": "任务名-mock1-v1",
                        "type": "api",
                        "id": 2,
                        "name": "mock1",
                        "version": "v1",
                        "editable": True,
                    }
                ],
                "caseCategories": [{"id": "g1", "name": "分组A-改"}],
                "allCaseTags": [{"id": 1, "name": "标签A-改"}],
            }
        },
    )
    assert resp.status_code == 200

    resp2 = client.get(f"/api/v1/reports/{report_id}")
    assert resp2.status_code == 200
    payload = resp2.get_json()
    assert payload["success"] is True

    summary = payload["data"]["summary"]
    assert summary["resourceHeaders"][0]["label"] == "任务名-mock1-v1"
    assert summary["caseCategories"][0]["name"] == "分组A-改"
    assert summary["allCaseTags"][0]["name"] == "标签A-改"

