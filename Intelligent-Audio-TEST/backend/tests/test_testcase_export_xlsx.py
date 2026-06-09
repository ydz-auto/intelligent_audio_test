import io

import pandas as pd


def test_export_xlsx_contains_all_sheets_and_audio_configs():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Audio, Dimension, Tag, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        group = TestCaseGroup(id="group-1", name="测试分组A", description="分组描述A")
        tag = Tag(name="标签A", description="标签描述A", color="#1677FF")
        audio = Audio(
            name="测试音频.wav",
            file_path="static/audios/test.wav",
            size=1,
            duration=1.0,
        )
        dim = Dimension(
            name="BLEU",
            type="auto",
            result_type=1,
            weight=60,
            rule={"type": "direct"},
            api_endpoints=[],
        )

        db.session.add_all([group, tag, audio, dim])
        db.session.commit()

        tc = TestCase(
            id="tc-1",
            name="测试用例A",
            description="用例描述A",
            group_id=group.id,
            test_type="api",
            config={
                "audios": [
                    {
                        "audio_id": audio.id,
                        "spl": 65,
                        "playback_device_id": None,
                        "play_order": 1,
                    }
                ],
                "dimensions": [dim.id],
                "reference_params": [
                    {"code": "asr_reference_text", "type": "text", "value": "ASR参考文本"},
                    {"code": "translation_reference_text", "type": "text", "value": "翻译参考文本"},
                ],
            },
        )
        tc.tags.append(tag)
        db.session.add(tc)
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        "/api/v1/testcases/export",
        json={"ids": ["tc-1"], "format": "xlsx", "include_deleted": True},
    )

    assert resp.status_code == 200
    excel = pd.ExcelFile(io.BytesIO(resp.data))

    expected_sheets = {
        "TestCases",
        "AudioConfigs",
        "Dimensions",
        "Tags",
        "Groups",
        "CaseTags",
    }
    assert expected_sheets.issubset(set(excel.sheet_names))

    testcases_df = pd.read_excel(excel, sheet_name="TestCases")
    assert "GROUP_ID" in testcases_df.columns
    assert "NOISE_AUDIO_ID" in testcases_df.columns
    assert testcases_df.loc[0, "GROUP_ID"] == "group-1"

    audio_df = pd.read_excel(excel, sheet_name="AudioConfigs")
    assert len(audio_df) == 1
    assert audio_df.loc[0, "CASE_ID"] == "tc-1"
    assert audio_df.loc[0, "CASE_NAME"] == "测试用例A"
    assert audio_df.loc[0, "AUDIO_ID"] == 1
    assert audio_df.loc[0, "AUDIO_NAME"] == "测试音频.wav"

    dim_df = pd.read_excel(excel, sheet_name="Dimensions")
    assert len(dim_df) == 1
    assert dim_df.loc[0, "CASE_ID"] == "tc-1"
    assert dim_df.loc[0, "DIMENSION_ID"] == 1
    assert dim_df.loc[0, "DIMENSION_NAME"] == "BLEU"

    tags_df = pd.read_excel(excel, sheet_name="Tags")
    assert len(tags_df) == 1
    assert tags_df.loc[0, "TAG_ID"] == 1
    assert tags_df.loc[0, "TAG_NAME"] == "标签A"
    assert tags_df.loc[0, "TAG_COLOR"] == "#1677FF"

    groups_df = pd.read_excel(excel, sheet_name="Groups")
    assert len(groups_df) == 1
    assert groups_df.loc[0, "GROUP_ID"] == "group-1"
    assert groups_df.loc[0, "GROUP_NAME"] == "测试分组A"

    case_tags_df = pd.read_excel(excel, sheet_name="CaseTags")
    assert len(case_tags_df) == 1
    assert case_tags_df.loc[0, "CASE_ID"] == "tc-1"
    assert case_tags_df.loc[0, "TAG_ID"] == 1


def test_export_json_contains_audios():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Audio, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        group = TestCaseGroup(id="group-1", name="测试分组A", description="分组描述A")
        audio = Audio(
            name="测试音频.wav",
            file_path="static/audios/test.wav",
            size=1,
            duration=1.0,
        )
        db.session.add_all([group, audio])
        db.session.commit()

        tc = TestCase(
            id="tc-1",
            name="测试用例A",
            description="用例描述A",
            group_id=group.id,
            test_type="api",
            config={
                "audios": [
                    {
                        "audio_id": audio.id,
                        "spl": 65,
                        "playback_device_id": None,
                        "play_order": 1,
                    }
                ],
            },
        )
        db.session.add(tc)
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        "/api/v1/testcases/export",
        json={"ids": ["tc-1"], "format": "json", "include_deleted": True},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    exported = payload["data"]
    assert exported["totalCount"] == 1
    assert exported["testCases"][0]["audios"][0]["audioName"] == "测试音频.wav"


