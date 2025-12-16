# app/db/mongodb.py  (async for FastAPI)
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import MONGO_URI, DB_NAME

# Configure MongoDB client with proper timeouts to prevent operation cancellation
client = AsyncIOMotorClient(
    MONGO_URI,
    serverSelectionTimeoutMS=30000,  # 30 seconds to find a server
    connectTimeoutMS=20000,  # 20 seconds to establish connection
    socketTimeoutMS=60000,  # 60 seconds for socket operations
    maxPoolSize=50,  # Maximum connections in pool
    minPoolSize=5,  # Minimum connections in pool
    retryWrites=True,
    retryReads=True
)
db = client[DB_NAME]
