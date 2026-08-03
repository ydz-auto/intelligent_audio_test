import argparse
import socket
import sys
from app.app import create_app
from app.config import config

def is_port_available(host, port):
    """检测端口是否可用（未被监听 / 无大量 TIME_WAIT 残留）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False

def main():
    parser = argparse.ArgumentParser(description='WER/SER Calculator Service')
    parser.add_argument('--port', type=int, default=config.PORT, help='Port to listen on')
    parser.add_argument('--host', type=str, default=config.HOST, help='Host to listen on')
    args = parser.parse_args()

    # 启动前检测端口是否可用
    check_host = '127.0.0.1' if args.host in ('0.0.0.0', '::', '') else args.host
    if not is_port_available(check_host, args.port):
        print(f"[ERROR] 端口 {args.port} 被占用或存在大量 TIME_WAIT 连接，无法启动服务。")
        print(f"        可通过 --port 指定其他端口，例如: python app.py --port 8888")
        print(f"        或等待 1-4 分钟让 TIME_WAIT 自动回收后再重试。")
        sys.exit(1)

    app = create_app()

    # 使用 waitress 生产级 WSGI 服务器（固定线程池，避免线程爆炸）
    from waitress import create_server
    # 线程数 = 本地并发数的 2 倍 + 4（计算线程 + 状态查询线程 + 余量）
    num_threads = config.WSGI_THREADS or min(config.LOCAL_MAX_CONCURRENCY * 2 + 4, 32)
    server = create_server(app, host=args.host, port=args.port, threads=num_threads)

    print(f"Starting WER Calculator Service on {args.host}:{args.port} (waitress, threads={num_threads})...")
    server.run()

if __name__ == '__main__':
    main()
