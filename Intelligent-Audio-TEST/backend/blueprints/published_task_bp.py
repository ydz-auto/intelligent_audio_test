from flask import Blueprint
from backend.controllers.published_task_controller import PublishedTaskController

published_task_bp = Blueprint('published_tasks', __name__)


@published_task_bp.route('', methods=['POST'])
def publish():
    return PublishedTaskController.publish()


@published_task_bp.route('', methods=['GET'])
def get_all():
    return PublishedTaskController.get_all()


@published_task_bp.route('/<int:published_task_id>', methods=['GET'])
def get_one(published_task_id):
    return PublishedTaskController.get_one(published_task_id)


@published_task_bp.route('/<int:published_task_id>/execute', methods=['POST'])
def execute(published_task_id):
    return PublishedTaskController.execute(published_task_id)


@published_task_bp.route('/<int:published_task_id>/versions', methods=['POST'])
def create_version(published_task_id):
    return PublishedTaskController.create_version(published_task_id)


@published_task_bp.route('/<int:published_task_id>/archive', methods=['POST'])
def archive(published_task_id):
    return PublishedTaskController.archive(published_task_id)
