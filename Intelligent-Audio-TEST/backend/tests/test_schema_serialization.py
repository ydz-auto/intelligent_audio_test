def test_success_response_serializes_pydantic_models_with_camel_case():
    from backend.app import create_app
    from backend.utils.response import success_response
    from backend.schemas.group import GroupItem, GroupListData

    app = create_app("testing")

    @app.get("/__test__/schema/groups")
    def _schema_groups():
        payload = GroupListData(
            items=[
                GroupItem(
                    id="g1",
                    name="n",
                    description=None,
                    created_at="2026-01-01T00:00:00",
                    updated_at="2026-01-01T00:00:00",
                    test_case_count=1,
                )
            ],
            total=1,
            page=1,
            per_page=10,
            pages=1,
        )
        return success_response(payload)

    client = app.test_client()
    resp = client.get("/__test__/schema/groups")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["success"] is True
    data = body["data"]
    assert data["perPage"] == 10
    assert data["items"][0]["testCaseCount"] == 1

