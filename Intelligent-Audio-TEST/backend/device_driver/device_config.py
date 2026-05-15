from typing import Dict, Any

DEVICE_DRIVER_CONFIG = {
    'mock_mode': True
}

DEVICE_CONFIGS = {
    'android': {
        'app_name': 'com.larus.nova',
        'unlock_password': '000000',
        'close_buttons': ['取消', '确定', '关闭', 'OK', 'Done', 'Allow', 'Deny', '允许', '拒绝'],
        'popup_keywords': ['权限', 'Permission', '授权', '允许', 'Allow', '提示', 'Notice', '下一步','知道了'],
        'exclude_list': [
            'Translating...', '小艺翻译', 'AI 写真', '按住说话',
            '星期', '月', '日', '密码错误', '确定', '取消', '完成', '解锁'
        ],
        'abnormal_keywords': ['密码错误', '锁定', '重试', '星期']
    },
    'ios': {
        'app_name': 'com.larus.nova',
        'unlock_password': '000000',
        'close_buttons': ['取消', '确定', '关闭', 'OK', 'Done', 'Allow', 'Deny', '允许', '拒绝'],
        'popup_keywords': ['权限', 'Permission', '授权', '允许', 'Allow', '提示', 'Notice','知道了'],
        'exclude_list': [
            '中文', '英语', 'Nova', '设置', '我的', '通知',
            '上滑', '电量', 'iOS', '未插入', '信号', 'WiFi', '蓝牙',
            'AI 写真', '按住说话', '按住', '说话', '翻译', '历史'
        ],
        'abnormal_keywords': []
    },
    'harmonyos': {
        'app_name': 'com.huawei.hmos.vassistant',
        'app_icon_key': 'AppIconCommonView_com.huawei.hmos.vassistant.launcher.VoiceAbility',
        'unlock_password': '000000',
        'close_buttons': ['取消', '确定', '关闭', 'OK', 'Done', 'Allow', 'Deny', '允许', '拒绝','保存'],
        'popup_keywords': ['权限', 'Permission', '授权', '允许', 'Allow', '提示', 'Notice','USB连接方式','选择路径'],
        'exclude_list': [
            '中文', '英语', '同传时请靠近声源', '点击下方按钮说话',
            '开启同传', '停止同传', '同传中', '设置', '我的',
            '浏览器', '相机', '时钟', '日历', '天气', '计算器', '图库',
            '应用市场', '华为视频', '华为音乐', '华为阅读', '智慧生活',
            'Translating', '小艺翻译', '星期', '月', '日', '密码错误', '请重新输入',
            '确定', '取消', '完成', '解锁', '紧急呼叫'
        ],
        'abnormal_keywords': ['密码错误', '重试', '锁定', '星期', '确定'],
        'translation_screen_texts': ['停止同传', '点击下方按钮说话', '同传中'],
        'mode_texts': {
            'zh2en': '同声传译',
            'en2zh': '面对面翻译'
        },
        'start_buttons': ['开启同传', '开始翻译'],
        'confirm_buttons': ['确定', '完成', 'OK', '解锁']
    }
}


def get_device_config(device_type: str) -> Dict[str, Any]:
    return DEVICE_CONFIGS.get(device_type.lower(), {})


def get_device_driver_config() -> Dict[str, Any]:
    return DEVICE_DRIVER_CONFIG
