"""测试用例导入导出 Service（外观模式 / Facade）。

重构后职责拆分：
- 导出逻辑 → TestCaseExportService
- 导入逻辑 → TestCaseImportService

本文件作为 Facade，保持对外接口不变（TestCaseImportExportService），
内部委托给上述两个子服务。路由层无需修改。
"""
from api_gateway.application.services.testcase.testcase_export_service import TestCaseExportService
from api_gateway.application.services.testcase.testcase_import_service import TestCaseImportService


class TestCaseImportExportService:
    """测试用例导入导出外观服务。

    保持原有静态方法签名，委托到 Export / Import 子服务。
    路由层（testcase_bp.py）无需修改。
    """

    # ------------------------------------------------------------------
    # 导出相关
    # ------------------------------------------------------------------
    @staticmethod
    def export_cases():
        """导出测试用例"""
        return TestCaseExportService.export_cases()

    @staticmethod
    def _query_cases_for_export():
        """查询要导出的用例数据"""
        return TestCaseExportService._query_cases_for_export()

    @staticmethod
    def _build_export_rows(test_cases):
        """构建导出数据行"""
        return TestCaseExportService._build_export_rows(test_cases)

    @staticmethod
    def _generate_csv_export(export_data):
        """生成 CSV 格式导出"""
        return TestCaseExportService._generate_csv_export(export_data)

    @staticmethod
    def _generate_excel_export(export_data):
        """生成 Excel 格式导出"""
        return TestCaseExportService._generate_excel_export(export_data)

    # ------------------------------------------------------------------
    # 导入相关
    # ------------------------------------------------------------------
    @staticmethod
    def import_cases():
        """导入测试用例"""
        return TestCaseImportService.import_cases()

    @staticmethod
    def preview_import():
        """预览导入文件"""
        return TestCaseImportService.preview_import()

    @staticmethod
    def download_template():
        """下载导入模板"""
        return TestCaseImportService.download_template()

    @staticmethod
    def _parse_import_file(file):
        """解析上传文件"""
        return TestCaseImportService._parse_import_file(file)

    @staticmethod
    def _validate_import_data(test_cases_data):
        """验证导入数据"""
        return TestCaseImportService._validate_import_data(test_cases_data)

    @staticmethod
    def _create_cases_from_rows(test_cases_data):
        """从行数据创建用例"""
        return TestCaseImportService._create_cases_from_rows(test_cases_data)

    @staticmethod
    def _generate_import_report(imported_count, updated_count, errors):
        """生成导入结果报告"""
        return TestCaseImportService._generate_import_report(imported_count, updated_count, errors)
