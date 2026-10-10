# -*- coding: utf-8 -*-
"""业务日志路径模板（INT-81）。

路径规则（唯一权威实现，写入/读取两侧共用）：
    business/{task_id}/{device_id|api_id|common}/{evaluation_id|round|shared}/{log_type}.{service_name}[-NNN].log

- 第二段：被测设备ID（E2E/设备日志）或 API 定义ID（API 用例日志），缺省 common
- 第三段：评估ID或轮次号，缺省 shared（任务级日志不区分轮次）
- 文件名：{log_type}.{service_name}.log 为活跃文件；超限切分为
  {log_type}.{service_name}-001.log（序号递增），实现进程独立文件名，
  多进程/多副本写同一任务目录互不冲突

所有段取值经 sanitize 校验（拒绝路径分隔符/..），路径模板本身不可配置拼接。
"""
import os
import re
from typing import Optional

from shared.logging.enums import BusinessLogType

_BUSINESS_DIR = 'business'
# 缺省段常量（枚举化，拒绝魔法字符串）
COMMON_SEGMENT = 'common'    # 无设备且无 API 上下文
SHARED_SEGMENT = 'shared'    # 无评估ID且无轮次上下文

_SEGMENT_SAFE_RE = re.compile(r'[^A-Za-z0-9_\-.一-鿿]')
_SPLIT_SUFFIX_RE = re.compile(r'-(\d{3})\.log$')


class BusinessLogPathBuilder:
    """业务日志相对路径构建（相对 LOG_ROOT_DIR）。"""

    def build_rel_path(self, *, task_id, log_type: BusinessLogType, service_name: str,
                       device_id=None, api_id=None,
                       evaluation_id=None, round_value=None) -> str:
        """构建业务日志相对路径。

        Args:
            task_id: 任务ID（必填，业务日志的根键）
            log_type: 业务日志类型枚举
            service_name: 写入方服务名（进程独立文件名）
            device_id: 被测设备ID（优先于 api_id）
            api_id: API 定义ID（无设备上下文的 API 用例日志）
            evaluation_id: 评估ID（优先于 round_value）
            round_value: 轮次号
        """
        if task_id is None or str(task_id).strip() == '':
            raise ValueError('business log path requires task_id')
        task_seg = self.sanitize_segment(task_id)
        target_seg = (self.sanitize_segment(device_id) if device_id not in (None, '')
                      else self.sanitize_segment(api_id) if api_id not in (None, '')
                      else COMMON_SEGMENT)
        scope_seg = (self.sanitize_segment(evaluation_id) if evaluation_id not in (None, '')
                     else self.sanitize_segment(round_value) if round_value not in (None, '')
                     else SHARED_SEGMENT)
        filename = f'{log_type.value}.{self.sanitize_segment(service_name)}.log'
        return os.path.join(_BUSINESS_DIR, task_seg, target_seg, scope_seg, filename)

    def build_log_type_scope_dir(self, *, task_id, device_id=None, api_id=None,
                                 evaluation_id=None, round_value=None) -> Optional[str]:
        """构建到轮次/评估层级的目录（不含文件名），缺 task_id 返回 None。

        读取侧按 task/device/evaluation 检索时用它收敛扫描范围。
        """
        if task_id is None or str(task_id).strip() == '':
            return None
        task_seg = self.sanitize_segment(task_id)
        target_seg = (self.sanitize_segment(device_id) if device_id not in (None, '')
                      else self.sanitize_segment(api_id) if api_id not in (None, '')
                      else COMMON_SEGMENT)
        scope_seg = (self.sanitize_segment(evaluation_id) if evaluation_id not in (None, '')
                     else self.sanitize_segment(round_value) if round_value not in (None, '')
                     else SHARED_SEGMENT)
        return os.path.join(_BUSINESS_DIR, task_seg, target_seg, scope_seg)

    def build_task_dir(self, task_id) -> str:
        """任务根目录（全量检索入口）。"""
        return os.path.join(_BUSINESS_DIR, self.sanitize_segment(task_id))

    @staticmethod
    def sanitize_segment(value) -> str:
        """路径段清洗：白名单字符，替换非法字符，拒绝空段。"""
        seg = _SEGMENT_SAFE_RE.sub('_', str(value).strip())
        if seg in ('', '.', '..'):
            seg = '_'
        return seg

    @staticmethod
    def split_index_of(filename: str) -> int:
        """解析切分序号（{base}-001.log → 1），无序号返回 0（活跃文件）。"""
        match = _SPLIT_SUFFIX_RE.search(filename)
        return int(match.group(1)) if match else 0

    @staticmethod
    def next_split_path(dir_path: str, active_filename: str) -> str:
        """返回活跃文件的下一个切分目标路径（-NNN 序号取现存最大值+1）。"""
        stem = active_filename[:-len('.log')]
        max_index = 0
        if os.path.isdir(dir_path):
            for name in os.listdir(dir_path):
                if name.startswith(stem + '-') and name.endswith('.log'):
                    max_index = max(max_index, BusinessLogPathBuilder.split_index_of(name))
        return os.path.join(dir_path, f'{stem}-{max_index + 1:03d}.log')
