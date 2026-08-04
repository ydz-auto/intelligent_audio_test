from shared.utils.log_handler import _cached_socketio


def get_socketio():
    """获取全局 socketio 实例（由 api_gateway 通过 set_socketio 设置）"""
    return _cached_socketio
