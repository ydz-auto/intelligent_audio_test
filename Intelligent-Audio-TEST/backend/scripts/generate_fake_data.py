import os
import sys
import random
from datetime import datetime
from faker import Faker

# 将项目根目录添加到 python 路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app import create_app
from backend.models.database import db
from backend.models.models import (
    User, Permission, UserPermission, Tag, TestCaseGroup, TestCase, 
    TestCaseTag, TestCaseAudio, TestCaseDimension, Device, DeviceTag,
    TranslationDirection, Audio, AudioAnnotation, AudioTag, API,
    Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TestResult,
    TestResultDimension, Report, Category, Dimension, Log
)

# 初始化 Faker
fake = Faker('zh_CN')

# 生成假数据的数量配置
DATA_COUNT = {
    'User': 5,
    'Permission': 10,
    'Tag': 15,
    'TestCaseGroup': 5,
    'TestCase': 20,
    'TestCaseAudio': 40,
    'TranslationDirection': 10,
    'Audio': 30,
    'Device': 10,
    'API': 5,
    'Task': 10,
    'Category': 5,
    'Dimension': 15,
    'TestResult': 50,
    'Report': 10
}

def generate_fake_data():
    app = create_app()
    with app.app_context():
        print("开始生成假数据...")
        
        # 1. 生成权限数据
        print("\n--- 生成 Permission 数据 ---")
        permissions = []
        permission_names = [
            'read_users', 'write_users', 'read_test_cases', 'write_test_cases',
            'read_devices', 'write_devices', 'read_apis', 'write_apis',
            'run_tasks', 'view_reports', 'manage_system'
        ]
        
        # 检查是否已经存在数据，如果存在则跳过
        existing_permissions = Permission.query.all()
        if existing_permissions:
            print(f"已经存在 {len(existing_permissions)} 条 Permission 数据，跳过生成")
            permissions = existing_permissions
        else:
            for i, name in enumerate(permission_names[:DATA_COUNT['Permission']]):
                permission = Permission(
                    name=name,
                    description=fake.text(max_nb_chars=100)
                )
                permissions.append(permission)
                db.session.add(permission)
            db.session.commit()
            print(f"生成了 {len(permissions)} 条 Permission 数据")
        
        # 2. 生成用户数据
        print("\n--- 生成 User 数据 ---")
        users = []
        existing_users = User.query.all()
        if existing_users:
            print(f"已经存在 {len(existing_users)} 条 User 数据，跳过生成")
            users = existing_users
        else:
            for i in range(DATA_COUNT['User']):
                user = User(
                    username=fake.user_name(),
                    password_hash='fake_password_hash',
                    email=fake.email(),
                    role=random.choice(['admin', 'editor', 'viewer']),
                    status=random.choice(['active', 'inactive'])
                )
                users.append(user)
                db.session.add(user)
            db.session.commit()
            print(f"生成了 {len(users)} 条 User 数据")
        
        # 3. 生成用户权限关联数据
        print("\n--- 生成 UserPermission 数据 ---")
        user_permissions = []
        existing_user_permissions = UserPermission.query.all()
        if existing_user_permissions:
            print(f"已经存在 {len(existing_user_permissions)} 条 UserPermission 数据，跳过生成")
            user_permissions = existing_user_permissions
        else:
            for user in users:
                # 每个用户随机分配 2-5 个权限
                assigned_permissions = random.sample(permissions, random.randint(2, 5))
                for permission in assigned_permissions:
                    user_perm = UserPermission(
                        user_id=user.id,
                        permission_id=permission.id
                    )
                    user_permissions.append(user_perm)
                    db.session.add(user_perm)
            db.session.commit()
            print(f"生成了 {len(user_permissions)} 条 UserPermission 数据")
        
        # 4. 生成标签数据
        print("\n--- 生成 Tag 数据 ---")
        tags = []
        tag_names = [
            '重要', '常用', '测试用', '生产用', '新功能', '音频质量',
            '稳定性测试', '兼容性测试', '性能测试', '回归测试',
            'Android', 'iOS', 'HarmonyOS', '中文', '英文'
        ]
        
        existing_tags = Tag.query.all()
        if existing_tags:
            print(f"已经存在 {len(existing_tags)} 条 Tag 数据，跳过生成")
            tags = existing_tags
        else:
            for i, name in enumerate(tag_names[:DATA_COUNT['Tag']]):
                tag = Tag(
                    name=name,
                    description=fake.text(max_nb_chars=100),
                    color=fake.color()
                )
                tags.append(tag)
                db.session.add(tag)
            db.session.commit()
            print(f"生成了 {len(tags)} 条 Tag 数据")
        
        # 5. 生成测试用例分组数据
        print("\n--- 生成 TestCaseGroup 数据 ---")
        test_case_groups = []
        for i in range(DATA_COUNT['TestCaseGroup']):
            group = TestCaseGroup(
                id=fake.uuid4(),
                name=fake.company() + '测试组',
                description=fake.text(max_nb_chars=150)
            )
            test_case_groups.append(group)
            db.session.add(group)
        db.session.commit()
        print(f"生成了 {len(test_case_groups)} 条 TestCaseGroup 数据")
        
        # 6. 生成翻译语向数据
        print("\n--- 生成 TranslationDirection 数据 ---")
        translation_directions = []
        language_pairs = [
            ('zh', 'en'), ('en', 'zh'), ('zh', 'ja'), ('ja', 'zh'),
            ('zh', 'ko'), ('ko', 'zh'), ('zh', 'fr'), ('fr', 'zh'),
            ('zh', 'de'), ('de', 'zh')
        ]
        
        for i, (source, target) in enumerate(language_pairs[:DATA_COUNT['TranslationDirection']]):
            direction = TranslationDirection(
                source_language=source,
                target_language=target,
                description=f"{source}到{target}的翻译"
            )
            translation_directions.append(direction)
            db.session.add(direction)
        db.session.commit()
        print(f"生成了 {len(translation_directions)} 条 TranslationDirection 数据")
        
        # 7. 生成音频数据
        print("\n--- 生成 Audio 数据 ---")
        audios = []
        for i in range(DATA_COUNT['Audio']):
            audio = Audio(
                name=fake.word() + '_audio',
                original_filename=fake.file_name(extension='wav'),
                file_path=f"uploads/audios/{fake.uuid4()}.wav",
                size=random.randint(1000000, 10000000),
                duration=random.uniform(1.0, 60.0),
                sample_rate=random.choice([8000, 16000, 22050, 44100]),
                channels=random.choice([1, 2]),
                bitrate=random.choice([128000, 192000, 256000]),
                format='wav',
                audio_type=random.choice(['dry', 'noise', 'prompt']),
                asr_text=fake.text(max_nb_chars=200),
                description=fake.text(max_nb_chars=150)
            )
            audios.append(audio)
            db.session.add(audio)
        db.session.commit()
        print(f"生成了 {len(audios)} 条 Audio 数据")
        
        # 8. 生成音频标注数据 (使用 AudioAnnotation 替代 AudioTranslation)
        print("\n--- 生成 AudioAnnotation 数据 ---")
        audio_annotations = []
        for audio in audios:
            # 每个音频随机分配 1-3 个翻译语向的标注
            assigned_directions = random.sample(translation_directions, random.randint(1, 3))
            for direction in assigned_directions:
                annotation = AudioAnnotation(
                    audio_id=audio.id,
                    format='json',
                    name=f"翻译-{direction.source_language}-{direction.target_language}",
                    data={'text': fake.text(max_nb_chars=200)},
                    source_language=direction.source_language,
                    target_language=direction.target_language
                )
                audio_annotations.append(annotation)
                db.session.add(annotation)
        db.session.commit()
        print(f"生成了 {len(audio_annotations)} 条 AudioAnnotation 数据")
        
        # 9. 生成音频标签关联数据
        print("\n--- 生成 AudioTag 数据 ---")
        audio_tags = []
        for audio in audios:
            # 每个音频随机分配 1-3 个标签
            assigned_tags = random.sample(tags, random.randint(1, 3))
            for tag in assigned_tags:
                audio_tag = AudioTag(
                    audio_id=audio.id,
                    tag_id=tag.id
                )
                audio_tags.append(audio_tag)
                db.session.add(audio_tag)
        db.session.commit()
        print(f"生成了 {len(audio_tags)} 条 AudioTag 数据")
        
        # 10. 生成设备数据
        print("\n--- 生成 Device 数据 ---")
        devices = []
        for i in range(DATA_COUNT['Device']):
            device = Device(
                name=fake.word() + '_device',
                model=fake.word() + '-' + str(fake.random_number(digits=4)),
                description=fake.text(max_nb_chars=150),
                type=random.choice(['phone', 'tablet']),
                system=random.choice(['Android', 'iOS', 'HarmonyOS']),
                system_version=str(random.randint(1, 14)) + '.' + str(random.randint(0, 9)),
                app_name=fake.company() + ' App',
                app_version=str(random.randint(1, 3)) + '.' + str(random.randint(0, 9)) + '.' + str(random.randint(0, 9)),
                location=fake.address(),
                max_audio_duration=random.uniform(30.0, 300.0),
                needs_prompt_audio=random.choice([True, False]),
                status=random.choice(['online', 'offline']),
                last_online_at=fake.date_time_this_year()
            )
            devices.append(device)
            db.session.add(device)
        db.session.commit()
        print(f"生成了 {len(devices)} 条 Device 数据")
        
        # 11. 生成设备标签关联数据
        print("\n--- 生成 DeviceTag 数据 ---")
        device_tags = []
        for device in devices:
            # 每个设备随机分配 1-3 个标签
            assigned_tags = random.sample(tags, random.randint(1, 3))
            for tag in assigned_tags:
                device_tag = DeviceTag(
                    device_id=device.id,
                    tag_id=tag.id
                )
                device_tags.append(device_tag)
                db.session.add(device_tag)
        db.session.commit()
        print(f"生成了 {len(device_tags)} 条 DeviceTag 数据")
        
        # 12. 生成 API 数据
        print("\n--- 生成 API 数据 ---")
        apis = []
        for i in range(DATA_COUNT['API']):
            api = API(
                name=fake.company() + ' API',
                endpoint=fake.url(),
                description=fake.text(max_nb_chars=150),
                status=random.choice(['online', 'offline']),
                meta={
                    'api_key': fake.uuid4(),
                    'headers': {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {fake.uuid4()}'
                    }
                },
                max_process=random.randint(1, 10),
                max_timeout=random.randint(10, 60),
                max_audio_duration=random.randint(30, 300),
                health_score=random.uniform(80.0, 100.0)
            )
            apis.append(api)
            db.session.add(api)
        db.session.commit()
        print(f"生成了 {len(apis)} 条 API 数据")
        
        # 13. 生成评估分类数据
        print("\n--- 生成 Category 数据 ---")
        categories = []
        category_names = ['准确性', '流畅度', '响应速度', '语音质量', '综合评估']
        for i, name in enumerate(category_names[:DATA_COUNT['Category']]):
            category = Category(
                name=name,
                description=fake.text(max_nb_chars=150),
                icon=random.choice(['accuracy', 'fluency', 'speed', 'quality', 'comprehensive'])
            )
            categories.append(category)
            db.session.add(category)
        db.session.commit()
        print(f"生成了 {len(categories)} 条 Category 数据")
        
        # 14. 生成评估维度数据
        print("\n--- 生成 Dimension 数据 ---")
        dimensions = []
        for i in range(DATA_COUNT['Dimension']):
            dimension = Dimension(
                name=fake.word() + '_dimension',
                keywords=fake.word() + ',' + fake.word() + ',' + fake.word(),
                description=fake.text(max_nb_chars=150),
                category_id=random.choice(categories).id,
                api_url=fake.url(),
                type=random.choice(['auto', 'manual']),
                result_type=random.choice([1, 2, 3]),
                result_min=0.0,
                result_max=100.0,
                decimal_places=2,
                weight=random.randint(1, 5),
                max_process=random.randint(1, 10),
                timeout=random.randint(10, 60),
                exec_time=random.randint(5, 30),
                rule={
                    'pass_threshold': 60.0,
                    'excellent_threshold': 90.0
                },
                api_settings={
                    'method': 'POST',
                    'headers': {
                        'Content-Type': 'application/json'
                    }
                },
                api_status=random.choice(['online', 'offline'])
            )
            dimensions.append(dimension)
            db.session.add(dimension)
        db.session.commit()
        print(f"生成了 {len(dimensions)} 条 Dimension 数据")
        
        # 15. 生成测试用例数据
        print("\n--- 生成 TestCase 数据 ---")
        test_cases = []
        for i in range(DATA_COUNT['TestCase']):
            test_case = TestCase(
                id=fake.uuid4(),
                name=fake.word() + '_testcase',
                description=fake.text(max_nb_chars=200),
                config={
                    'param1': fake.word(),
                    'param2': random.randint(1, 100),
                    'param3': random.choice([True, False])
                },
                group_id=random.choice(test_case_groups).id,
                background_noise_id=random.choice(audios).id if random.choice([True, False]) else None,
                background_noise_spl=random.uniform(30.0, 90.0)
            )
            test_cases.append(test_case)
            db.session.add(test_case)
        db.session.commit()
        print(f"生成了 {len(test_cases)} 条 TestCase 数据")
        
        # 16. 生成测试用例标签关联数据
        print("\n--- 生成 TestCaseTag 数据 ---")
        test_case_tags = []
        for test_case in test_cases:
            # 每个测试用例随机分配 1-3 个标签
            assigned_tags = random.sample(tags, random.randint(1, 3))
            for tag in assigned_tags:
                test_case_tag = TestCaseTag(
                    test_case_id=test_case.id,
                    tag_id=tag.id
                )
                test_case_tags.append(test_case_tag)
                db.session.add(test_case_tag)
        db.session.commit()
        print(f"生成了 {len(test_case_tags)} 条 TestCaseTag 数据")
        
        # 17. 生成测试用例音频关联数据
        print("\n--- 生成 TestCaseAudio 数据 ---")
        test_case_audios = []
        for i in range(DATA_COUNT['TestCaseAudio']):
            test_case_audio = TestCaseAudio(
                test_case_id=random.choice(test_cases).id,
                audio_id=random.choice(audios).id,
                test_type=random.choice(['api', 'e2e']),
                spl=random.uniform(50.0, 100.0),
                play_order=random.randint(0, 10)
            )
            test_case_audios.append(test_case_audio)
            db.session.add(test_case_audio)
        db.session.commit()
        print(f"生成了 {len(test_case_audios)} 条 TestCaseAudio 数据")
        
        # 18. 生成测试用例维度关联数据
        print("\n--- 生成 TestCaseDimension 数据 ---")
        test_case_dimensions = []
        for test_case in test_cases:
            # 每个测试用例随机分配 1-3 个维度
            assigned_dimensions = random.sample(dimensions, random.randint(1, 3))
            for dimension in assigned_dimensions:
                test_case_dimension = TestCaseDimension(
                    test_case_id=test_case.id,
                    dimension_id=dimension.id
                )
                test_case_dimensions.append(test_case_dimension)
                db.session.add(test_case_dimension)
        db.session.commit()
        print(f"生成了 {len(test_case_dimensions)} 条 TestCaseDimension 数据")
        
        # 21. 生成测试任务数据
        print("\n--- 生成 Task 数据 ---")
        tasks = []
        for i in range(DATA_COUNT['Task']):
            task = Task(
                name=fake.word() + '_task',
                description=fake.text(max_nb_chars=200),
                type=random.choice(['api', 'e2e']),
                status=random.choice(['pending', 'running', 'completed', 'failed', 'stopped']),
                config={
                    'param1': fake.word(),
                    'param2': random.randint(1, 100)
                },
                total_cases=random.randint(5, 20),
                completed_cases=random.randint(0, 20),
                failed_cases=random.randint(0, 10),
                created_by=random.choice(users).id,
                started_at=fake.date_time_this_year() if random.choice([True, False]) else None,
                completed_at=fake.date_time_this_year() if random.choice([True, False]) else None,
                estimated_time=random.randint(60, 3600),
                actual_duration=random.randint(0, 3600) if random.choice([True, False]) else None
            )
            tasks.append(task)
            db.session.add(task)
        db.session.commit()
        print(f"生成了 {len(tasks)} 条 Task 数据")
        
        # 22. 生成任务标签关联数据
        print("\n--- 生成 TaskTag 数据 ---")
        task_tags = []
        for task in tasks:
            # 每个任务随机分配 1-3 个标签
            assigned_tags = random.sample(tags, random.randint(1, 3))
            for tag in assigned_tags:
                task_tag = TaskTag(
                    task_id=task.id,
                    tag_id=tag.id
                )
                task_tags.append(task_tag)
                db.session.add(task_tag)
        db.session.commit()
        print(f"生成了 {len(task_tags)} 条 TaskTag 数据")
        
        # 23. 生成任务用例关联数据
        print("\n--- 生成 TaskCase 数据 ---")
        task_cases = []
        for task in tasks:
            # 每个任务随机分配 1-5 个用例
            assigned_cases = random.sample(test_cases, random.randint(1, 5))
            for test_case in assigned_cases:
                task_case = TaskCase(
                    task_id=task.id,
                    test_case_id=test_case.id,
                    status=random.choice(['pending', 'running', 'completed', 'failed']),
                    started_at=fake.date_time_this_year() if random.choice([True, False]) else None,
                    completed_at=fake.date_time_this_year() if random.choice([True, False]) else None,
                    duration=random.randint(10, 600) if random.choice([True, False]) else None
                )
                task_cases.append(task_case)
                db.session.add(task_case)
        db.session.commit()
        print(f"生成了 {len(task_cases)} 条 TaskCase 数据")
        
        # 24. 生成任务设备关联数据
        print("\n--- 生成 TaskDevice 数据 ---")
        task_devices = []
        for task in tasks:
            # 每个任务随机分配 1-3 个设备
            assigned_devices = random.sample(devices, random.randint(1, 3))
            for device in assigned_devices:
                task_device = TaskDevice(
                    task_id=task.id,
                    device_id=device.id
                )
                task_devices.append(task_device)
                db.session.add(task_device)
        db.session.commit()
        print(f"生成了 {len(task_devices)} 条 TaskDevice 数据")
        
        # 25. 生成任务 API 关联数据
        print("\n--- 生成 TaskAPI 数据 ---")
        task_apis = []
        for task in tasks:
            # 每个任务随机分配 1-2 个 API
            assigned_apis = random.sample(apis, random.randint(1, 2))
            for api in assigned_apis:
                task_api = TaskAPI(
                    task_id=task.id,
                    api_id=api.id
                )
                task_apis.append(task_api)
                db.session.add(task_api)
        db.session.commit()
        print(f"生成了 {len(task_apis)} 条 TaskAPI 数据")
        
        # 26. 生成测试结果数据
        print("\n--- 生成 TestResult 数据 ---")
        test_results = []
        algorithm_types = ['translation', 'asr', 'tts', 'speaker_recognition']
        for i in range(DATA_COUNT['TestResult']):
            algo_type = random.choice(algorithm_types)
            test_result = TestResult(
                task_id=random.choice(tasks).id,
                test_case_id=random.choice(test_cases).id,
                device_id=random.choice(devices).id,
                api_id=random.choice(apis).id,
                algorithm_type=algo_type,
                status=random.choice(['completed', 'failed']),
                response_time=random.randint(100, 5000),
                algorithm_result={
                    'asr_result': fake.text(max_nb_chars=200) if algo_type in ['translation', 'asr'] else None,
                    'translation_result': fake.text(max_nb_chars=200) if algo_type == 'translation' else None,
                },
                execution_steps=[
                    {
                        'step': 1,
                        'name': '准备设备',
                        'status': 'completed',
                        'timestamp': str(fake.date_time_this_year())
                    },
                    {
                        'step': 2,
                        'name': '播放音频',
                        'status': 'completed',
                        'timestamp': str(fake.date_time_this_year())
                    },
                    {
                        'step': 3,
                        'name': '获取结果',
                        'status': 'completed',
                        'timestamp': str(fake.date_time_this_year())
                    }
                ],
                result_data={
                    'raw_score': random.uniform(0.0, 100.0),
                    'metrics': {
                        'bleu': random.uniform(0.0, 1.0),
                        'wer': random.uniform(0.0, 1.0)
                    }
                },
                error_message=fake.text(max_nb_chars=100) if random.choice([True, False]) else None
            )
            test_results.append(test_result)
            db.session.add(test_result)
        db.session.commit()
        print(f"生成了 {len(test_results)} 条 TestResult 数据")
        
        # 27. 生成测试结果维度数据
        print("\n--- 生成 TestResultDimension 数据 ---")
        test_result_dimensions = []
        for test_result in test_results:
            # 每个测试结果随机分配 1-3 个维度
            assigned_dimensions = random.sample(dimensions, random.randint(1, 3))
            algo_type = test_result.algorithm_type  # 继承 TestResult 的算法类型
            for dimension in assigned_dimensions:
                test_result_dimension = TestResultDimension(
                    test_result_id=test_result.id,
                    dimension_id=dimension.id,
                    algorithm_type=algo_type,
                    dimension_value=random.uniform(0.0, 100.0),
                    score=random.uniform(0.0, 100.0),
                    status=random.choice(['completed', 'failed']),
                    error_message=fake.text(max_nb_chars=100) if random.choice([True, False]) else None
                )
                test_result_dimensions.append(test_result_dimension)
                db.session.add(test_result_dimension)
        db.session.commit()
        print(f"生成了 {len(test_result_dimensions)} 条 TestResultDimension 数据")
        
        # 28. 生成测试报告数据
        print("\n--- 生成 Report 数据 ---")
        reports = []
        for i in range(DATA_COUNT['Report']):
            report = Report(
                name=fake.word() + '_report',
                type=random.choice(['summary', 'detail', 'comparison']),
                description=fake.text(max_nb_chars=200),
                task_id=random.choice(tasks).id,
                status=random.choice(['draft', 'published']),
                summary={
                    'total_tests': random.randint(10, 100),
                    'completed_tests': random.randint(5, 100),
                    'failed_tests': random.randint(0, 50),
                    'pass_rate': random.uniform(0.5, 1.0)
                },
                comparison_data={
                    'previous_pass_rate': random.uniform(0.5, 1.0),
                    'current_pass_rate': random.uniform(0.5, 1.0),
                    'trend': random.choice(['up', 'down', 'stable'])
                },
                analysis=fake.text(max_nb_chars=500)
            )
            reports.append(report)
            db.session.add(report)
        db.session.commit()
        print(f"生成了 {len(reports)} 条 Report 数据")
        
        # 29. 生成日志数据
        print("\n--- 生成 Log 数据 ---")
        logs = []
        for i in range(100):
            log = Log(
                time=fake.date_time_this_year(),
                level=random.choice(['DEBUG', 'INFO', 'WARN', 'ERROR']),
                category=random.choice(['system', 'task', 'device', 'frontend', 'backend', 'execution', 'api', 'audio', 'user', 'test']).lower(),
                module=fake.word() + '_module',
                source=fake.word() + '_source',
                content=fake.text(max_nb_chars=200),
                mark=random.choice(['yellow', 'red', 'green', 'blue', None]),
                device_id=random.choice(devices).id if random.choice([True, False]) else None,
                task_id=random.choice(tasks).id if random.choice([True, False]) else None,
                user_id=random.choice(users).id if random.choice([True, False]) else None,
                thread_id=fake.uuid4()
            )
            logs.append(log)
            db.session.add(log)
        db.session.commit()
        print(f"生成了 {len(logs)} 条 Log 数据")
        
        print("\n所有假数据生成完成！")
        print("注意：playback_devices 表未生成数据，因为用户要求跳过该表。")

if __name__ == "__main__":
    generate_fake_data()
