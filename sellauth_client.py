import requests
import config

class SellAuthError(Exception):
    pass

class SellAuthClient:
    def __init__(self, shop_id: str, api_key: str):
        self.shop_id = shop_id
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _handle(self, resp: requests.Response):
        if not resp.ok:
            try:
                data = resp.json()
            except Exception:
                data = {"message": resp.text}
            raise SellAuthError(f"{resp.status_code} | {data}")
        try:
            return resp.json()
        except Exception:
            return {}

    def list_products(self):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/products"
        return self._handle(self.session.get(url))

    def get_product(self, product_id: str):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/products/{product_id}"
        return self._handle(self.session.get(url))

    def create_checkout(self, product_id: str, quantity: int, email: str | None, discord_id: int | None):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/checkout"
        payload = {
            "line_items": [{"product_id": product_id, "quantity": quantity}],
            "customer_email": email,
            "metadata": {"discord_id": str(discord_id) if discord_id else None},
        }
        return self._handle(self.session.post(url, json=payload))

    def list_invoices(self, limit: int = 10):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/invoices"
        return self._handle(self.session.get(url, params={"limit": limit}))

    def get_invoice(self, invoice_id: str):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/invoices/{invoice_id}"
        return self._handle(self.session.get(url))

    def refund_invoice(self, invoice_id: str):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/invoices/{invoice_id}/refund"
        return self._handle(self.session.post(url))

    def wallet_transactions(self):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/wallet/transactions"
        return self._handle(self.session.get(url))

    def analytics_overview(self):
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/analytics/overview"
        return self._handle(self.session.get(url))

    def get_customer_by_email(self, email: str):
        # Placeholder: ajusta según la doc real de SellAuth
        url = f"https://api.sellauth.com/v1/shops/{self.shop_id}/customers"
        resp = self.session.get(url, params={"email": email, "perPage": 1})
        data = self._handle(resp)
        customers = data.get("data", data if isinstance(data, list) else [])
        if not customers:
            return None
        if isinstance(customers, list):
            return customers[0]
        return customers

sellauth = SellAuthClient(config.SELLAUTH_SHOP_ID or "", config.SELLAUTH_API_KEY or "")
