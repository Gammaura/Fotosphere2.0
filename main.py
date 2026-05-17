from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse, Response, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
import uuid
import io
import os
import re
import gc
import base64
import qrcode
import json
import secrets
import socket
import string
import random
import threading
import time
import urllib.parse
import dotenv
from typing import List, Optional
from datetime import datetime
from PIL import Image

from payment import create_payment, check_payment_status, generate_order_id
from db import (
    create_session, update_session, upload_photo, upload_strip, upload_file,
    get_session, get_all_sessions,
    # Frames
    db_upsert_frame, db_delete_frame, storage_upload_frame, storage_download_frame,
    db_upsert_custom_frame, db_delete_custom_frame, storage_upload_custom_frame, storage_download_custom_frame,
    sync_frames_to_local, upload_local_frames_to_supabase,
    # Vouchers
    db_upsert_voucher, db_update_voucher_uses, db_delete_voucher,
    sync_vouchers_from_db, upload_local_vouchers_to_supabase,
    # Tickets
    db_upsert_ticket, db_update_ticket_uses, db_delete_ticket,
    sync_tickets_from_db, upload_local_tickets_to_supabase,
    # Payments & Photos
    db_insert_payment, db_update_payment_status, db_get_all_payments,
    db_get_photo_history,
    upload_local_payments_to_supabase,
)
from utils import (
    FILTERS, scan_frames_dir, get_frame_slots,
    composite_photos_on_frame, pil_to_bytes, apply_filter
)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
os.makedirs("static/assets", exist_ok=True)
os.makedirs("static/frames", exist_ok=True)
os.makedirs("static/custom_frames", exist_ok=True)

# ── App Configuration ─────────────────────────────────────
QRIS_PRICE = int(os.environ.get("QRIS_PRICE", "30000"))

# In-memory stores (ephemeral — session photos only)
SESSION_STORE = {} # session_id -> {"photos": [], "timestamp": datetime, ...}

# Vouchers & Tickets — loaded from Supabase on startup
VOUCHER_CODES = {}  # code -> {uses_left, created_at, custom_frame}
TICKET_CODES = {}   # code -> {uses_left, created_at, custom_frame}

# ── Secure Admin Token Store ──────────────────────────────
# Tokens are generated per login session — no more hardcoded secrets
ADMIN_TOKENS = set()  # set of valid token strings

def require_admin(request: Request):
    """FastAPI dependency: verify admin cookie token."""
    token = request.cookies.get("admin_token")
    if not token or token not in ADMIN_TOKENS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token

# ── Helper: find frame data across public + custom dirs ───
def find_frame_data(frame_id: str) -> dict | None:
    """Look up a frame by filename across public and custom frame directories."""
    all_frames = get_frames() + scan_frames_dir("static/custom_frames")
    frame_data = next((f for f in all_frames if f["id"] == frame_id), None)
    if frame_data:
        thumb_prefix = "/custom_frames/" if frame_data.get("is_private") else "/frames/"
        return {
            "id": frame_data["id"], "name": frame_data["name"], "photos": frame_data["photos"],
            "layout": frame_data["layout"], "width": frame_data["width"], "height": frame_data["height"],
            "slots": frame_data["slots"], "thumb": f"{thumb_prefix}{frame_data['file']}"
        }
    return None

# ── Atomic lock for voucher/ticket claims ─────────────────
_claim_lock = threading.Lock()

# (threading and time already imported at top)

def cleanup_sessions_task():
    """Periodically clear old sessions from memory."""
    global SESSION_STORE
    while True:
        try:
            now = datetime.utcnow()
            to_delete = []
            for sid, data in SESSION_STORE.items():
                created_at = data.get("created_at", now)
                if (now - created_at).total_seconds() > 1200:
                    to_delete.append(sid)
            for sid in to_delete:
                print(f"Cleaning up stale session: {sid}")
                del SESSION_STORE[sid]
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(600)

threading.Thread(target=cleanup_sessions_task, daemon=True).start()

# ── Startup: Sync everything from Supabase ──
def startup_sync():
    global VOUCHER_CODES, TICKET_CODES
    print("═══ Syncing data from Supabase ═══")

    # 1. Frames: upload any local-only frames to Supabase, then download missing ones
    try:
        upload_local_frames_to_supabase()
        sync_frames_to_local()
    except Exception as e:
        print(f"Frame sync warning: {e}")

    # 2. Vouchers: migrate local JSON if exists, then load from DB
    local_voucher_file = "static/vouchers.json"
    if os.path.exists(local_voucher_file):
        try:
            with open(local_voucher_file, 'r') as f:
                local_vouchers = json.load(f)
            if local_vouchers:
                upload_local_vouchers_to_supabase(local_vouchers)
                # Rename file so we don't re-migrate
                os.rename(local_voucher_file, local_voucher_file + ".migrated")
                print(f"Migrated {len(local_vouchers)} vouchers from local JSON")
        except Exception as e:
            print(f"Voucher migration warning: {e}")

    try:
        VOUCHER_CODES = sync_vouchers_from_db()
        print(f"Loaded {len(VOUCHER_CODES)} vouchers from Supabase")
    except Exception as e:
        print(f"Voucher load error: {e}")

    # 3. Tickets: same migration pattern
    local_ticket_file = "static/tickets.json"
    if os.path.exists(local_ticket_file):
        try:
            with open(local_ticket_file, 'r') as f:
                local_tickets = json.load(f)
            if local_tickets:
                upload_local_tickets_to_supabase(local_tickets)
                os.rename(local_ticket_file, local_ticket_file + ".migrated")
                print(f"Migrated {len(local_tickets)} tickets from local JSON")
        except Exception as e:
            print(f"Ticket migration warning: {e}")

    try:
        TICKET_CODES = sync_tickets_from_db()
        print(f"Loaded {len(TICKET_CODES)} tickets from Supabase")
    except Exception as e:
        print(f"Ticket load error: {e}")

    # 4. Payments: migrate local JSON if exists
    local_payment_file = "static/payments.json"
    if os.path.exists(local_payment_file):
        try:
            with open(local_payment_file, 'r') as f:
                local_payments = json.load(f)
            if local_payments:
                upload_local_payments_to_supabase(local_payments)
                os.rename(local_payment_file, local_payment_file + ".migrated")
                print(f"Migrated {len(local_payments)} payments from local JSON")
        except Exception as e:
            print(f"Payment migration warning: {e}")

    print("═══ Sync complete ═══")

