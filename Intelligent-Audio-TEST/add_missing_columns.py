"""一次性迁移：给 test_cases 表添加缺失的 algorithm_params 和 reference_params 列"""
from backend.app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    db.session.execute(text(
        'ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS algorithm_params JSON'
    ))
    db.session.execute(text(
        'ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS reference_params JSON'
    ))
    db.session.commit()
    print('OK: columns added')
