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

CREATE TABLE frames (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    slots JSONB,
    storage_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE vouchers (
    code TEXT PRIMARY KEY,
    uses_left INT DEFAULT 1,
    custom_frame TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tickets (
    code TEXT PRIMARY KEY,
    uses_left INT DEFAULT 1,
    custom_frame TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    order_id TEXT UNIQUE,
    session_id TEXT,
    amount INT,
    method TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

Storage buckets: "fotobox-photos" (public), "frames" (public)
"""

import os, json
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_supabase_client = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        _supabase_client = create_client(url, key)
    return _supabase_client


# ══════════════════════════════════════════════════════════
# SESSIONS
# ══════════════════════════════════════════════════════════

def create_session(session_id: str, order_id: str) -> dict:
    sb = get_supabase()
    data = {"id": session_id, "midtrans_order_id": order_id, "status": "pending"}
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
    res = sb.table("sessions").select("*").order("created_at", desc=True).limit(limit).execute()
    return res.data or []


# ══════════════════════════════════════════════════════════
# PHOTO STORAGE (fotobox-photos bucket)
# ══════════════════════════════════════════════════════════

def upload_photo(session_id: str, photo_index: int, img_bytes: bytes) -> str:
    sb = get_supabase()
    path = f"{session_id}/photo_{photo_index}.png"
    sb.storage.from_("fotobox-photos").upload(path, img_bytes, {"content-type": "image/png", "upsert": "true"})
    return sb.storage.from_("fotobox-photos").get_public_url(path)

def upload_strip(session_id: str, img_bytes: bytes) -> str:
    sb = get_supabase()
    path = f"{session_id}/strip_final.png"
    sb.storage.from_("fotobox-photos").upload(path, img_bytes, {"content-type": "image/png", "upsert": "true"})
    return sb.storage.from_("fotobox-photos").get_public_url(path)

def upload_file(session_id: str, filename: str, content: bytes, content_type: str) -> str:
    sb = get_supabase()
    path = f"{session_id}/{filename}"
    sb.storage.from_("fotobox-photos").upload(path, content, {"content-type": content_type, "upsert": "true"})
    return sb.storage.from_("fotobox-photos").get_public_url(path)


# ══════════════════════════════════════════════════════════
# FRAMES (DB + Storage)
# ══════════════════════════════════════════════════════════

def db_get_all_frames() -> list:
    sb = get_supabase()
    res = sb.table("frames").select("*").order("created_at").execute()
    return res.data or []

def db_upsert_frame(frame_id: str, display_name: str, slots: list, storage_url: str) -> dict:
    sb = get_supabase()
    data = {"id": frame_id, "display_name": display_name, "slots": slots, "storage_url": storage_url}
    res = sb.table("frames").upsert(data).execute()
    return res.data[0] if res.data else {}

def db_delete_frame(frame_id: str):
    sb = get_supabase()
    sb.table("frames").delete().eq("id", frame_id).execute()
    try:
        sb.storage.from_("frames").remove([frame_id])
    except Exception as e:
        print(f"Storage delete error: {e}")

def storage_upload_frame(filename: str, content: bytes) -> str:
    sb = get_supabase()
    sb.storage.from_("frames").upload(filename, content, {"content-type": "image/png", "upsert": "true"})
    return sb.storage.from_("frames").get_public_url(filename)

def storage_download_frame(filename: str) -> bytes | None:
    sb = get_supabase()
    try:
        return sb.storage.from_("frames").download(filename)
    except Exception as e:
        print(f"Frame download error for {filename}: {e}")
        return None

def sync_frames_to_local(frames_dir: str = "static/frames"):
    """Download all frames from Supabase to local cache."""
    os.makedirs(frames_dir, exist_ok=True)
    try:
        frames = db_get_all_frames()
        count = 0
        for frame in frames:
            filename = frame["id"]
            local_path = os.path.join(frames_dir, filename)
            json_path = os.path.splitext(local_path)[0] + ".json"

            # Download PNG if not exists locally
            if not os.path.exists(local_path):
                content = storage_download_frame(filename)
                if content:
                    with open(local_path, 'wb') as f:
                        f.write(content)
                    count += 1

            # Write slot + display_name JSON sidecar
            sidecar = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as jf:
                        sidecar = json.load(jf)
                except:
                    pass
            if frame.get("slots"):
                sidecar["slots"] = frame["slots"]
            if frame.get("display_name"):
                sidecar["display_name"] = frame["display_name"]
            with open(json_path, 'w') as jf:
                json.dump(sidecar, jf, indent=2)

        print(f"Synced {count} new frames from Supabase ({len(frames)} total in DB)")
        return len(frames)
    except Exception as e:
        print(f"Frame sync error: {e}")
        return 0

def upload_local_frames_to_supabase(frames_dir: str = "static/frames"):
    """Upload any local frames that aren't yet in Supabase (for initial migration)."""
    try:
        existing = {f["id"] for f in db_get_all_frames()}
        for fname in sorted(os.listdir(frames_dir)):
            if not fname.lower().endswith(".png"):
                continue
            if fname in existing:
                continue
            local_path = os.path.join(frames_dir, fname)
            json_path = os.path.splitext(local_path)[0] + ".json"

            # Upload PNG to storage
            with open(local_path, 'rb') as f:
                content = f.read()
            storage_url = storage_upload_frame(fname, content)

            # Read sidecar for display_name and slots
            display_name = fname.replace('.png', '').replace('_', ' ').title()
            slots = []
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as jf:
                        sidecar = json.load(jf)
                    if sidecar.get("display_name"):
                        display_name = sidecar["display_name"]
                    if sidecar.get("slots"):
                        slots = sidecar["slots"]
                except:
                    pass

            db_upsert_frame(fname, display_name, slots, storage_url)
            print(f"Uploaded frame to Supabase: {fname}")
    except Exception as e:
        print(f"Frame upload migration error: {e}")


# ══════════════════════════════════════════════════════════
# VOUCHERS (DB)
# ══════════════════════════════════════════════════════════

def db_get_all_vouchers() -> list:
    sb = get_supabase()
    res = sb.table("vouchers").select("*").order("created_at").execute()
    return res.data or []

def db_upsert_voucher(code: str, uses_left: int, custom_frame: str = None) -> dict:
    sb = get_supabase()
    data = {"code": code, "uses_left": uses_left}
    if custom_frame:
        data["custom_frame"] = custom_frame
    res = sb.table("vouchers").upsert(data).execute()
    return res.data[0] if res.data else {}

def db_update_voucher_uses(code: str, uses_left: int):
    sb = get_supabase()
    sb.table("vouchers").update({"uses_left": uses_left}).eq("code", code).execute()

def db_delete_voucher(code: str):
    sb = get_supabase()
    sb.table("vouchers").delete().eq("code", code).execute()

def sync_vouchers_from_db() -> dict:
    """Load all vouchers from Supabase into a dict format."""
    rows = db_get_all_vouchers()
    result = {}
    for r in rows:
        result[r["code"]] = {
            "uses_left": r["uses_left"],
            "created_at": r.get("created_at", ""),
            "custom_frame": r.get("custom_frame")
        }
    return result

def upload_local_vouchers_to_supabase(voucher_dict: dict):
    """Migrate local vouchers.json to Supabase (one-time)."""
    try:
        existing = {r["code"] for r in db_get_all_vouchers()}
        for code, data in voucher_dict.items():
            if code not in existing:
                db_upsert_voucher(code, data.get("uses_left", 0), data.get("custom_frame"))
                print(f"Migrated voucher to Supabase: {code}")
    except Exception as e:
        print(f"Voucher migration error: {e}")


# ══════════════════════════════════════════════════════════
# TICKETS (DB)
# ══════════════════════════════════════════════════════════

def db_get_all_tickets() -> list:
    sb = get_supabase()
    res = sb.table("tickets").select("*").order("created_at").execute()
    return res.data or []

def db_upsert_ticket(code: str, uses_left: int, custom_frame: str = None) -> dict:
    sb = get_supabase()
    data = {"code": code, "uses_left": uses_left}
    if custom_frame:
        data["custom_frame"] = custom_frame
    res = sb.table("tickets").upsert(data).execute()
    return res.data[0] if res.data else {}

def db_update_ticket_uses(code: str, uses_left: int):
    sb = get_supabase()
    sb.table("tickets").update({"uses_left": uses_left}).eq("code", code).execute()

def db_delete_ticket(code: str):
    sb = get_supabase()
    sb.table("tickets").delete().eq("code", code).execute()

def sync_tickets_from_db() -> dict:
    """Load all tickets from Supabase into a dict format."""
    rows = db_get_all_tickets()
    result = {}
    for r in rows:
        result[r["code"]] = {
            "uses_left": r["uses_left"],
            "created_at": r.get("created_at", ""),
            "custom_frame": r.get("custom_frame")
        }
    return result

def upload_local_tickets_to_supabase(ticket_dict: dict):
    """Migrate local tickets.json to Supabase (one-time)."""
    try:
        existing = {r["code"] for r in db_get_all_tickets()}
        for code, data in ticket_dict.items():
            if code not in existing:
                db_upsert_ticket(code, data.get("uses_left", 0), data.get("custom_frame"))
                print(f"Migrated ticket to Supabase: {code}")
    except Exception as e:
        print(f"Ticket migration error: {e}")


# ══════════════════════════════════════════════════════════
# PAYMENTS (DB)
# ══════════════════════════════════════════════════════════

def db_insert_payment(order_id: str, session_id: str, amount: int, method: str, status: str = "pending") -> dict:
    sb = get_supabase()
    data = {"order_id": order_id, "session_id": session_id, "amount": amount, "method": method, "status": status}
    try:
        res = sb.table("payments").upsert(data, on_conflict="order_id").execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        print(f"Payment insert error: {e}")
        return {}

def db_update_payment_status(order_id: str, status: str):
    sb = get_supabase()
    try:
        sb.table("payments").update({"status": status}).eq("order_id", order_id).execute()
    except Exception as e:
        print(f"Payment update error: {e}")

def db_get_all_payments(limit: int = 100) -> list:
    sb = get_supabase()
    res = sb.table("payments").select("*").order("created_at", desc=True).limit(limit).execute()
    return res.data or []

def db_get_photo_history(limit: int = 100) -> list:
    """Get completed sessions as photo history."""
    sb = get_supabase()
    res = (
        sb.table("sessions")
        .select("id, frame_choice, filter_choice, photo_urls, strip_url, created_at")
        .eq("status", "completed")
        .not_.is_("strip_url", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    results = []
    for item in res.data or []:
        results.append({
            "session_id": item["id"],
            "frame": item.get("frame_choice", "Unknown"),
            "filter": item.get("filter_choice", "Natural"),
            "photos": len(item.get("photo_urls", []) or []),
            "strip_url": item.get("strip_url", ""),
            "created_at": item.get("created_at", "")
        })
    return results
