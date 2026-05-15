
import sys
import os

# Add the backend directory and its parent to the sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
parent_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, parent_dir)

from app import create_app
from backend.models.database import db
from backend.models.models import Audio

app = create_app('default')

with app.app_context():
    # Verify which db instance we are using
    print(f"DB instance in script: {id(db)}")
    from flask import current_app
    # Get all audios
    audios = Audio.query.all()
    print(f"Total audios: {len(audios)}")
    for audio in audios:
        print(f"ID: {audio.id}, Name: {audio.name}, Path: {audio.file_path}")
