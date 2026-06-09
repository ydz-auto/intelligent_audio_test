import argparse
from app.app import create_app
from app.config import config

def main():
    parser = argparse.ArgumentParser(description='WER/SER Calculator Service')
    parser.add_argument('--port', type=int, default=config.PORT, help='Port to listen on')
    parser.add_argument('--host', type=str, default=config.HOST, help='Host to listen on')
    args = parser.parse_args()

    app = create_app()
    
    print(f"Starting WER Calculator Service on {args.host}:{args.port}...")
    app.run(host=args.host, port=args.port, debug=config.DEBUG, use_reloader=False)

if __name__ == '__main__':
    main()
