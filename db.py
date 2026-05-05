"""
db.py — Supabase helper untuk PhotoBooth
Tabel yang dibutuhkan (jalankan di Supabase SQL editor):

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',   -- pending | paid | completed
    midtrans_order_id TEXT,
    frame_choice TEXT,
    mirror BOOLEAN DEFAULT FALSE,
    filter_choice TEXT DEFAULT 'Original',
    photo_urls TEXT[],               -- array of storage URLs
    strip_url TEXT
);

Storage bucket: "fotobox-photos" (public)
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# We can cache the client manually if needed, but Supabase python client is lightweight
_supabase_client = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        _supabase_client = create_client(url, key)
    return _supabase_client


def create_session(session_id: str, order_id: str) -> dict:
    sb = get_supabase()
    data = {
        "id": session_id,
        "midtrans_order_id": order_id,
        "status": "pending",
    }
    res = sb.table("sessions").insert(data).execute()
    return res.data[0] if res.data else {}


def update_session(session_id: str, **kwargs) -> dict:
    sb = get_supabase()
    res = sb.table("sessions").update(kwargs).eq("id", session_id).execute()
    return res.data[0] if res.data else {}


def get_session(session_id: str) -> dict | None:
    sb = get_supabase()
    res = sb.table("sessions").select("*").eq("id", session_id).execute()
    return res.data[0] if res.data else None


def get_all_sessions(limit: int = 100) -> list:
    sb = get_supabase()
    res = (
        sb.table("sessions")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def upload_photo(session_id: str, photo_index: int, img_bytes: bytes) -> str:
    """Upload foto ke Supabase Storage, return public URL."""
    sb = get_supabase()
    path = f"{session_id}/photo_{photo_index}.png"
    sb.storage.from_("fotobox-photos").upload(
        path, img_bytes, {"content-type": "image/png", "upsert": "true"}
    )
    public_url = sb.storage.from_("fotobox-photos").get_public_url(path)
    return public_url


def upload_strip(session_id: str, img_bytes: bytes) -> str:
    """Upload strip final ke Supabase Storage, return public URL."""
    sb = get_supabase()
    path = f"{session_id}/strip_final.png"
    sb.storage.from_("fotobox-photos").upload(
        path, img_bytes, {"content-type": "image/png", "upsert": "true"}
    )
    public_url = sb.storage.from_("fotobox-photos").get_public_url(path)
    return public_url

def upload_file(session_id: str, filename: str, content: bytes, content_type: str) -> str:
    """Upload file ke Supabase Storage, return public URL."""
    sb = get_supabase()
    path = f"{session_id}/{filename}"
    sb.storage.from_("fotobox-photos").upload(
        path, content, {"content-type": content_type, "upsert": "true"}
    )
    public_url = sb.storage.from_("fotobox-photos").get_public_url(path)
    return public_url
