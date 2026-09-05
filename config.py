import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MAX_SESSION_SPEND = 5000000
CONFIRMATION_THRESHOLD = 1000
MAX_ITEMS_PER_ADD = 5
CURRENCY = 'INR'

RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
AUDIT_LOG_PATH = DATA_DIR / 'audit_log.jsonl'
