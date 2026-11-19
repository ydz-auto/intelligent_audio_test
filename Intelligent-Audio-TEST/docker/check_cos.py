from shared.infrastructure.storage import storage

path = storage.save_bytes(b'iat-deploy-check', 'temp', 'deploy-check.txt')
print('saved', path)
print('exists', storage.exists(path))
print('read', storage.load_bytes(path))
storage.delete(path)
print('deleted')
