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

# Screening Settings
REJECT_THRESHOLD = 50