startup_sync()

def get_frames():
    return scan_frames_dir("static/frames")

# ── Frame thumbnail cache (in-memory, small JPEGs) ───────
_thumb_cache = {}  # filename -> (mtime, jpeg_bytes)
THUMB_SIZE = 200   # max width in px

@app.get("/api/frames/thumb/{filename}")
def api_frame_thumb(filename: str):
    """Return a small JPEG thumbnail of a frame (cached in memory)."""
    # Search in both directories
    for d in ["static/frames", "static/custom_frames"]:
        path = os.path.join(d, filename)
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            cached = _thumb_cache.get(filename)
            if cached and cached[0] == mtime:
                return Response(content=cached[1], media_type="image/jpeg",
                                headers={"Cache-Control": "public, max-age=86400"})
            # Generate thumbnail
            try:
                img = Image.open(path)
                ratio = THUMB_SIZE / img.width
                new_h = int(img.height * ratio)
                img = img.resize((THUMB_SIZE, new_h), Image.LANCZOS)
                # Flatten transparency to white for JPEG
                if img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                    img = bg
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                thumb_bytes = buf.getvalue()
                _thumb_cache[filename] = (mtime, thumb_bytes)
                return Response(content=thumb_bytes, media_type="image/jpeg",
                                headers={"Cache-Control": "public, max-age=86400"})
            except Exception as e:
                print(f"Thumb generation error for {filename}: {e}")
                break
    raise HTTPException(status_code=404, detail="Frame not found")

