from flask import Blueprint
from backend.controllers.tag_controller import TagCategoryController, TagController

tag_bp = Blueprint('tag', __name__)


@tag_bp.route('/categories', methods=['GET'])
def get_categories():
    return TagCategoryController.get_all()


@tag_bp.route('/categories/<int:category_id>', methods=['GET'])
def get_category(category_id):
    return TagCategoryController.get_one(category_id)


@tag_bp.route('/categories', methods=['POST'])
def create_category():
    return TagCategoryController.create()


@tag_bp.route('/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    return TagCategoryController.update(category_id)


@tag_bp.route('/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    return TagCategoryController.delete(category_id)


@tag_bp.route('', methods=['GET'])
def get_tags():
    return TagController.get_all()


@tag_bp.route('/names', methods=['GET'])
def get_tag_names():
    return TagController.get_all_names()


@tag_bp.route('/by-category', methods=['GET'])
def get_tags_by_category():
    return TagController.get_tags_by_category()


@tag_bp.route('/<int:tag_id>', methods=['GET'])
def get_tag(tag_id):
    return TagController.get_one(tag_id)


@tag_bp.route('', methods=['POST'])
def create_tag():
    return TagController.create()


@tag_bp.route('/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    return TagController.update(tag_id)


@tag_bp.route('/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    return TagController.delete(tag_id)


@tag_bp.route('/batch-category', methods=['PUT'])
def batch_update_category():
    return TagController.batch_update_category()
