# -*- coding: utf-8 -*-
"""INT-2095: full before snapshot of the 10 soft-deleted rows."""
import os, json, sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2
DSN = os.environ.get('DATABASE_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:15432/intelligent_audio_test')
conn = psycopg2.connect(DSN)
cur = conn.cursor()
cur.execute("""
SELECT id, algorithm_type, param_code, param_name, label, param_type, required,
       default_value, help_text, ui_order, hidden, scope,
       min_value, max_value, step, unit,
       annotation_code, field_path, deleted, created_at, updated_at
FROM case_algorithm_params
WHERE algorithm_type = 'voice_llm'
ORDER BY ui_order, id
""")
cols = [d[0] for d in cur.description]
rows = [dict(zip(cols, r)) for r in cur.fetchall()]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int2095_case_params_before.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
print(f"snapshot written to {out}")
for r in rows:
    print(f"id={r['id']} code={r['param_code']} deleted={r['deleted']} label={r['label']!r} help={r['help_text']!r}")
conn.close()
