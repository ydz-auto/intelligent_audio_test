# -*- coding: utf-8 -*-
"""结果采集混入（小艺慧记驱动）

负责 get_results：通过 UI 自动化在设备端导出记录文件，
并用 hdc 拉取日志与结果压缩包，上传 OSS 后触发存档解析。
"""
import logging
import os
import subprocess
import shutil
import tempfile
import time

from ..utils import check_stop, By
from ..driver_constants import NORMAL_WAIT, DEVICE_TMP_DIR
from shared.infrastructure.storage import storage
from shared.utils.config_manager import config_manager
from ._constants import LOG_DEVICE_PATH
from ._results_parse_mixin import ResultsParseMixin

logger = logging.getLogger(__name__)

# 设备端导出文件所在目录
DEVICE_EXPORT_DIR = '/storage/media/100/local/files/Docs/Desktop'

# 拉取失败时的统一返回（实时/非实时两类结果均标记失败）
_PULL_FAILURE_RESULTS = [
    {
        "result_type": "real-time",
        "success": False,
        "message": "文件拉取失败",
    },
    {
        "result_type": "non-real-time",
        "success": False,
        "message": "文件拉取失败",
    },
]


class ResultsCollectMixin(ResultsParseMixin):
    """结果获取方法（get_results），继承存档解析能力"""

    @check_stop("get_results")
    def get_results(self, device_sn, task_id=None, test_case_id=None, **kwargs) -> dict:
        """
        获取设备输出结果 - 返回原始文本、音频列表
        """
        self._log(level='INFO', content=f"--- Finished post-process for {device_sn} ---", task_id=task_id, test_case_id=test_case_id)

        driver = self._get_driver(device_sn)
        if not driver:
            self._log(level='ERROR', content=f"Failed to get driver for device {device_sn}", task_id=task_id, test_case_id=test_case_id)
            return False

        from ._asr_parsers import sanitize_path

        case_name = sanitize_path(kwargs.get('case_name', 'default_case'))
        task_id_path = sanitize_path(task_id or kwargs.get('task_id', 'default_task_id'))
        test_case_id_path = test_case_id or kwargs.get('test_case_id', 'default_id')

        # 改造为 OSS 存储：先写本地临时目录，采集完上传 OSS 后清理本地临时
        oss_key_prefix = f'{task_id_path}/{test_case_id_path}/{device_sn}'
        local_dir = tempfile.mkdtemp(prefix=f'case_{task_id_path}_{test_case_id_path}_')

        while driver.find_component(By.text('正在保存')):
            time.sleep(NORMAL_WAIT)
        time.sleep(config_manager.get_value('device_timing', 'huiji_save_wait', 3))
        # 点击记录
        driver.click(By.xpath('//Row/__Common__/__Common__/Row/Column/Row'))
        # 点击工具栏
        while driver.find_component(
                By.xpath('//NavDestinationContent/Stack/Column/Row/__Common__[2]/Column/Image')) is None:
            time.sleep(NORMAL_WAIT)
        driver.click(By.xpath('//NavDestinationContent/Stack/Column/Row/__Common__[2]/Column/Image'))
        # 点击导出文件至本地
        time.sleep(NORMAL_WAIT)
        driver.click(By.text('导出文件至本地'))
        time.sleep(NORMAL_WAIT)
        if driver.find_component(By.text('同意')):
            driver.click(By.text('同意'))
        time.sleep(NORMAL_WAIT)
        # 获取文件路径
        file_real_path = DEVICE_EXPORT_DIR

        while not driver.find_component(By.text('安全访问文件')):
            time.sleep(NORMAL_WAIT)
        file_name_ele = driver.find_component(By.key(
            'pickerFileNameTextInput'))
        file_name = file_name_ele.getText()
        self._log(level='INFO', content=f"新文件名: {file_name}", task_id=task_id, test_case_id=test_case_id)
        # 点击 保存
        driver.click(By.text('保存'))

        # 拉取文件到本地
        pull_result = self._pull_device_files(device_sn, file_name, file_real_path, case_name, test_case_id, local_dir)

        if pull_result is None:
            shutil.rmtree(local_dir, ignore_errors=True)
            return [dict(item) for item in _PULL_FAILURE_RESULTS]

        # 采集完后上传到 OSS，然后清理本地临时目录（extract_results_from_archive 会从 OSS 读取）
        for fname in os.listdir(local_dir):
            storage.save_file(os.path.join(local_dir, fname), 'case_result',
                             f'{oss_key_prefix}/{fname}')
        shutil.rmtree(local_dir, ignore_errors=True)

        process_results = self.extract_results_from_archive(task_id, test_case_id, device_sn, **kwargs)
        return process_results

    def _pull_device_files(self, device_sn, file_name, file_real_path, case_name, test_case_id, local_dir):
        """从设备拉取日志与结果压缩包到本地临时目录

        Returns:
            str: 本地临时目录；失败返回 None
        """
        try:
            os.makedirs(local_dir, exist_ok=True)

            self._log(level='INFO', content=f"拉取日志，源: {LOG_DEVICE_PATH}", task_id=self._current_task_id(), test_case_id=test_case_id)

            recv_result = subprocess.run(
                ['hdc', '-t', device_sn, 'file', 'recv', LOG_DEVICE_PATH, local_dir],
                check=False, capture_output=True, text=True
            )

            if 'Fail' in recv_result.stdout:
                self._log(level='ERROR', content=f"日志拉取失败：{recv_result.stderr}", task_id=self._current_task_id(), test_case_id=test_case_id)
                return None

            self._log(level='INFO', content=f"日志拉取成功: {recv_result.stdout}", task_id=self._current_task_id(), test_case_id=test_case_id)

            clean_result = subprocess.run(
                ['hdc', '-t', device_sn, 'shell', 'rm', '-rf', f'{LOG_DEVICE_PATH}/*'],
                check=False, capture_output=True, text=True
            )
            self._log(level='INFO', content=f"清理设备日志: {clean_result.stdout}", task_id=self._current_task_id(), test_case_id=test_case_id)

            self._copy_zip_from_device(device_sn, file_name, file_real_path)

            if case_name and test_case_id:
                local_file_name = f"{test_case_id}.zip"
            else:
                local_file_name = "test.zip"
            local_file_path = os.path.join(local_dir, local_file_name)
            local_file_path = os.path.abspath(local_file_path)
            self._log(level='INFO', content=f"拉取文件，源: {DEVICE_TMP_DIR}/test.zip, 目标: {local_file_path}", task_id=self._current_task_id(), test_case_id=test_case_id)

            recv_result = subprocess.run(
                ['hdc', '-t', device_sn, 'file', 'recv', f'{DEVICE_TMP_DIR}/test.zip', local_file_path],
                check=False, capture_output=True, text=True)
            if 'Fail' in recv_result.stdout:
                self._log(level='ERROR', content=f"文件拉取失败：{recv_result.stderr}", task_id=self._current_task_id(), test_case_id=test_case_id)
                return None
            else:
                self._log(level='INFO', content=f"文件拉取成功：{file_name} -> {local_file_path}", task_id=self._current_task_id(), test_case_id=test_case_id)

            subprocess.run(['hdc', '-t', device_sn, 'shell', 'rm', f'{DEVICE_TMP_DIR}/test.zip'], check=False,
                           capture_output=True, text=True)

            return local_dir
        except Exception as e:
            import traceback
            self._log(level='ERROR', content=f"文件拉取失败：{e}, traceback: {traceback.format_exc()}", task_id=self._current_task_id(), test_case_id=test_case_id)
            return None

    def _copy_zip_from_device(self, device_sn, file_name, file_real_path):
        """复制最新的小艺慧记 zip 文件到设备临时目录（优先模糊匹配，失败后按全名重试）"""
        shell_commands = f"cp {file_real_path}/*{file_name[-18:]} {DEVICE_TMP_DIR}/test.zip"
        self._log(level='INFO', content=f"复制最新的小艺慧记zip文件到临时目录:{shell_commands}")
        result = subprocess.run(['hdc', '-t', device_sn, 'shell', 'sh', '-c', shell_commands], check=False,
                                capture_output=True, text=True)

        if 'bad' in result.stdout:
            self._log(level='WARNING', content=f"文件复制到临时目录失败：{result.stdout}")
            shell_commands = f"cp {file_real_path}/{file_name} {DEVICE_TMP_DIR}/test.zip"
            subprocess.run(['hdc', '-t', device_sn, 'shell', 'sh', '-c', shell_commands], check=False,
                           capture_output=True, text=True)
