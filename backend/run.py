"""
KubeTrain2 - 启动入口
用法: conda activate bs && python run.py
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)

from app import create_app, socketio
from config import Config

Config.validate_secrets()
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8010))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = app.config.get('DEBUG', False)
    print(f"KubeTrain2 Backend: Starting on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
