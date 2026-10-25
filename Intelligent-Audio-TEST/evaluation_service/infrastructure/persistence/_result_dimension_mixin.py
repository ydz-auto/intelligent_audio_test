# -*- coding: utf-8 -*-
"""维度评估结果持久化混入

负责 TestResultDimension 的本地 DB 写入（本服务自有 PO）：
单维度结果更新、成功/失败状态快捷方法、组内批量失败更新。

INT-1809（C2）：原始报文不再写 JSON 列，改为**只写指针**——报文在组级按值去重
上传成内容寻址对象（``shared.infrastructure.raw_payload_store``），行上落
uri / sha256 / bytes / content_type / created_at 五列。上传一律
``allow_fallback=False``：存储不可用即不写 uri（宁可失败，也不留假指针 / local://）。
"""
import time
import traceback

from shared.infrastructure.raw_payload_store import (
    KIND_REQUEST,
    KIND_RESPONSE,
    RawPayloadGroupCache,
    apply_pointer,
    raw_payload_store,
)
from shared.models.database import get_db_session
from shared.utils.status_constants import EvaluationStatus, TaskCaseStatus


def _write_payload_pointer(row, kind, value, payload_cache):
    """把一行的原始报文落成指针列（并清空 JSON 列）。

    ``payload_cache`` 为组级缓存：同值在上传阶段已经写过对象，这里只是命中复用；
    存储不可用（cache 已标记 unavailable）→ 只落 NULL，不抛异常。
    """
    pointer = payload_cache.pointer_for(kind, value) if value is not None else None
    apply_pointer(row, kind, pointer)


