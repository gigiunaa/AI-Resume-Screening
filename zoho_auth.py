import time
import requests
import config


class ZohoAuth:
    def __init__(self):
        self.access_token = None
        self.token_expiry = 0

    def get_token(self):
        if time.time() > self.token_expiry or not self.access_token:
            self._refresh()
        return self.access_token

    def _refresh(self):
        print("[Auth] Refreshing Zoho token...")
        resp = requests.post(config.ZOHO_ACCOUNTS_URL, data={
            'refresh_token': config.ZOHO_REFRESH_TOKEN,
            'client_id': config.ZOHO_CLIENT_ID,
            'client_secret': config.ZOHO_CLIENT_SECRET,
            'grant_type': 'refresh_token'
        })
        data = resp.json()
        if 'access_token' not in data:
            raise Exception(f"Token refresh failed: {data}")
        self.access_token = data['access_token']
        self.token_expiry = time.time() + 3500
        print("[Auth] Token refreshed ✅")


auth = ZohoAuth()
