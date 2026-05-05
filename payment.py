"""
payment.py — Midtrans SNAP integration untuk PhotoBooth

Docs: https://docs.midtrans.com/reference/snap-api
"""

import requests
import base64
import os
from datetime import datetime
import uuid
from dotenv import load_dotenv

load_dotenv()


def _get_auth_header() -> str:
    server_key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    encoded = base64.b64encode(f"{server_key}:".encode()).decode()
    return f"Basic {encoded}"


def _base_url() -> str:
    is_prod = os.environ.get("MIDTRANS_PROD", "false").lower() == "true"
    server_key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    # Auto-detect sandbox jika key diawali SB- atau MIDTRANS_PROD = false
    is_sandbox = (not is_prod) or server_key.startswith("SB-")
    return "https://app.sandbox.midtrans.com/snap/v1" if is_sandbox else "https://app.midtrans.com/snap/v1"


def create_payment(order_id: str, amount: int = 10000) -> dict:
    """
    Buat transaksi Midtrans SNAP.
    Return: {"token": "...", "redirect_url": "...", "order_id": "..."}
    """
    url = f"{_base_url()}/transactions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": _get_auth_header(),
    }
    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": amount,
        },
        "item_details": [
            {
                "id": "FOTOBOX-SESSION",
                "price": amount,
                "quantity": 1,
                "name": "PhotoBooth Session",
            }
        ],
        "customer_details": {
            "first_name": "Guest",
        },
        "expiry": {
            "unit": "minutes",
            "duration": 10,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {
        "token": data.get("token"),
        "redirect_url": data.get("redirect_url"),
        "order_id": order_id,
    }


def check_payment_status(order_id: str) -> str:
    """
    Cek status pembayaran.
    Return: 'paid' | 'pending' | 'expired' | 'failed'
    """
    is_prod = os.environ.get("MIDTRANS_PROD", "false").lower() == "true"
    server_key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    is_sandbox = (not is_prod) or server_key.startswith("SB-")
    base = "https://api.sandbox.midtrans.com" if is_sandbox else "https://api.midtrans.com"
    url = f"{base}/v2/{order_id}/status"
    headers = {"Authorization": _get_auth_header()}
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        return "pending"
    data = resp.json()
    tx_status = data.get("transaction_status", "pending")
    fraud = data.get("fraud_status", "accept")

    if tx_status in ("capture", "settlement") and fraud == "accept":
        return "paid"
    elif tx_status in ("cancel", "deny", "expire"):
        return "failed"
    else:
        return "pending"


def generate_order_id() -> str:
    return f"FOTOBOX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"