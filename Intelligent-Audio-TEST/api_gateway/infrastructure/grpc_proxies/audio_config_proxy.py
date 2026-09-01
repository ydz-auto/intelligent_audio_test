"""Audio 配置 CRUD 代理：_AudioConfigProxy 及模块级单例 audio_config_service。

通过多继承组合 _AudioConfigQueryMixin（读）与 _AudioConfigCommandMixin（写/上传/转换/预览），
替代原 AudioCommandService/AudioQueryService/AudioUploadService/
AudioConvertService/AudioPreviewService 直接操作 DB 的方式，
网关侧不再 import Audio 模型和 get_db_session()，统一走 gRPC。
所有方法返回 dict: {success, message, data, code}
"""
from shared.clients.grpc_clients import get_audio_config_service_stub

from ._AudioConfigQueryMixin import _AudioConfigQueryMixin
from ._AudioConfigCommandMixin import _AudioConfigCommandMixin


class _AudioConfigProxy(_AudioConfigQueryMixin, _AudioConfigCommandMixin):
    """Audio 配置 CRUD 代理：把方法调用转发到 gRPC AudioConfigService

    继承读/写两个 mixin，对外保持与原单类 _AudioConfigProxy 完全一致的接口。
    """

    @property
    def stub(self):
        """获取 AudioConfigService stub（供需要直接调 RPC 的场景使用）"""
        return get_audio_config_service_stub()


# Audio 配置 CRUD 模块级单例
audio_config_service = _AudioConfigProxy()
