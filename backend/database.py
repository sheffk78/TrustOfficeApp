# Database connection and helpers
from motor.motor_asyncio import AsyncIOMotorClient
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
# setdefault (2026-10-01 collection-fix): bare imports (pytest full-suite
# collection, dev tooling) crashed with KeyError('MONGO_URL') because only
# some suites setdefault their env vars first — 19 downstream test files
# failed with cascading "unknown location" ImportErrors on every full run.
# Env vars still win (Railway prod sets them; .env loads above); the fallback
# is a LOCAL-only default that can never reach production.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(
    mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
    maxPoolSize=50,
    minPoolSize=5,
    maxIdleTimeMS=60000,
    waitQueueTimeoutMS=5000,
)
os.environ.setdefault("DB_NAME", "trustoffice_fallback_local")
db = client[os.environ["DB_NAME"]]
