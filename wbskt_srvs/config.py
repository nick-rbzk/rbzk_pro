import os
from dotenv import load_dotenv

load_dotenv()

# Coinbase API credentials (not strictly needed for public WebSocket, but kept for compatibility)
COINBASE_API_KEY = os.environ.get("COINBASE_API_KEY", "")
COINBASE_API_SECRET = os.environ.get("COINBASE_API_SECRET", "")

# Redis configuration (using service name from docker-compose)
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))

# WebSocket configuration
PRODUCT_IDS = os.environ.get("PRODUCT_IDS", "BTC-USD,XLM-USD").split(",")
WEBSOCKET_HEALTH_PORT = int(os.environ.get("WEBSOCKET_HEALTH_PORT", 8080))