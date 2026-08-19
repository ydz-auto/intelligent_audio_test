import argparse
from app.app import create_app
from app.config import config

def main():
    parser = argparse.ArgumentParser(description='WER/SER Calculator Service')
    parser.add_argument('--port', type=int, default=config.PORT, help='Port to listen on')
    parser.add_argument('--host', type=str, default=config.HOST, help='Host to listen on')
    args = parser.parse_args()

    app = create_app()

    # 使用 waitress 生产级 WSGI 服务器（固定线程池，避免线程爆炸）
    from waitress import create_server
    # 线程数 = 本地并发数的 2 倍 + 4（计算线程 + 状态查询线程 + 余量）
    num_threads = config.WSGI_THREADS or min(config.LOCAL_MAX_CONCURRENCY * 2 + 4, 32)
    server = create_server(app, host=args.host, port=args.port, threads=num_threads)

    print(f"Starting Eval Server on {args.host}:{args.port} (waitress, threads={num_threads})...")
    server.run()

if __name__ == '__main__':
    main()
