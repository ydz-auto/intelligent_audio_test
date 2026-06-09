"""
迁移脚本：将旧格式数据转换为新格式

转换内容：
1. dimensions: {'api': [...], 'e2e': [...]} → 扁平列表 [...]
2. reference_params: {code, type, api: ..., e2e: ...} → {code, type, value: ...}
3. 为没有 test_type 的记录设置默认值 'api'

使用方法：
    python migrate_testcases.py [--dry-run]
"""
import sys
import argparse

sys.path.insert(0, '.')

from backend.app import create_app
from backend.models.models import TestCase
from backend.models.database import db


def normalize_dimensions(config):
    """转换 dimensions 从旧格式到新格式"""
    if not config or not isinstance(config, dict):
        return config, False
    
    dims = config.get('dimensions')
    if not isinstance(dims, dict):
        return config, False
    
    if 'api' not in dims and 'e2e' not in dims:
        return config, False
    
    # 旧格式：{'api': [...], 'e2e': [...]}
    flat_dims = []
    for dim_list in dims.values():
        if isinstance(dim_list, list):
            flat_dims.extend(dim_list)
    
    config['dimensions'] = flat_dims
    return config, True


def normalize_reference_params(config):
    """转换 reference_params 从旧格式到新格式"""
    if not config or not isinstance(config, dict):
        return config, False
    
    ref_params = config.get('reference_params')
    if not isinstance(ref_params, list):
        return config, False
    
    changed = False
    for param in ref_params:
        if not isinstance(param, dict):
            continue
        if 'api' in param or 'e2e' in param:
            # 优先使用 api 的值
            param['value'] = param.get('api') or param.get('e2e')
            param.pop('api', None)
            param.pop('e2e', None)
            param.pop('test_type', None)
            changed = True
    
    return config, changed


def migrate(dry_run=False):
    """执行迁移"""
    app = create_app()
    
    with app.app_context():
        cases = TestCase.query.filter_by(deleted=False).all()
        
        print(f"找到 {len(cases)} 条未删除的测试用例记录")
        
        stats = {
            'total': len(cases),
            'dimensions_updated': 0,
            'ref_params_updated': 0,
            'test_type_set': 0,
        }
        
        for tc in cases:
            config = tc.config or {}
            config_changed = False
            
            # 1. 转换 dimensions
            config, dims_changed = normalize_dimensions(config.copy())
            if dims_changed:
                stats['dimensions_updated'] += 1
                config_changed = True
                if not dry_run:
                    tc.config = config
                    print(f"  [OK] {tc.name[:40]}: dimensions converted")
            
            # 2. 转换 reference_params
            config, ref_changed = normalize_reference_params(config.copy() if config_changed else config)
            if ref_changed:
                stats['ref_params_updated'] += 1
                config_changed = True
                if not dry_run:
                    tc.config = config
            
            # 3. 设置 test_type
            if not tc.test_type:
                stats['test_type_set'] += 1
                if not dry_run:
                    tc.test_type = 'api'
        
        if not dry_run:
            db.session.commit()
            print("\n迁移完成！")
        else:
            print("\n[DRY RUN] 预览模式，未执行任何更改")
        
        print(f"\n统计:")
        print(f"  总记录数: {stats['total']}")
        print(f"  dimensions 转换: {stats['dimensions_updated']}")
        print(f"  reference_params 转换: {stats['ref_params_updated']}")
        print(f"  test_type 设置: {stats['test_type_set']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='迁移测试用例数据到新格式')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不执行任何更改')
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)
