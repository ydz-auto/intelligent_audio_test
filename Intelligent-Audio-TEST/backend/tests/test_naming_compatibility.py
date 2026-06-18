def test_request_accepts_camel_and_response_returns_camel():
    from flask import request

    from backend.app import create_app
    from backend.utils.web.response import success_response

    app = create_app("testing")

    @app.post("/__test__/naming")
    def _naming_test():
        return success_response(
            data={
                "json": request.get_json(),
                "per_page": request.args.get("per_page"),
            }
        )

    client = app.test_client()

    resp = client.post(
        "/__test__/naming?perPage=3",
        json={
            "taskId": 1,
            "nestedValue": {"innerKey": 2},
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()

    assert payload["success"] is True
    assert payload["code"] in (0, 200)
    assert payload["data"]["perPage"] == "3"
    assert payload["data"]["json"]["taskId"] == 1
    assert payload["data"]["json"]["nestedValue"]["innerKey"] == 2


def test_request_snake_keys_keep_e2e_tokens():
    from flask import request

    from backend.app import create_app
    from backend.utils.web.response import success_response

    app = create_app("testing")

    @app.post("/__test__/naming-e2e")
    def _naming_e2e_test():
        dims = (request.get_json() or {}).get("dimensions") or {}
        return success_response(data={"dimension_keys": sorted(dims.keys())})

    client = app.test_client()

    resp = client.post(
        "/__test__/naming-e2e",
        json={
            "dimensions": {
                "e2e": [1],
                "translation_reference_text_e2e": "x",
            }
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["code"] in (0, 200)

    keys = payload["data"]["dimensionKeys"]
    assert "e2e" in keys
    assert "e_2e" not in keys
    assert "translation_reference_text_e2e" in keys
    assert "translation_reference_text_e_2e" not in keys
