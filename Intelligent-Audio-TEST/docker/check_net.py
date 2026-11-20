import socket
import urllib.request

for port in (50052, 50053):
    sock = socket.create_connection(('100.123.155.32', port), 5)
    print('hardware', port, 'OK')
    sock.close()

print('asr', urllib.request.urlopen('http://100.103.97.108:10095/health', timeout=8).status)