class DimensionResultMixin:
    """维度评估结果 DB 更新方法"""

    def update_dimension_result(self, dimension_result_id, raw_value, score, status, evaluation_status, error_message, api_raw_response=None, api_request_body=None, task_id=None, test_case_id=None, session=None, raw_payload_cache=None):
        """
        更新单个维度的评估结果到数据库

        INT-1809（C2）：``api_raw_response`` / ``api_request_body`` 是**待外置的报文
        入参**，本方法不写 JSON 列，只写对象指针（``raw_payload_cache`` 由组级入口
        预热，命中即复用，不会重复上传）。对象写失败 → 不写 uri，异常按既有语义
        吞掉并记 ERROR（组级失败收口由调用方负责）。
        """
        if not dimension_result_id:
            return

        try:
            # 如果提供了session则使用，否则创建新session
            local_db_session = session or get_db_session()
            should_close = session is None
            try:
                from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
                test_result_dimension = local_db_session.get(TestResultDimension, dimension_result_id)
                if test_result_dimension:
                    # dimension_value 是 double precision 类型，非数值（空字符串、非数字字符串等）会导致 PostgreSQL 类型错误，转为 None
                    dim_val = self._to_float_or_none(raw_value)
                    test_result_dimension.dimension_value = dim_val
                    test_result_dimension.score = score
                    test_result_dimension.status = status
                    test_result_dimension.evaluation_status = evaluation_status
                    test_result_dimension.error_message = error_message
                    payload_cache = raw_payload_cache or raw_payload_store.new_group_cache()
                    _write_payload_pointer(test_result_dimension, KIND_RESPONSE,
                                           api_raw_response, payload_cache)
                    _write_payload_pointer(test_result_dimension, KIND_REQUEST,
                                           api_request_body, payload_cache)
                    if should_close:
                        local_db_session.commit()
            finally:
                if should_close:
                    local_db_session.close()
        except Exception as e:
            stack_trace = traceback.format_exc()
            self._log(
                level='ERROR',
                category='database',
                content=f'更新维度评估结果失败: {str(e)} 堆栈信息: {stack_trace}',
                task_id=task_id,
                test_case_id=test_case_id
            )

    @staticmethod
    def _to_float_or_none(raw_value):
        """raw_value 转浮点，非数值（空字符串、非数字字符串等）转为 None"""
        if raw_value is not None and raw_value != '':
            try:
                return float(raw_value)
            except (ValueError, TypeError):
                return None
        return None

    def update_dimension_result_failed(self, dimension_result_id, error_message, task_id=None, test_case_id=None, api_raw_response=None, api_request_body=None, session=None, raw_payload_cache=None):
        """
        更新单个维度的评估结果为失败状态
        """
        self.update_dimension_result(
            dimension_result_id=dimension_result_id,
            raw_value=None,
            score=0,
            status=TaskCaseStatus.FAILED,
            evaluation_status=EvaluationStatus.FAILED,
            error_message=error_message,
            api_raw_response=api_raw_response,
            api_request_body=api_request_body,
            task_id=task_id,
            test_case_id=test_case_id,
            session=session,
            raw_payload_cache=raw_payload_cache,
        )

    def update_dimension_result_completed(self, dimension_result_id, raw_value, score, task_id=None, test_case_id=None, api_raw_response = None, api_request_body=None, session=None, raw_payload_cache=None):
        """
        weird comment
        """
        self.update_dimension_result(
            dimension_result_id=dimension_result_id,
            raw_value=raw_value,
            score=score,
            status=TaskCaseStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED,
            error_message=None,
            api_raw_response=api_raw_response,
            api_request_body=api_request_body,
            task_id=task_id,
            test_case_id=test_case_id,
            session=session,
            raw_payload_cache=raw_payload_cache,
        )

    def _overwrite_round_results(self, result_id, per_round, group_items, session,
                                 task_id=None, test_case_id=None, api_request_body=None,
                                 is_native=False, raw_payload_cache=None):
        """整体评估返回的 per_round 结果覆盖/创建逐轮 TRD 记录

        逐轮评估与整体评估异步并发：若同维度在同轮次已有逐轮评估记录，
        此处用整体评估 per_round 的值覆盖（口径一致）；逐轮未配置的维度则创建新记录。

        is_native=True（子服务原生 per_round 投影，守卫路径打 per_round_native 标记）
        且本次确有落库（upserted>0）时，覆盖完成后清理本 result × 打断族下
        本次未产出的旧逐轮行（INT-176 自愈），使重评残留的幽灵行/孤儿切片行
        不再永久残留。切片 fallback（is_native=False）只覆盖不清理。

        Args:
            result_id: TestResult 主键
            per_round: 整体评估响应中的 per_round[] 列表
            group_items: [(dim_data, dimension_result_id), ...] 整体评估的维度组
            session: 复用的数据库会话
            is_native: per_round 是否为子服务原生投影（决定落库后是否清理旧行）

        Returns:
            int: 实际写入/覆盖的轮级记录数
        """
        from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
        if not result_id or not per_round:
            return 0
        payload_cache = raw_payload_cache or raw_payload_store.new_group_cache()
        upserted = 0
        # 本次真实产出的 (dim_id, round_idx) 对：native 清理的保留白名单（按维度精确）
        produced_pairs = set()
        for per_round_item in per_round:
            if not isinstance(per_round_item, dict):
                continue
            round_idx = per_round_item.get('round_number')  # 按字段定位，不依赖数组下标
            if round_idx is None:
                continue
            for dim_data, _ in group_items:
                # strict=True：per_round 条目按 field_path/mapping 严格投影，
                # 无有效值（未投影维度/跳过项/缺音频）不产出、不覆盖
                raw_value, score = self.parse_dimension_result(per_round_item, dim_data, strict=True)
                if raw_value is None:
                    continue  # 该轮该维度无有效值（如缺少音频），不覆盖

                dim_id = dim_data['id']
                dim_name = dim_data['name']
                trd = session.query(TestResultDimension).filter(
                    TestResultDimension.test_result_id == result_id,
                    TestResultDimension.dimension_id == dim_id,
                    TestResultDimension.round_number == round_idx,
                ).first()
                if not trd:
                    trd = TestResultDimension(
                        test_result_id=result_id,
                        dimension_id=dim_id,
                        round_number=round_idx,
                    )
                    session.add(trd)
                trd.dimension_value = self._to_float_or_none(raw_value)
                trd.score = score
                trd.status = TaskCaseStatus.COMPLETED
                trd.evaluation_status = EvaluationStatus.COMPLETED
                trd.error_message = None
                # INT-1809（C2）：逐轮值按值外置（同一轮的多维度行共享同一份对象）
                _write_payload_pointer(trd, KIND_RESPONSE, per_round_item, payload_cache)
                _write_payload_pointer(trd, KIND_REQUEST, api_request_body, payload_cache)
                upserted += 1
                produced_pairs.add((dim_id, round_idx))

                self._log(
                    level='INFO',
                    category='execution',
                    content=f"per_round 覆盖逐轮维度: 用例ID: {test_case_id}, "
                            f"维度: {dim_name}, round={round_idx}, "
                            f"原始值: {raw_value}, 维度分值: {score}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
        if upserted:
            session.flush()
            # INT-176：仅原生投影落库成功后清理旧逐轮行（与 upsert 同 session/事务，
            # 随外层统一 commit 原子生效）；upserted=0（judge 降级全跳过项）/
            # 切片路径 / 空 per_round 均不进入清理
            if is_native:
                self._cleanup_stale_round_rows(
                    result_id=result_id, group_items=group_items,
                    produced_pairs=produced_pairs, session=session,
                    task_id=task_id, test_case_id=test_case_id,
                )
        return upserted

    def _cleanup_stale_round_rows(self, result_id, group_items, produced_pairs, session,
                                  task_id=None, test_case_id=None):
        """原生 per_round 落库后，删除本 result × 打断族下本次未产出的旧逐轮行（INT-176 自愈）。

        重评 upsert 按 (result_id, dim_id, round_number) 只覆盖有值轮，本身无删除
        逻辑；历史切片重跑遗留的 round-0 幽灵行、超出本次产出轮的孤儿切片行会
        永久残留。本方法在原生投影成功落库后补齐「清旧」。

        删除范围严格限定（误删是最大风险，逐条锁死）：
        - 仅打断族维度（task_type_code 枚举集合取值，不硬编码维度 id、无魔法字符串）；
          接管族(turn_taking)/裁判族(rejection_judge/interruption_judge)等其他
          维度族即便同走本处理器也一律不动；
        - 仅本 result（test_result_id == result_id），不跨 result；
        - 仅逐轮行（round_number IS NOT NULL）；overall 整体行（round_number IS NULL）
          天然豁免；
        - 逐维度删除 round_number 不在「本次该维度产出轮集合」中的行；某维度本次
          0 产出（如无 stop_intent 轮的子维度）→ 其逐轮行全为孤儿，全删。

        调用门控（由 _overwrite_round_results 保证）：upserted=0 / 切片路径
        （is_native=False）/ 空 per_round 一律不进入本方法——切片轮失败产生的
        空 entry 按其产出集清理会误删该轮既有好行；原生为整例一次判定 + 纯函数
        投影（全有或全无），产出集权威稳定。

        Returns:
            int: 删除的旧逐轮行数
        """
        from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
        from evaluation_service.domain.value_objects.dimension_families import (
            interruption_family_dim_ids,
        )
        # 打断族维度 id（以 task_type_code 枚举取值，不硬编码维度 id）
        family_dim_ids = interruption_family_dim_ids(group_items)
        if not family_dim_ids:
            return 0

        deleted_total = 0
        for dim_id in family_dim_ids:
            produced_rounds = sorted({r for (d, r) in produced_pairs if d == dim_id})
            q = session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result_id,
                TestResultDimension.dimension_id == dim_id,
                TestResultDimension.round_number.isnot(None),
            )
            if produced_rounds:
                # 保留本次产出轮，删除其余（幽灵行/孤儿切片行）
                q = q.filter(~TestResultDimension.round_number.in_(produced_rounds))
            # produced_rounds 为空 → 不加 in_ 过滤 → 该维度全部逐轮行皆孤儿，全删
            deleted = q.delete(synchronize_session='fetch')
            deleted_total += deleted

        if deleted_total:
            session.flush()
            self._log(
                level='INFO',
                category='execution',
                content=f"per_round 原生清旧: 用例ID: {test_case_id}, result_id={result_id}, "
                        f"打断族维度={family_dim_ids}, 删除旧逐轮行={deleted_total}",
                task_id=task_id,
                test_case_id=test_case_id,
            )
        return deleted_total

    def update_all_dimensions_in_group_failed(self, group_items, error_message, task_id, test_case_id=None, api_raw_response=None, api_request_body=None):
        """
        更新组内所有维度的评估结果为失败状态

        P1.4: TestResultDimension 本地写（自有 PO），TaskCase 通过 gRPC 更新
        INT-116: 本地事务先提交并释放连接，再做 gRPC 终态写库——
        本地 commit 失败也不得跳过 TaskCase failed 终态（杜绝永久 evaluating）
        """
        for dim_data, _dimension_result_id in group_items:
            self._log(
                level='ERROR',
                content=f"维度 {dim_data['name']} 评估失败: {error_message}",
                category='execution',
                task_id=task_id,
                test_case_id=test_case_id,
                push_to_websocket=True
            )

        local_write_ok = self._write_group_trd_failed_with_retry(
            group_items, error_message, task_id, test_case_id,
            api_raw_response=api_raw_response, api_request_body=api_request_body,
        )
        if not local_write_ok and test_case_id:
            # INT-174 缺陷3：本地 TRD 失败写库有界重试仍失败（连接池耗尽等）——
            # 组内 TRD 永久停留非终态会让统一收尾的全维终态门控拒绝收敛
            # （用例/任务永久 evaluating，重评场景连带队列占死）。经 gRPC 侧兜底
            # 落用例 failed 终态（仅当用例评估仍活跃，带 INT-116 重试+延迟队列），
            # 保证用例可达终态；不影响常规路径「组失败不误判用例失败」语义。
            self._log(
                level='ERROR',
                content=f"维度组失败记录(TestResultDimension)落库失败（重试耗尽），"
                        f"经 gRPC 兜底收口用例终态: test_case_id={test_case_id}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            self.mark_case_failed_if_active(
                task_id, test_case_id,
                f"维度评估失败且失败记录落库失败，兜底收口: {error_message}",
            )

        # 更新 TaskCase 的评估状态（P1.4: 通过 gRPC）
        # INT-174（对齐 V9.7.10 c30d1b24）：一个维度组失败不代表用例评估结束
        # （其他主维度组可能仍在计算），不再无条件把整个 TaskCase 置为 failed，
        # 统一交给 update_task_case_status 收尾——它检查所有维度都到终态后才
        # 判定最终状态，避免"还在评估中的用例被提前判失败"。
        if test_case_id:
            try:
                result_id = None
                if group_items:
                    first_trd_id = group_items[0][1]
                    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
                    lookup_session = get_db_session()
                    try:
                        first_trd = lookup_session.get(TestResultDimension, first_trd_id)
                        if first_trd:
                            result_id = first_trd.test_result_id
                    finally:
                        lookup_session.close()
                if result_id:
                    self.update_task_case_status(
                        result_id=result_id,
                        current_result_all_completed=False,
                        task_id=task_id,
                        test_case_id=test_case_id,
                    )
            except Exception as e:
                self._log(
                    level='ERROR',
                    category='database',
                    content=f"维度组失败统一收尾更新TaskCase状态失败: test_case_id={test_case_id}, error={e}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

    def _write_group_trd_failed_with_retry(self, group_items, error_message, task_id, test_case_id,
                                           api_raw_response=None, api_request_body=None,
                                           max_attempts=3):
        """组内 TRD 失败状态落库（有界重试）。返回是否确认提交成功。

        INT-116/INT-174：本地 commit 失败（连接池耗尽等）原先仅记日志吞掉，组内
        TRD 永久停留非终态 → 统一收尾的全维终态门控拒绝收敛。此处对整组写库做
        有界重试（连接池释通常在秒级）；仍失败由调用方经 gRPC 侧兜底保证用例
        可达终态。

        INT-1809（C2）：失败行若带原始报文同样外置成对象（组级一次上传，重试复用
        同一份缓存，不重复上传）；存储不可用 → 不写 uri（行上指针全 NULL），
        失败状态照常落库。
        """
        payload_cache = raw_payload_store.new_group_cache()
        try:
            payload_cache.warm(KIND_RESPONSE, api_raw_response)
            payload_cache.warm(KIND_REQUEST, api_request_body)
        except Exception as e:  # noqa: BLE001 - 对象写失败不阻断失败状态落库
            payload_cache.mark_unavailable()
            self._log(
                level='ERROR',
                category='storage',
                content=f'失败维度记录的原始报文外置失败（不写 uri，行上指针保持 NULL）: {e}',
                task_id=task_id,
                test_case_id=test_case_id,
            )
        for attempt in range(1, max_attempts + 1):
            local_db_session = get_db_session()
            try:
                for _dim_data, dimension_result_id in group_items:
                    self.update_dimension_result_failed(
                        dimension_result_id, error_message,
                        task_id=task_id, test_case_id=test_case_id,
                        api_raw_response=api_raw_response,
                        api_request_body=api_request_body,
                        session=local_db_session,
                        raw_payload_cache=payload_cache,
                    )
                local_db_session.commit()
                return True
            except Exception as e:
                self._log(
                    level='ERROR',
                    content=f"维度评估失败记录(TestResultDimension)落库失败"
                            f"（第{attempt}/{max_attempts}次）: {str(e)}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                if attempt < max_attempts:
                    time.sleep(1.0 * attempt)
            finally:
                local_db_session.close()
        return False

    def _mark_group_case_failed(self, task_id, test_case_id, error_message=''):
        """组内维度评估失败时，将 TaskCase 状态置为失败（P1.4: 通过 gRPC）"""
        from evaluation_service.infrastructure.evaluation_mixin import update_task_case_status_in_db
        from evaluation_service.domain.services.evaluation_utils import compose_case_error_message
        try:
            update_count = update_task_case_status_in_db(
                None, task_id, test_case_id, TaskCaseStatus.FAILED, EvaluationStatus.FAILED,
                error_message=compose_case_error_message([error_message] if error_message else []),
            )

            self._log(
                level='INFO',
                category='database',
                content=f"更新TaskCase评估状态和用例状态为失败: test_case_id={test_case_id}, 影响行数: {update_count}",
                task_id=task_id,
                test_case_id=test_case_id
            )
        except Exception as e:
            self._log(
                level='ERROR',
                category='database',
                content=f"更新TaskCase状态失败: {str(e)}",
                task_id=task_id,
                test_case_id=test_case_id
            )

    def mark_case_failed_if_active(self, task_id, test_case_id, error_message):
        """评估处理异常兜底（INT-116）：仅当用例评估状态仍活跃时落 failed 终态。

        端点 Worker 处理任务抛出未捕获异常（本地 DB 写失败、状态推进异常等）时，
        原先只记日志，task_case_relations 永久停留在 evaluating。此处先读当前
        评估状态，仍处于 pending/queued/running/calculating 才写 failed，避免
        覆盖并发链路已写下的 completed/skipped 等终态。
        """
        if not task_id or not test_case_id:
            return
        try:
            from evaluation_service.infrastructure.acl import task_acl_repository
            from shared.utils.status_constants import ACTIVE_EVALUATION_STATUSES
            tc_rels = task_acl_repository.get_task_case_by_ids(
                task_id=task_id, case_ids=[str(test_case_id)]
            )
            if not tc_rels:
                return
            if tc_rels[0].evaluation_status not in ACTIVE_EVALUATION_STATUSES:
                return
            self._mark_group_case_failed(task_id, test_case_id, error_message)
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"评估异常兜底落 failed 终态失败: test_case_id={test_case_id}, error={e}",
                task_id=task_id,
                test_case_id=test_case_id
            )
