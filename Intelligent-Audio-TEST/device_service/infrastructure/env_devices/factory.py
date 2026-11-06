import logging

logger = logging.getLogger(__name__)


class EnvDeviceFactory:
    _registry = {}

    @classmethod
    def register(cls, device_type, device_class):
        cls._registry[device_type] = device_class

    @classmethod
    def create(cls, device_type, config=None):
        device_class = cls._registry.get(device_type)
        if not device_class:
            logger.warning("未注册的环境设备类型: %s", device_type)
            return None
        return device_class(config)

    @classmethod
    def create_from_config(cls, configs):
        devices = []
        for cfg in (configs or []):
            if not isinstance(cfg, dict):
                continue
            device_type = cfg.get('device_type')
            if not device_type:
                continue
            dev = cls.create(device_type, cfg)
            if dev:
                devices.append(dev)
        return devices
