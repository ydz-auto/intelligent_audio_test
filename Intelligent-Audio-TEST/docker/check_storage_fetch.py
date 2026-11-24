import os
import pathlib
import sys

repo = pathlib.Path(r'D:\00_code\V10.11.2\Intelligent-Audio-TEST')
env_path = repo / 'logs' / 'host_services' / 'remote.env'
for line in env_path.read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(repo))

from shared.infrastructure.storage import storage

mode = sys.argv[1] if len(sys.argv) > 1 else 'cache'
if mode == 'cache':
    # 故意指向不可达地址：命中本地缓存时不应发起服务器请求
    os.environ['STORAGE_SERVER_FETCH_URL'] = 'http://127.0.0.1:1'

path = storage.load_file('oss://audios/test.wav')
print(mode, 'temp=', path, 'size=', os.path.getsize(path))
os.remove(path)
print('cache_exists=', os.path.exists(r'D:\00_code\static\audios\test.wav'))