def make_qr_b64(url: str) -> str:
    qr = qrcode.QRCode(version=2, box_size=8, border=2,
                        error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

@app.get("/api/qr/{code}")
def serve_qr_image(code: str):
    qr = qrcode.QRCode(version=2, box_size=15, border=2, error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")

def make_gif(photos: list, filter_name: str = "Natural") -> bytes:
    """Create animated GIF from session photos."""
    frames = []
    for b in photos:
        img = Image.open(io.BytesIO(b)).convert("RGB")
        # Resize for GIF BEFORE applying filter to save massive amounts of memory and CPU
        img.thumbnail((480, 480), Image.LANCZOS)
        img = apply_filter(img, filter_name)
        frames.append(img)
    if not frames:
        return b""
    
    # Boomerang effect: 0-1-2-3-2-1
    if len(frames) > 2:
        boomerang = frames + frames[-2:0:-1]
    else:
        boomerang = frames
        
    buf = io.BytesIO()
    boomerang[0].save(buf, format="GIF", save_all=True, append_images=boomerang[1:],
                   duration=400, loop=0, optimize=True)
    return buf.getvalue()

# ─── MAIN ROUTES ──────────────────────────────────────────

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

@app.post("/api/payment/create")
def api_create_payment():
    session_id = str(uuid.uuid4())
    order_id = generate_order_id()
    try:
        payment = create_payment(order_id, amount=QRIS_PRICE)
        create_session(session_id, order_id)
        SESSION_STORE[session_id] = {
            "order_id": order_id, "photos": [], "frame_id": None, "mirror": False,
            "created_at": datetime.utcnow()
        }
        db_insert_payment(order_id, session_id, QRIS_PRICE, "QRIS", "pending")
        return {
            "session_id": session_id,
            "order_id": order_id,
            "payment_url": payment["redirect_url"],
            "qr_b64": make_qr_b64(payment["redirect_url"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payment/status/{order_id}")
def api_payment_status(order_id: str):
    try:
        status = check_payment_status(order_id)
        session_id = None
        for sid, data in SESSION_STORE.items():
            if data.get("order_id") == order_id:
                session_id = sid
                break
        if status == "paid":
            if session_id:
                update_session(session_id, status="paid", paid_at=datetime.utcnow().isoformat())
            db_update_payment_status(order_id, "paid")
        return {"status": status, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/payment/webhook")
async def api_payment_webhook(request: Request):
    try:
        data = await request.json()
        order_id = data.get("order_id")
        transaction_status = data.get("transaction_status")
        fraud_status = data.get("fraud_status")
        
        if not order_id or not transaction_status:
            return {"status": "ignored"}
            
        is_paid = False
        if transaction_status == 'capture':
            if fraud_status == 'challenge':
                is_paid = False
            elif fraud_status == 'accept':
                is_paid = True
        elif transaction_status == 'settlement':
            is_paid = True
            
        if is_paid:
            db_update_payment_status(order_id, "paid")
            session_id = None
            for sid, sdata in SESSION_STORE.items():
                if sdata.get("order_id") == order_id:
                    session_id = sid
                    break
            if session_id:
                update_session(session_id, status="paid", paid_at=datetime.utcnow().isoformat())
        elif transaction_status in ['cancel', 'deny', 'expire']:
            db_update_payment_status(order_id, transaction_status)
            
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/config")
def api_get_config():
    frames = get_frames()
    public_frames = []
    for f in frames:
        if not f.get("is_private", False):
            public_frames.append({
                "id": f["id"], "name": f["name"], "photos": f["photos"],
                "layout": f["layout"], "width": f["width"], "height": f["height"],
                "slots": f["slots"], "thumb": f"/frames/{f['file']}",
                "file": f["file"],
                "category": f.get("category", "Other")
            })
    return {
        "frames": public_frames,
        "filters": [{"id": k, "name": k} for k in FILTERS.keys()],
        "qris_price": QRIS_PRICE,
    }

# ─── VOUCHER ──────────────────────────────────────────────

@app.post("/api/voucher/claim")
async def api_claim_voucher(request: Request):
    try:
        body = await request.json()
        code = body.get("code", "").strip().upper()

        with _claim_lock:
            if code in VOUCHER_CODES:
                v = VOUCHER_CODES[code]
                if v.get("uses_left", 0) > 0:
                    session_id = str(uuid.uuid4())
                    order_id = f"VOUCHER-{code}"
                    
                    try:
                        create_session(session_id, order_id)
                    except Exception as db_err:
                        print(f"DB Error creating session: {db_err}")
                        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
                    
                    v["uses_left"] -= 1
                    db_update_voucher_uses(code, v["uses_left"])
                    
                    SESSION_STORE[session_id] = {
                        "order_id": order_id, "photos": [], "frame_id": None, "mirror": False,
                        "created_at": datetime.utcnow()
                    }
                    db_insert_payment(order_id, session_id, 0, "Voucher", "paid")
                    result = {"valid": True, "session_id": session_id}
                    if v.get("custom_frame"):
                        fd = find_frame_data(v["custom_frame"])
                        if fd:
                            result["custom_frame_data"] = fd
                    return result
                    
            # Fallback: Check if they typed a ticket code in the voucher menu
            if code in TICKET_CODES:
                t = TICKET_CODES[code]
                if t.get("uses_left", 0) > 0:
                    session_id = str(uuid.uuid4())
                    order_id = f"TICKET-{code}"
                    try:
                        create_session(session_id, order_id)
                    except Exception as db_err:
                        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
                    t["uses_left"] -= 1
                    db_update_ticket_uses(code, t["uses_left"])
                    SESSION_STORE[session_id] = {
                        "order_id": order_id, "photos": [], "frame_id": None, "mirror": False,
                        "created_at": datetime.utcnow()
                    }
                    db_insert_payment(order_id, session_id, 0, "Ticket", "paid")
                    result = {"valid": True, "session_id": session_id}
                    if t.get("custom_frame"):
                        fd = find_frame_data(t["custom_frame"])
                        if fd:
                            result["custom_frame_data"] = fd
                    return result

        return JSONResponse({"valid": False, "error": "Voucher tidak ditemukan atau sudah habis"}, status_code=404)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Voucher claim error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── SESSION ──────────────────────────────────────────────

@app.post("/api/session/{session_id}/upload")
async def api_upload_photos(
    session_id: str,
    frame_id: str = Form(...),
    mirror: bool = Form(False),
    photos: List[UploadFile] = File(...)
):
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {"photos": [], "order_id": "", "frame_id": None, "mirror": False}

    SESSION_STORE[session_id]["frame_id"] = frame_id
    SESSION_STORE[session_id]["mirror"] = mirror

    saved = []
    urls = []
    for idx, file in enumerate(photos):
        contents = await file.read()
        saved.append(contents)
        try:
            url = upload_photo(session_id, idx, contents)
            urls.append(url)
        except Exception as e:
            print(f"Upload photo {idx} error: {e}")
            urls.append("")

    try:
        SESSION_STORE[session_id]["photos"] = saved
        
        # Pre-generate a 300px base thumbnail for the filter preview to prevent OOM
        frame_path = os.path.join("static/frames", frame_id)
        if not os.path.exists(frame_path):
            frame_path = os.path.join("static/custom_frames", frame_id)
            
        if os.path.exists(frame_path):
            photos_pil = [Image.open(io.BytesIO(b)) for b in saved]
            slots = get_frame_slots(frame_path)
            thumb_img = composite_photos_on_frame(frame_path, photos_pil, slots, "Natural", 300)
            buf = io.BytesIO()
            thumb_img.save(buf, format="JPEG", quality=80)
            SESSION_STORE[session_id]["thumb_base"] = buf.getvalue()
            del thumb_img; del photos_pil; gc.collect()
            
        update_session(session_id, photo_urls=urls, frame_choice=frame_id, mirror=mirror)
        return {"success": True, "uploaded": len(saved)}
    except Exception as e:
        print(f"Update session error: {e}")
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

def log_debug(msg):
    with open("static/debug.log", "a") as f:
        f.write(f"[{datetime.utcnow()}] {msg}\n")

async def ensure_session_loaded(session_id: str):
    """Ensures session photos are in memory, downloading from Supabase if needed."""
    if session_id in SESSION_STORE and SESSION_STORE[session_id].get("photos"):
        return True
    
    log_debug(f"Session {session_id} not in memory, attempting recovery from Supabase...")
    sess = get_session(session_id)
    if not sess or not sess.get("photo_urls"):
        log_debug(f"SESSION RECOVERY FAIL: session {session_id} not found in DB or no photos")
        return False
    
    import requests
    photo_bytes = []
    for url in sess["photo_urls"]:
        try:
            r = requests.get(url, timeout=5)
            if r.ok: photo_bytes.append(r.content)
        except: pass
    
    if not photo_bytes:
        log_debug(f"SESSION RECOVERY FAIL: could not download photos for {session_id}")
        return False
        
    SESSION_STORE[session_id] = {
        "photos": photo_bytes,
        "frame_id": sess.get("frame_choice"),
        "mirror": sess.get("mirror", False),
        "created_at": datetime.utcnow()
    }
    log_debug(f"Session {session_id} recovered successfully")
    return True

@app.get("/api/session/{session_id}/preview")
async def api_preview_strip(session_id: str, filter_name: str = "Natural", thumb: int = 0):
    if not await ensure_session_loaded(session_id):
        raise HTTPException(status_code=404, detail="Session not found or no photos")

    data = SESSION_STORE[session_id]
    if thumb and "thumb_base" in data:
        try:
            img = Image.open(io.BytesIO(data["thumb_base"])).convert("RGB")
            if filter_name != "Natural":
                img = apply_filter(img, filter_name)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            return Response(content=buf.getvalue(), media_type="image/jpeg")
        except Exception as e:
            log_debug(f"THUMB GEN FAIL: {e}")

    frame_id = data.get("frame_id")
    if not frame_id:
        log_debug(f"PREVIEW FAIL: no frame_id in session {session_id}")
        raise HTTPException(status_code=400, detail="No frame selected")

    # Check both frames and custom_frames directories
    frame_path = os.path.join("static/frames", frame_id)
    if not os.path.exists(frame_path):
        frame_path = os.path.join("static/custom_frames", frame_id)

    # 2. Download frame from Supabase if missing locally (critical for cloud)
    if not os.path.exists(frame_path) or os.path.isdir(frame_path):
        log_debug(f"Frame {frame_id} missing locally, downloading from Supabase...")
        try:
            # Try public frames
            fb = storage_download_frame(frame_id)
            if not fb:
                # Try custom frames
                fb = storage_download_custom_frame(frame_id)
            
            if fb:
                os.makedirs(os.path.dirname(frame_path), exist_ok=True)
                with open(frame_path, "wb") as f:
                    f.write(fb)
                log_debug(f"Frame {frame_id} downloaded successfully")
            else:
                log_debug(f"PREVIEW FAIL: frame {frame_id} not in storage")
                raise HTTPException(404, "Frame not found in storage")
        except Exception as e:
            log_debug(f"FRAME DOWNLOAD ERROR: {e}")
            raise HTTPException(500, "Frame download failed")

    try:
        photos_pil = [Image.open(io.BytesIO(b)) for b in data["photos"]]
        slots = get_frame_slots(frame_path)
        
        # Main preview (thumb=0) is limited to 800px
        result = composite_photos_on_frame(frame_path, photos_pil, slots, filter_name, 800)

        fmt = "JPEG"
        buf = io.BytesIO()
        result.save(buf, format=fmt, quality=90)
        del result; [p.close() for p in photos_pil]; gc.collect()
        return Response(content=buf.getvalue(), media_type=f"image/{fmt.lower()}")
    except Exception as e:
        log_debug(f"COMPOSITE FAIL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/{session_id}/finalize")
async def api_finalize_strip(
    request: Request, 
    session_id: str, 
    filter_name: str = Form(...),
    sticker_overlay: Optional[UploadFile] = File(None),
    live_clips: List[UploadFile] = File(default=[])
):
    if not await ensure_session_loaded(session_id):
        raise HTTPException(status_code=404, detail="Session not found or no photos")

    data = SESSION_STORE[session_id]
    frame_id = data["frame_id"]
    frame_path = os.path.join("static/frames", frame_id)
    if not os.path.exists(frame_path):
        frame_path = os.path.join("static/custom_frames", frame_id)

    if not os.path.exists(frame_path):
        raise HTTPException(status_code=404, detail="Frame not found")

    photos_pil = [Image.open(io.BytesIO(b)) for b in data["photos"]]
    slots = get_frame_slots(frame_path)
    result = composite_photos_on_frame(frame_path, photos_pil, slots, filter_name)

    if sticker_overlay:
        try:
            overlay_bytes = await sticker_overlay.read()
            overlay_img = Image.open(io.BytesIO(overlay_bytes)).convert("RGBA")
            overlay_img = overlay_img.resize(result.size, Image.LANCZOS)
            result = result.convert("RGBA")
            result = Image.alpha_composite(result, overlay_img)
            result = result.convert("RGB")
            # Free memory immediately
            del overlay_img
            gc.collect()
        except Exception as e:
            print(f"Failed to apply sticker overlay: {e}")

    strip_bytes = pil_to_bytes(result)
    
    # Free result image from memory
    del result
    del photos_pil
    gc.collect()

    # Generate GIF
    gif_bytes = make_gif(data["photos"], filter_name)
    gif_url = ""

    try:
        url = upload_strip(session_id, strip_bytes)
        update_session(
            session_id, filter_choice=filter_name,
            strip_url=url, status="completed",
            completed_at=datetime.utcnow().isoformat()
        )
        # Photo history is now stored in Supabase sessions table (update_session above)

        # Save GIF locally and upload to Supabase
        if gif_bytes:
            gif_dir = os.path.join("static", "gifs")
            os.makedirs(gif_dir, exist_ok=True)
            gif_path = os.path.join(gif_dir, f"{session_id}.gif")
            with open(gif_path, 'wb') as f:
                f.write(gif_bytes)
            gif_url = upload_file(session_id, "anim.gif", gif_bytes, "image/gif")

        # Upload live photo clips (webm) to Supabase
        live_urls = []
        if live_clips:
            print(f"[LIVE] Received {len(live_clips)} live clips for session {session_id}")
            for i, clip in enumerate(live_clips):
                if clip and clip.filename:
                    try:
                        clip_bytes = await clip.read()
                        if len(clip_bytes) > 0:
                            # Use original filename from frontend (e.g. live_0.webm, live_2.webm)
                            # to preserve the correct slot index
                            fname = clip.filename if clip.filename.startswith("live_") else f"live_{i}.webm"
                            print(f"[LIVE] Uploading {fname} ({len(clip_bytes)} bytes)")
                            clip_url = upload_file(session_id, fname, clip_bytes, "video/webm")
                            live_urls.append(clip_url)
                        else:
                            print(f"[LIVE] Clip {i} ({clip.filename}) is empty, skipping")
                    except Exception as e:
                        print(f"[LIVE] Failed to upload clip {i} ({clip.filename}): {e}")

        del SESSION_STORE[session_id]

        # Generate download URL pointing back to our server
        base = str(request.base_url)
        if "localhost" in base or "127.0.0.1" in base:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                base = base.replace("localhost", local_ip).replace("127.0.0.1", local_ip)
            except Exception:
                pass

        download_url = f"{base}download/{session_id}"

        return {"success": True, "strip_url": url, "qr_b64": make_qr_b64(download_url), "gif_url": gif_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-proxy")
async def download_proxy(request: Request, url: str, filename: str, inline: bool = False):
    import requests as _req
    try:
        headers = {}
        if "range" in request.headers:
            headers["Range"] = request.headers["range"]
            
        r = _req.get(url, headers=headers)
        
        disposition = f"inline; filename={filename}" if inline else f"attachment; filename={filename}"
        resp_headers = {
            "Content-Disposition": disposition,
            "Content-Type": r.headers.get("Content-Type", "application/octet-stream"),
            "Accept-Ranges": "bytes"
        }
        if "Content-Range" in r.headers:
            resp_headers["Content-Range"] = r.headers["Content-Range"]
        if "Content-Length" in r.headers:
            resp_headers["Content-Length"] = r.headers["Content-Length"]
            
        return Response(content=r.content, status_code=r.status_code, headers=resp_headers)
    except Exception as e:
        raise HTTPException(500, f"Download failed: {str(e)}")

@app.get("/download/{session_id}", response_class=HTMLResponse)
def download_page(session_id: str, request: Request):
    session_data = get_session(session_id)
    if not session_data:
        return HTMLResponse("<h1>Session tidak ditemukan</h1><p>Link ini mungkin sudah kadaluarsa.</p>", status_code=404)

    strip_url = session_data.get("strip_url") or ""
    photo_urls = session_data.get("photo_urls") or []
    if not isinstance(photo_urls, list):
        photo_urls = []
    frame_choice = session_data.get("frame_choice") or ""
    
    # Get frame metadata for live photo frame view
    frame_info = None
    if frame_choice:
        frames = get_frames()
        for f in frames:
            if f["id"] == frame_choice:
                frame_info = f
                break
    
    gif_url = ""
    base_path = ""
    if strip_url:
        base_path = strip_url.rsplit("/", 1)[0]
        gif_url = f"{base_path}/anim.gif"
        if not photo_urls:
            photo_urls = [f"{base_path}/photo_{i}.png" for i in range(6)]
    
    n_clips = frame_info["photos"] if frame_info else 6
    live_clip_urls = [f"{base_path}/live_{i}.webm" for i in range(n_clips)] if base_path else []

    import urllib.parse
    def p(u, f): 
        if not u: return "#"
        safe_url = urllib.parse.quote(u, safe='')
        return f"/api/download-proxy?url={safe_url}&filename={f}"

    def p_inline(u, f):
        if not u: return "#"
        safe_url = urllib.parse.quote(u, safe='')
        return f"/api/download-proxy?url={safe_url}&filename={f}&inline=true"

    # Build live photo frame HTML (videos inside frame slots)
    live_frame_html = ""
    if frame_info and live_clip_urls:
        fw, fh = frame_info["width"], frame_info["height"]
        frame_thumb = f"/frames/{frame_info['file']}"
        slots_html = ""
        for i, s in enumerate(frame_info["slots"]):
            if i >= len(live_clip_urls): break
            lp = s["x"]/fw*100; tp = s["y"]/fh*100
            wp = s["w"]/fw*100; hp = s["h"]/fh*100
            v_url = p_inline(live_clip_urls[i], f"live_{i}.webm")
            slots_html += f'<div style="position:absolute;left:{lp:.2f}%;top:{tp:.2f}%;width:{wp:.2f}%;height:{hp:.2f}%;overflow:hidden;z-index:1;"><video src="{v_url}" autoplay loop muted playsinline webkit-playsinline style="width:100%;height:100%;object-fit:cover;border-radius:0;margin:0;box-shadow:none;background:#222;"></video></div>'
        
        import json as _jsn
        slots_json = _jsn.dumps(frame_info["slots"])
        
        live_frame_html = f"""
            <div id="live-section" style="display:none">
            <h2>🎬 LIVE PHOTO <span class="live-badge">Video</span></h2>
            <div id="live-frame-container" style="position:relative;width:100%;aspect-ratio:{fw}/{fh};border-radius:16px;overflow:hidden;margin-bottom:20px;box-shadow:0 10px 20px rgba(0,0,0,0.03);background:#111;">
                <img id="live-frame-img" src="{frame_thumb}" style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:2;pointer-events:none;margin:0;border-radius:0;box-shadow:none;">
                {slots_html}
            </div>
            <button id="btn-download-live" class="btn" onclick="downloadLiveVideo()" style="margin-bottom:20px">🎥 UNDUH LIVE PHOTO</button>
            <div id="live-loading" style="display:none;font-size:0.8rem;color:#666;margin-bottom:20px;font-weight:bold">Memproses Video... (Mohon tunggu)</div>
            </div>
            
            <script>
                (function(){{
                    var sec=document.getElementById('live-section');
                    if(!sec)return;
                    var vids=document.querySelectorAll('#live-frame-container video');
                    var ok=0,fail=0,tot=vids.length;
                    if(!tot)return;
                    function chk(){{if(ok>0)sec.style.display='block';if(ok+fail>=tot&&ok===0)sec.style.display='none';}}
                    vids.forEach(function(v){{v.onloadeddata=function(){{ok++;chk();}};v.onerror=function(){{fail++;v.parentElement.style.background='#333';chk();}}}});
                    setTimeout(function(){{if(ok===0)sec.style.display='none';}},5000);
                }})();
                
                async function downloadLiveVideo() {{
                    var btn=document.getElementById('btn-download-live');
                    var loader=document.getElementById('live-loading');
                    btn.style.display='none';loader.style.display='block';
                    try {{
                        var container=document.getElementById('live-frame-container');
                        var videos=container.querySelectorAll('video');
                        var frameImg=document.getElementById('live-frame-img');
                        var ready=Array.from(videos).filter(function(v){{return v.readyState>=2;}});
                        if(ready.length===0){{alert('Video belum dimuat.');btn.style.display='flex';loader.style.display='none';return;}}
                        var maxD=2160; // Ultra HD limit
                        var rw={fw}, rh={fh};
                        if(rw>maxD || rh>maxD){{ var rat=Math.min(maxD/rw, maxD/rh); rw=Math.floor(rw*rat); rh=Math.floor(rh*rat); }}
                        var cvs=document.createElement('canvas');cvs.width=rw;cvs.height=rh;
                        var ctx=cvs.getContext('2d');
                        var scale_x = rw/{fw}, scale_y = rh/{fh};
                        await Promise.all(Array.from(videos).map(function(v){{v.currentTime=0;return v.play().catch(function(){{}});}}));
                        await new Promise(function(r){{setTimeout(r,200);}});
                        var stream=cvs.captureStream(30);
                        var mime='video/webm;codecs=vp9';
                        if(!MediaRecorder.isTypeSupported(mime))mime='video/webm';
                        if(!MediaRecorder.isTypeSupported(mime))mime='video/mp4';
                        var recorder=new MediaRecorder(stream,{{mimeType:mime}});
                        var chunks=[];
                        recorder.ondataavailable=function(e){{if(e.data.size>0)chunks.push(e.data);}};
                        var recording=true;
                        var slots={slots_json};
                        function draw(){{
                            if(!recording)return;
                            ctx.fillStyle='#fff';ctx.fillRect(0,0,cvs.width,cvs.height);
                            videos.forEach(function(v,i){{if(i<slots.length&&v.readyState>=2){{var s=slots[i];ctx.drawImage(v,s.x*scale_x,s.y*scale_y,s.w*scale_x,s.h*scale_y);}}}});
                            if(frameImg.complete)ctx.drawImage(frameImg,0,0,cvs.width,cvs.height);
                            requestAnimationFrame(draw);
                        }}
                        recorder.onstop=function(){{
                            recording=false;
                            var blob=new Blob(chunks,{{type:mime}});
                            var url=URL.createObjectURL(blob);
                            var a=document.createElement('a');a.href=url;
                            a.download='fotosphere_live.'+(mime.indexOf('mp4')>=0?'mp4':'webm');
                            document.body.appendChild(a);a.click();document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                            btn.style.display='flex';loader.style.display='none';
                        }};
                        recorder.start(100);draw();
                        // Freeze videos at the end like iPhone Live Photo
                        setTimeout(function(){{ videos.forEach(function(v){{ v.pause(); }}); }}, 2500);
                        setTimeout(function(){{recorder.stop();}},4000);
                    }} catch(err) {{
                        console.error(err);alert('Gagal: '+err.message);
                        btn.style.display='flex';loader.style.display='none';
                    }}
                }}
            </script>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Download Foto - Fotosphere</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            :root {{ --pink: #e91e63; --dark: #1a1a1a; --bg: #f8f9fa; }}
            body {{ font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg); color: var(--dark); margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 20px auto; background: #fff; border-radius: 32px; padding: 40px 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.05); text-align: center; border: 1px solid #eee; }}
            .logo {{ font-size: 1.5rem; font-weight: 800; letter-spacing: 4px; color: var(--dark); margin-bottom: 10px; }}
            .sub {{ color: #666; font-size: 0.9rem; margin-bottom: 30px; }}
            h2 {{ font-weight: 800; font-size: 1.1rem; margin-top: 40px; margin-bottom: 20px; color: var(--dark); display: flex; align-items: center; justify-content: center; gap: 10px; }}
            h2::before, h2::after {{ content: ''; flex: 1; height: 1px; background: #eee; }}
            img, video {{ max-width: 100%; border-radius: 16px; margin-bottom: 20px; background: #fdfdfd; box-shadow: 0 10px 20px rgba(0,0,0,0.03); }}
            .btn {{ display: flex; align-items: center; justify-content: center; gap: 10px; background: var(--dark); color: #fff; padding: 18px; border-radius: 20px; text-decoration: none; font-weight: 700; transition: 0.2s; margin-bottom: 15px; border: none; width: 100%; box-sizing: border-box; }}
            .btn-pink {{ background: var(--pink); }}
            .btn:active {{ transform: scale(0.96); opacity: 0.9; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
            .live-badge {{ display: inline-block; background: #fff; border: 1px solid var(--pink); color: var(--pink); padding: 4px 10px; border-radius: 50px; font-size: 0.6rem; font-weight: 800; text-transform: uppercase; margin-bottom: 10px; vertical-align: middle; }}
            .footer {{ margin-top: 40px; font-size: 0.7rem; color: #999; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">FOTOSPHERE</div>
            <div class="sub">Terima kasih telah berfoto! ✨</div>
            
            <h2>📸 HASIL STRIP</h2>
            <img src="{strip_url}" alt="Strip">
            <a href="{p(strip_url, 'fotosphere_strip.png')}" download="fotosphere_strip.png" class="btn btn-pink">UNDUH HASIL STRIP</a>

            {live_frame_html}

            <h2>✨ GIF <span class="live-badge">Bergerak</span></h2>
            <img src="{gif_url}" alt="GIF">
            <a href="{p(gif_url, 'fotosphere_live.gif')}" download="fotosphere_live.gif" class="btn">UNDUH GIF</a>

            <h2>🎞️ FOTO ORIGINAL</h2>
            <div class="grid">
                {"".join([f'<div><img src="{u}" alt="Photo {i+1}"><a href="{p(u, f"foto_{i+1}.png")}" download="foto_{i+1}.png" class="btn" style="padding: 12px; font-size: 0.8rem;">FOTO {i+1}</a></div>' for i, u in enumerate(photo_urls)])}
            </div>
            
            <div class="footer">FOTOSPHERE © 2026 • self-photobox system</div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ═══════════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════════

@app.get("/admin/login")
def admin_login_page():
    return FileResponse("private_login.html")

@app.post("/api/admin/login")
def api_admin_login(username: str = Form(...), password: str = Form(...)):
    admin_password = os.environ.get("ADMIN_PASSWORD", "fotosphere")
    if username == "admin" and password == admin_password:
        # Generate a cryptographically secure random token per login
        token = secrets.token_urlsafe(32)
        ADMIN_TOKENS.add(token)
        response = JSONResponse({"success": True})
        response.set_cookie(key="admin_token", value=token, httponly=True, samesite="lax")
        return response
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/admin/logout")
def api_admin_logout(request: Request):
    token = request.cookies.get("admin_token")
    if token and token in ADMIN_TOKENS:
        ADMIN_TOKENS.discard(token)
    response = JSONResponse({"success": True})
    response.delete_cookie("admin_token")
    return response

@app.post("/api/admin/change_password")
def api_admin_change_password(request: Request, new_password: str = Form(...), _=Depends(require_admin)):
    dotenv.set_key(".env", "ADMIN_PASSWORD", new_password)
    os.environ["ADMIN_PASSWORD"] = new_password
    return {"success": True}

@app.get("/admin")
def admin_page(request: Request):
    token = request.cookies.get("admin_token")
    if not token or token not in ADMIN_TOKENS:
        return HTMLResponse("<script>window.location.href='/admin/login'</script>")
    return FileResponse("private_admin.html")

# ─── TICKET VALIDATION ───

@app.post("/api/ticket/validate")
async def api_validate_ticket(request: Request):
    try:
        body = await request.json()
        code = body.get("code", "").strip().upper()
        log_debug(f"TICKET VALIDATE: code={code}, codes_in_memory={len(TICKET_CODES)}")

        with _claim_lock:
            if code in TICKET_CODES:
                t = TICKET_CODES[code]
                if t.get("uses_left", 0) > 0:
                    session_id = str(uuid.uuid4())
                    order_id = f"TICKET-{code}"
                    try:
                        create_session(session_id, order_id)
                    except Exception as e:
                        log_debug(f"TICKET DB ERROR: {e}")
                        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
                    
                    t["uses_left"] -= 1
                    try:
                        db_update_ticket_uses(code, t["uses_left"])
                    except Exception as e:
                        log_debug(f"TICKET UPDATE USES ERROR: {e}")
                    
                    SESSION_STORE[session_id] = {
                        "order_id": order_id, "photos": [], "frame_id": None, "mirror": False,
                        "created_at": datetime.utcnow()
                    }
                    try:
                        db_insert_payment(order_id, session_id, 0, "Ticket", "paid")
                    except Exception as e:
                        log_debug(f"TICKET PAYMENT INSERT ERROR: {e}")
                    
                    result = {"valid": True, "session_id": session_id}
                    
                    if t.get("custom_frame"):
                        try:
                            fd = find_frame_data(t["custom_frame"])
                            if fd:
                                result["custom_frame_data"] = fd
                        except Exception as e:
                            log_debug(f"TICKET FRAME LOOKUP ERROR: {e}")
                    return result

        return JSONResponse({"valid": False, "error": "Tiket tidak ditemukan atau sudah habis"}, status_code=404)
    except HTTPException:
        raise
    except Exception as e:
        log_debug(f"TICKET VALIDATE UNHANDLED ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── ADMIN: FRAMES ───
@app.get("/api/admin/frames")
def admin_list_frames(_=Depends(require_admin)):
    public_f = scan_frames_dir("static/frames")
    custom_f = scan_frames_dir("static/custom_frames")
    return public_f + custom_f

@app.post("/api/admin/frames/upload")
async def admin_upload_frame(
    request: Request,
    frame: UploadFile = File(...),
    name: str = Form(None),
    is_private: str = Form("false"),
    whatsapp: str = Form(None),
    category: str = Form("Other"),
    _=Depends(require_admin)
):
    if not frame.filename.lower().endswith(".png"):
        raise HTTPException(400, "Only PNG files allowed")
    content = await frame.read()

    # Use custom name for filename, or original
    if name:
        safe = re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip().replace(' ', '_').lower()
        fname = safe + ".png"
    else:
        fname = frame.filename

    is_private_bool = is_private.lower() == "true"
    
    # Save to the correct directory
    target_dir = "static/custom_frames" if is_private_bool else "static/frames"
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, fname)
    with open(path, 'wb') as f:
        f.write(content)

    # Detect slots
    slots = get_frame_slots(path)
    display = name.strip() if name else fname.replace('.png','').replace('_',' ').title()

    # Update JSON sidecar
    json_path = os.path.splitext(path)[0] + ".json"
    data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
        except:
            pass
    
    data["display_name"] = display
    data["is_private"] = is_private_bool
    data["category"] = category.strip() if category else "Other"
    
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)

    # Generate ticket if private
    ticket_code = None
    wa_link = None
    if is_private_bool:
        chars = string.ascii_uppercase + string.digits
        ticket_code = ''.join(random.choice(chars) for _ in range(6))
        
        # Save ticket
        TICKET_CODES[ticket_code] = {"uses_left": 1, "created_at": datetime.utcnow().isoformat(), "custom_frame": fname}
        db_upsert_ticket(ticket_code, 1, fname)
        
        if whatsapp:
            base = str(request.base_url)
            wa_num = whatsapp.strip()
            if wa_num.startswith('0'):
                wa_num = '62' + wa_num[1:]
            qr_url = f"{base}api/qr/{ticket_code}"
            text = f"Halo! Ini akses eksklusif Photobooth kamu.%0A%0ABuka link di bawah ini untuk melihat *Barcode Tiket* yang bisa di-scan ke kamera photobooth:%0A{qr_url}%0A%0A(Atau kamu juga bisa mengetik kodenya manual di menu Voucher: *{ticket_code}*)%0A%0ASelamat berfoto!"
            wa_link = f"https://wa.me/{wa_num}?text={text}"

    # Upload to Supabase Storage + DB
    try:
        if is_private_bool:
            storage_url = storage_upload_custom_frame(fname, content)
            db_upsert_custom_frame(fname, display, slots, storage_url)
        else:
            storage_url = storage_upload_frame(fname, content)
            db_upsert_frame(fname, display, slots, storage_url)
    except Exception as e:
        print(f"Supabase upload warning: {e}")

    return {
        "success": True, 
        "name": display, 
        "slots_detected": len(slots),
        "is_private": is_private_bool,
        "ticket_code": ticket_code,
        "wa_link": wa_link
    }


@app.put("/api/admin/frames/{filename}")
async def admin_edit_frame(filename: str, request: Request, _=Depends(require_admin)):
    """Edit frame metadata (name, category) without re-uploading the file."""
    body = await request.json()
    new_name = body.get("name", "").strip()
    new_category = body.get("category", "").strip() or "Other"

    if not new_name:
        raise HTTPException(400, "Name is required")

    updated = False
    for t_dir in ["static/frames", "static/custom_frames"]:
        path = os.path.join(t_dir, filename)
        if os.path.exists(path):
            json_path = os.path.splitext(path)[0] + ".json"
            data = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                except:
                    pass
            data["display_name"] = new_name
            data["category"] = new_category
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            updated = True

            # Also update Supabase DB
            is_private = data.get("is_private", False)
            try:
                if is_private or t_dir == "static/custom_frames":
                    db_upsert_custom_frame(filename, new_name, data.get("slots", []), "")
                else:
                    db_upsert_frame(filename, new_name, data.get("slots", []), "")
            except Exception as e:
                print(f"Supabase frame update warning: {e}")
            break

    if not updated:
        raise HTTPException(404, "Frame not found")

    # Invalidate thumb cache for this frame
    if filename in _thumb_cache:
        del _thumb_cache[filename]

    return {"success": True, "name": new_name, "category": new_category}

@app.delete("/api/admin/frames/{filename}")
def admin_delete_frame(filename: str, _=Depends(require_admin)):
    # Try deleting from both directories
    for t_dir in ["static/frames", "static/custom_frames"]:
        path = os.path.join(t_dir, filename)
        if os.path.exists(path):
            os.remove(path)
            json_path = os.path.splitext(path)[0] + ".json"
            if os.path.exists(json_path):
                os.remove(json_path)
    # Delete from Supabase (both tables just to be sure)
    try:
        db_delete_frame(filename)
        db_delete_custom_frame(filename)
    except Exception as e:
        print(f"Supabase frame delete error: {e}")
    return {"success": True}

# ─── ADMIN: PAYMENTS & PHOTOS ───
@app.get("/api/admin/payments")
def admin_payments(_=Depends(require_admin)):
    return db_get_all_payments(500)

@app.get("/api/admin/photos")
def admin_photos(sync: bool = False, _=Depends(require_admin)):
    return db_get_photo_history(100)

# ─── ADMIN: VOUCHERS ───
@app.get("/api/admin/vouchers")
def admin_vouchers(_=Depends(require_admin)):
    global VOUCHER_CODES
    VOUCHER_CODES = sync_vouchers_from_db()
    return VOUCHER_CODES

@app.post("/api/admin/vouchers")
async def admin_create_voucher(request: Request, _=Depends(require_admin)):
    body = await request.json()
    code = body.get("code", "").strip().upper()
    uses = body.get("uses", 1)
    custom_frame = body.get("custom_frame") or None
    if not code:
        raise HTTPException(400, "Code required")
    VOUCHER_CODES[code] = {"uses_left": uses, "created_at": datetime.utcnow().isoformat(), "custom_frame": custom_frame}
    db_upsert_voucher(code, uses, custom_frame)
    return {"success": True, "code": code, "uses": uses}

@app.post("/api/admin/vouchers/generate")
async def admin_generate_voucher(request: Request, _=Depends(require_admin)):
    """Generate a unique random voucher code."""
    body = await request.json()
    uses = body.get("uses", 1)
    custom_frame = body.get("custom_frame") or None
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if code not in VOUCHER_CODES:
            break
    VOUCHER_CODES[code] = {"uses_left": uses, "created_at": datetime.utcnow().isoformat(), "custom_frame": custom_frame}
    db_upsert_voucher(code, uses, custom_frame)
    return {"success": True, "code": code, "uses": uses}

@app.delete("/api/admin/vouchers/{code}")
def admin_delete_voucher(code: str, _=Depends(require_admin)):
    code = code.upper()
    if code in VOUCHER_CODES:
        del VOUCHER_CODES[code]
    db_delete_voucher(code)
    return {"success": True}

# ─── ADMIN: TICKETS ───
@app.get("/api/admin/tickets")
def admin_tickets(_=Depends(require_admin)):
    global TICKET_CODES
    TICKET_CODES = sync_tickets_from_db()
    return TICKET_CODES

@app.post("/api/admin/tickets")
async def admin_create_ticket(request: Request, _=Depends(require_admin)):
    body = await request.json()
    code = body.get("code", "").strip().upper()
    uses = body.get("uses", 1)
    custom_frame = body.get("custom_frame") or None
    if not code:
        raise HTTPException(400, "Code required")
    TICKET_CODES[code] = {"uses_left": uses, "created_at": datetime.utcnow().isoformat(), "custom_frame": custom_frame}
    db_upsert_ticket(code, uses, custom_frame)
    return {"success": True, "code": code, "uses": uses}

@app.post("/api/admin/tickets/generate")
async def admin_generate_ticket(request: Request, _=Depends(require_admin)):
    body = await request.json()
    uses = body.get("uses", 1)
    custom_frame = body.get("custom_frame") or None
    while True:
        code = ''.join(random.choices(string.digits, k=12))
        if code not in TICKET_CODES:
            break
    TICKET_CODES[code] = {"uses_left": uses, "created_at": datetime.utcnow().isoformat(), "custom_frame": custom_frame}
    db_upsert_ticket(code, uses, custom_frame)
    return {"success": True, "code": code, "uses": uses}

@app.delete("/api/admin/tickets/{code}")
def admin_delete_ticket(code: str, _=Depends(require_admin)):
    code = code.upper()
    if code in TICKET_CODES:
        del TICKET_CODES[code]
    db_delete_ticket(code)
    return {"success": True}

@app.get("/api/admin/debug-log")
def admin_view_debug_log(_=Depends(require_admin)):
    if os.path.exists("static/debug.log"):
        with open("static/debug.log", "r") as f:
            return Response(content=f.read(), media_type="text/plain")
    return Response(content="No log found", media_type="text/plain")

# Serve static (LAST)
app.mount("/custom_frames", StaticFiles(directory="static/custom_frames"), name="custom_frames")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8502))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

