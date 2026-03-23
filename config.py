import os
from dotenv import load_dotenv

load_dotenv()

# Zoho OAuth
ZOHO_CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
ZOHO_CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
ZOHO_REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')
ZOHO_RECRUIT_BASE = 'https://recruit.zoho.com/recruit/v2'
ZOHO_ACCOUNTS_URL = 'https://accounts.zoho.com/oauth/v2/token'

# OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Score thresholds
# 0–30   → Rejected
# 31–59  → Saved for the future
# 60–100 → Associated
REJECT_THRESHOLD = 30
SAVE_FOR_FUTURE_THRESHOLD = 60

# Exact Zoho Recruit Candidate_Status values
STATUS_REJECTED = "Rejected"
STATUS_SAVE_FOR_FUTURE = "Saved for the future - applied"
STATUS_ASSOCIATED = "Associated"

# Countries: auto-reject if score < 60, associate if score >= 60
AUTO_REJECT_COUNTRIES = {
    "india",
    "pakistan",
    "nigeria",
    "kenya",
    "ghana",
    "south africa",
    "uganda",
    "tanzania",
    "ethiopia",
    "egypt",
    "algeria",
    "morocco",
    "tunisia",
}
