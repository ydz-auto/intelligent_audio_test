from shared.infrastructure.config import BaseConfig
from shared.infrastructure.storage import storage

print('backend=', BaseConfig.STORAGE_BACKEND,
      'addressing=', BaseConfig.OSS_ADDRESSING_STYLE or 'auto',
      'endpoint=', BaseConfig.OSS_ENDPOINT)
path = storage.save_bytes(b'iat-deploy-check', 'temp', 'deploy-check.txt')
print('saved', path)
print('exists', storage.exists(path))
print('read', storage.load_bytes(path))
storage.delete(path)
print('deleted')
