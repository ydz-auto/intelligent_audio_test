from shared.infrastructure.storage import storage

data = storage.load_bytes('oss://audios/test.wav')
print('audio bytes', len(data))