def test_export_json_tolerates_empty_playback_device_id_string():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Audio, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        group = TestCaseGroup(id="group-1", name="测试分组A", description="分组描述A")
        audio = Audio(
            name="测试音频.wav",
            file_path="static/audios/test.wav",
            size=1,
            duration=1.0,
        )
        db.session.add_all([group, audio])
        db.session.commit()

        tc = TestCase(
            id="tc-1",
            name="测试用例A",
            description="用例描述A",
            group_id=group.id,
            test_type="api",
            config={
                "audios": [
                    {
                        "audio_id": audio.id,
                        "spl": 65,
                        "playback_device_id": "",
                        "play_order": 1,
                    }
                ],
            },
        )
        db.session.add(tc)
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        "/api/v1/testcases/export",
        json={"ids": ["tc-1"], "format": "json", "include_deleted": True},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    audio_item = payload["data"]["testCases"][0]["audios"][0]
    assert audio_item.get("playbackDeviceId") is None


def test_get_one_tolerates_empty_playback_device_id_string():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Audio, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        group = TestCaseGroup(id="group-1", name="测试分组A", description="分组描述A")
        audio = Audio(
            name="测试音频.wav",
            file_path="static/audios/test.wav",
            size=1,
            duration=1.0,
        )
        db.session.add_all([group, audio])
        db.session.commit()

        tc = TestCase(
            id="tc-1",
            name="测试用例A",
            description="用例描述A",
            group_id=group.id,
            test_type="api",
            config={
                "audios": [
                    {
                        "audio_id": audio.id,
                        "spl": 65,
                        "playback_device_id": "",
                        "play_order": 1,
                    }
                ],
            },
        )
        db.session.add(tc)
        db.session.commit()

    client = app.test_client()
    resp = client.get("/api/v1/testcases/tc-1")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    audio_item = payload["data"]["audios"][0]
    assert audio_item.get("playbackDeviceId") is None


def test_exported_xlsx_can_be_imported_back():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Audio, Dimension, Tag, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        group = TestCaseGroup(id="group-1", name="测试分组A", description="分组描述A")
        tag = Tag(name="标签A", description="标签描述A", color="#1677FF")
        audio = Audio(
            name="测试音频.wav",
            file_path="static/audios/test.wav",
            size=1,
            duration=1.0,
        )
        noise_audio = Audio(
            name="噪声.wav",
            file_path="static/audios/noise.wav",
            size=1,
            duration=1.0,
            audio_type="noise",
        )
        dim = Dimension(
            name="BLEU",
            type="auto",
            result_type=1,
            weight=60,
            rule={"type": "direct"},
            api_endpoints=[],
        )
        db.session.add_all([group, tag, audio, noise_audio, dim])
        db.session.commit()

        tc = TestCase(
            id="tc-1",
            name="测试用例A",
            description="用例描述A",
            group_id=group.id,
            test_type="api",
            config={
                "audios": [
                    {
                        "audio_id": audio.id,
                        "spl": 65,
                        "playback_device_id": None,
                        "play_order": 1,
                    }
                ],
                "dimensions": [dim.id],
                "background_noise": {"audio_id": noise_audio.id, "spl": 50},
            },
        )
        tc.tags.append(tag)
        db.session.add(tc)
        db.session.commit()

    client = app.test_client()
    export_resp = client.post(
        "/api/v1/testcases/export",
        json={"ids": ["tc-1"], "format": "xlsx", "include_deleted": True},
    )
    assert export_resp.status_code == 200

    with app.app_context():
        tc = db.session.get(TestCase, "tc-1")
        tc.config = {}
        tc.tags = []
        db.session.commit()

    import_resp = client.post(
        "/api/v1/testcases/import",
        data={"file": (io.BytesIO(export_resp.data), "testcases_export.xlsx")},
        content_type="multipart/form-data",
    )
    assert import_resp.status_code == 200
    payload = import_resp.get_json()
    assert payload["success"] is True

    with app.app_context():
        tc = db.session.get(TestCase, "tc-1")
        assert tc is not None
        assert tc.group_id == "group-1"
        assert tc.config["audios"][0]["audio_id"] == 1
        assert tc.config["dimensions"] == [1]
        assert tc.config["background_noise"]["audio_id"] == 2
        assert tc.tags[0].name == "标签A"


def test_import_update_restores_deleted_testcase():
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Audio, TestCase, TestCaseGroup

    app = create_app("testing")

    with app.app_context():
        group = TestCaseGroup(id="group-1", name="测试分组A", description="分组描述A")
        audio = Audio(
            name="测试音频.wav",
            file_path="static/audios/test.wav",
            size=1,
            duration=1.0,
        )
        db.session.add_all([group, audio])
        db.session.commit()

        tc = TestCase(
            id="tc-1",
            name="测试用例A",
            description="用例描述A",
            group_id=group.id,
            test_type="api",
            config={
                "audios": [{"audio_id": audio.id, "spl": 65, "play_order": 1}],
            },
            deleted=False,
        )
        db.session.add(tc)
        db.session.commit()

    client = app.test_client()
    export_resp = client.post(
        "/api/v1/testcases/export",
        json={"ids": ["tc-1"], "format": "xlsx", "include_deleted": True},
    )
    assert export_resp.status_code == 200

    with app.app_context():
        tc = db.session.get(TestCase, "tc-1")
        tc.deleted = True
        db.session.commit()

    import_resp = client.post(
        "/api/v1/testcases/import",
        data={"file": (io.BytesIO(export_resp.data), "testcases_export.xlsx")},
        content_type="multipart/form-data",
    )
    assert import_resp.status_code == 200

    with app.app_context():
        tc = db.session.get(TestCase, "tc-1")
        assert tc is not None
        assert tc.deleted is False
