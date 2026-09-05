import razorpay
from typing import Dict, Any, Optional
import config

class RazorpayClient:
    def __init__(self):
        """Initializes the Razorpay client using config credentials."""
        if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
            print("WARNING: Razorpay credentials are not fully configured in config.py")
            # fallback to avoid crashing instantly if keys are empty in .env.example testing
            self.client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID or "dummy", config.RAZORPAY_KEY_SECRET or "dummy"))
        else:
            self.client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))

    def create_order(self, amount_paise: int, receipt: str, notes: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            data = {
                "amount": amount_paise,
                "currency": config.CURRENCY,
                "receipt": receipt,
                "notes": notes or {}
            }
            return self.client.order.create(data=data)
        except Exception as e:
            return {"error": str(e)}

    def create_payment_link(self, amount_paise: int, description: str, customer_name: str, customer_email: str, customer_contact: str, notes: Optional[Dict[str, str]] = None, reference_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            data = {
                "amount": amount_paise,
                "currency": config.CURRENCY,
                "description": description,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                    "contact": customer_contact
                },
                "notify": {"sms": True, "email": True},
                "reminder_enable": True,
                "notes": notes or {}
            }
            if reference_id:
                data["reference_id"] = reference_id
            
            pl = self.client.payment_link.create(data)
            return {
                "id": pl.get("id"),
                "short_url": pl.get("short_url"),
                "status": pl.get("status")
            }
        except Exception as e:
            return {"error": str(e)}

    def fetch_payment_link(self, link_id: str) -> Dict[str, Any]:
        try:
            return self.client.payment_link.fetch(link_id)
        except Exception as e:
            return {"error": str(e)}

    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        try:
            return self.client.payment.fetch(payment_id)
        except Exception as e:
            return {"error": str(e)}

    def fetch_order_payments(self, order_id: str) -> Dict[str, Any]:
        try:
            return self.client.order.payments(order_id)
        except Exception as e:
            return {"error": str(e)}
