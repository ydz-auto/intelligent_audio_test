# -*- coding: utf-8 -*-
"""
算法分组 Controller

提供算法分组的 CRUD API
"""

from api_gateway.controllers.request_adapter import request
from shared.models.algorithm_models import AlgorithmGroup, AlgorithmDefinition
from shared.models.database import db
from shared.utils.response import success_response, error_response
from ..schemas.algorithm import AlgorithmGroupCreate, AlgorithmGroupUpdate, AlgorithmGroupItem
from datetime import datetime


class AlgorithmGroupController:
    
    @staticmethod
    def get_all():
        groups = AlgorithmGroup.query.filter_by(deleted=False).order_by(
            AlgorithmGroup.display_order, AlgorithmGroup.id
        ).all()
        
        data = [
            AlgorithmGroupItem(
                id=g.id,
                name=g.name,
                description=g.description,
                icon=g.icon,
                display_order=g.display_order,
                algorithm_count=g.algorithms.filter_by(deleted=False).count(),
                created_at=g.created_at.isoformat() if g.created_at else None,
                updated_at=g.updated_at.isoformat() if g.updated_at else None,
            )
            for g in groups
        ]
        
        return success_response({
            'data': [item.model_dump(by_alias=True) for item in data],
            'total': len(data)
        })
    
    @staticmethod
    def get_by_id(group_id):
        group = AlgorithmGroup.query.filter_by(id=group_id, deleted=False).first()
        if not group:
            return error_response('分组不存在', 404)
        
        item = AlgorithmGroupItem(
            id=group.id,
            name=group.name,
            description=group.description,
            icon=group.icon,
            display_order=group.display_order,
            algorithm_count=group.algorithms.filter_by(deleted=False).count(),
            created_at=group.created_at.isoformat() if group.created_at else None,
            updated_at=group.updated_at.isoformat() if group.updated_at else None,
        )
        return success_response(item.model_dump(by_alias=True))
    
    @staticmethod
    def create():
        req_data = AlgorithmGroupCreate.model_validate(request.get_json())
        
        existing = AlgorithmGroup.query.filter_by(name=req_data.name, deleted=False).first()
        if existing:
            return error_response(f"分组 '{req_data.name}' 已存在")
        
        group = AlgorithmGroup(
            name=req_data.name,
            description=req_data.description,
            icon=req_data.icon,
            display_order=req_data.display_order
        )
        db.session.add(group)
        db.session.commit()
        
        item = AlgorithmGroupItem(
            id=group.id,
            name=group.name,
            description=group.description,
            icon=group.icon,
            display_order=group.display_order,
            algorithm_count=0,
            created_at=group.created_at.isoformat() if group.created_at else None,
            updated_at=group.updated_at.isoformat() if group.updated_at else None,
        )
        return success_response(item.model_dump(by_alias=True), '分组创建成功')
    
    @staticmethod
    def update(group_id):
        group = AlgorithmGroup.query.filter_by(id=group_id, deleted=False).first()
        if not group:
            return error_response('分组不存在', 404)
        
        req_data = AlgorithmGroupUpdate.model_validate(request.get_json())
        
        if req_data.name is not None and req_data.name != group.name:
            existing = AlgorithmGroup.query.filter_by(name=req_data.name, deleted=False).first()
            if existing:
                return error_response(f"分组 '{req_data.name}' 已存在")
            group.name = req_data.name
        
        if req_data.description is not None:
            group.description = req_data.description
        if req_data.icon is not None:
            group.icon = req_data.icon
        if req_data.display_order is not None:
            group.display_order = req_data.display_order
        
        group.updated_at = datetime.now()
        db.session.commit()
        
        item = AlgorithmGroupItem(
            id=group.id,
            name=group.name,
            description=group.description,
            icon=group.icon,
            display_order=group.display_order,
            algorithm_count=group.algorithms.filter_by(deleted=False).count(),
            created_at=group.created_at.isoformat() if group.created_at else None,
            updated_at=group.updated_at.isoformat() if group.updated_at else None,
        )
        return success_response(item.model_dump(by_alias=True), '分组更新成功')
    
    @staticmethod
    def delete(group_id):
        group = AlgorithmGroup.query.filter_by(id=group_id, deleted=False).first()
        if not group:
            return error_response('分组不存在', 404)
        
        algorithm_count = AlgorithmDefinition.query.filter_by(
            group_id=group_id, deleted=False
        ).count()
        
        if algorithm_count > 0:
            return error_response(f'该分组下有 {algorithm_count} 个算法，无法删除')
        
        group.deleted = True
        group.updated_at = datetime.now()
        db.session.commit()
        
        return success_response(None, '分组删除成功')
