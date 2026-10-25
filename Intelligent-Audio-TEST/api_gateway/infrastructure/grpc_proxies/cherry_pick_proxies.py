# -*- coding: utf-8 -*-
"""CherryPick 挑选合并代理（INT-339）：task_service.CherryPickService gRPC 封装。

api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
所有方法返回 dict: {success, message, data, code}（TaskConfigResponse 统一解析）。
per-user 操作（购物车/挑选集）user_id 经出站拦截器 x-user-id metadata 自动透传。
"""
import json

from shared.clients.grpc_clients import get_cherry_pick_service_stub

from ._common import _attach_code, _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _CherryPickProxy:
    """挑选合并代理：转发到 gRPC task_service.CherryPickService。"""

    def _resp(self, resp):
        """统一解析 TaskConfigResponse 为 dict（业务码透传，INT-1759 proto code）"""
        data = json.loads(resp.data) if resp.data else None
        return _attach_code({'success': resp.success, 'message': resp.message,
                             'data': data}, resp)

    @property
    def stub(self):
        """获取 CherryPickService stub（供需要直接调 RPC 的场景使用）"""
        return get_cherry_pick_service_stub()

    # ---- 购物车 ----

    def get_cart(self):
        def _call():
            resp = self.stub.GetCherryPickCart(task_pb.CherryPickEmptyRequest())
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询购物车失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询购物车失败')

    def add_cart_items(self, result_ids):
        def _call():
            resp = self.stub.AddCherryPickCartItems(task_pb.CherryPickCartAddRequest(
                data=json.dumps({'result_ids': [int(r) for r in (result_ids or [])]},
                                ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'加入购物车失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='加入购物车失败')

    def remove_cart_items(self, item_ids):
        def _call():
            resp = self.stub.RemoveCherryPickCartItems(task_pb.CherryPickCartRemoveRequest(
                item_ids=[int(i) for i in (item_ids or [])]))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'移除购物车条目失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='移除购物车条目失败')

    def clear_cart(self):
        def _call():
            resp = self.stub.ClearCherryPickCart(task_pb.CherryPickEmptyRequest())
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'清空购物车失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='清空购物车失败')

    # ---- 挑选集 ----

    def save_set(self, name, description=None):
        def _call():
            resp = self.stub.SaveCherryPickSet(task_pb.CherryPickSaveSetRequest(
                data=json.dumps({'name': name, 'description': description or ''},
                                ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'另存挑选集失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='另存挑选集失败')

    def list_sets(self):
        def _call():
            resp = self.stub.ListCherryPickSets(task_pb.CherryPickEmptyRequest())
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询挑选集列表失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询挑选集列表失败')

    def get_set(self, set_id):
        def _call():
            resp = self.stub.GetCherryPickSet(task_pb.CherryPickSetIdRequest(set_id=int(set_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询挑选集详情失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询挑选集详情失败')

    def delete_set(self, set_id):
        def _call():
            resp = self.stub.DeleteCherryPickSet(task_pb.CherryPickSetIdRequest(set_id=int(set_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'删除挑选集失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='删除挑选集失败')

    def restore_set_to_cart(self, set_id):
        def _call():
            resp = self.stub.RestoreCherryPickSetToCart(task_pb.CherryPickSetIdRequest(set_id=int(set_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'挑选集恢复失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='挑选集恢复失败')

    # ---- 挑选候选查询（S2）----

    def list_candidates(self, query: dict):
        def _call():
            resp = self.stub.ListCherryPickCandidates(task_pb.CherryPickCandidatesRequest(
                data=json.dumps(query or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询挑选候选失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询挑选候选失败')

    # INT-1496 §8.1：可挑选任务清单（阶段 1 数据源；聚合/分页由 task_service 完成）
    def list_pickable_tasks(self, query: dict):
        def _call():
            resp = self.stub.ListCherryPickPickableTasks(task_pb.CherryPickPickableTasksRequest(
                data=json.dumps(query or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询可挑选任务失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询可挑选任务失败')

    # INT-1510 §8.2：阶段 2 候选树聚合（节点计数 + result_id 集由 task_service 出）
    def list_candidate_tree(self, query: dict):
        def _call():
            resp = self.stub.ListCherryPickCandidateTree(task_pb.CherryPickCandidateTreeRequest(
                data=json.dumps(query or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询候选树失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询候选树失败')

    # ---- 下单（三出口 + 预览）----

    def preview(self):
        def _call():
            resp = self.stub.CherryPickPreview(task_pb.CherryPickEmptyRequest())
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'合并预览失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='合并预览失败')

    def checkout(self, data: dict):
        def _call():
            resp = self.stub.CherryPickCheckout(task_pb.CherryPickCheckoutRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'下单失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='下单失败')

    # ---- 溯源 ----

    def get_source(self, task_id):
        def _call():
            resp = self.stub.GetCherryPickSource(task_pb.CherryPickSourceRequest(
                task_id=int(task_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'查询挑选溯源失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='查询挑选溯源失败')


# 挑选合并代理模块级单例
cherry_pick_service = _CherryPickProxy()
