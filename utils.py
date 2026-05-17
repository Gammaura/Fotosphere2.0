"""
utils.py — PNG Frame system: detect transparent slots + composite photos
"""
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps
import numpy as np
import io, os, math

# ── Font helpers ──────────────────────────────────────────
def _font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

# ── Filters ───────────────────────────────────────────────
FILTERS = {
    "Original": lambda i: i,
    "Natural":  lambda i: i,
    "Soft":     lambda i: ImageEnhance.Contrast(i).enhance(0.85),
    "Warm":     lambda i: _warm(i),
    "Cold":     lambda i: _cool(i),
    "B&W":      lambda i: ImageOps.grayscale(i).convert("RGB"),
    "Vintage":  lambda i: _vintage(i),
    "Vivid":    lambda i: ImageEnhance.Contrast(ImageEnhance.Color(i).enhance(1.9)).enhance(1.2),
    "Faded":    lambda i: ImageEnhance.Brightness(ImageEnhance.Color(ImageEnhance.Contrast(i).enhance(0.7)).enhance(0.6)).enhance(1.1),
    "Dreamy":   lambda i: ImageEnhance.Brightness(ImageEnhance.Contrast(i).enhance(0.75)).enhance(1.15),
    "Rose":     lambda i: _rose(i),
    "Sunset":   lambda i: _sunset(i),
    "Cinematic":lambda i: _cinematic(i),
    "Polaroid": lambda i: _polaroid(i),
    "Sepia":    lambda i: _sepia(i),
}

def _warm(img):
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.18)))
    g = g.point(lambda x: min(255, int(x * 1.05)))
    b = b.point(lambda x: int(x * 0.85))
    return Image.merge("RGB", (r, g, b))

def _cool(img):
    r, g, b = img.split()
    r = r.point(lambda x: int(x * 0.88))
    b = b.point(lambda x: min(255, int(x * 1.18)))
    return Image.merge("RGB", (r, g, b))

def _vintage(img):
    img = ImageOps.grayscale(img).convert("RGB")
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.12)))
    b = b.point(lambda x: int(x * 0.88))
    return ImageEnhance.Contrast(Image.merge("RGB", (r, g, b))).enhance(0.88)

def _rose(img):
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.15)))
    g = g.point(lambda x: int(x * 0.92))
    b = b.point(lambda x: min(255, int(x * 1.08)))
    return ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(1.05)

def _sunset(img):
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.25)))
    g = g.point(lambda x: min(255, int(x * 1.05)))
    b = b.point(lambda x: int(x * 0.75))
    return ImageEnhance.Contrast(Image.merge("RGB", (r, g, b))).enhance(1.1)

def _cinematic(img):
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Color(img).enhance(0.8)
    r, g, b = img.split()
    b = b.point(lambda x: min(255, int(x * 1.1)))
    return ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(0.9)

def _polaroid(img):
    img = ImageEnhance.Contrast(img).enhance(0.9)
    img = ImageEnhance.Brightness(img).enhance(1.1)
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.05)))
    g = g.point(lambda x: min(255, int(x * 1.02)))
    return Image.merge("RGB", (r, g, b))

def _sepia(img):
    img = ImageOps.grayscale(img).convert("RGB")
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.2)))
    g = g.point(lambda x: min(255, int(x * 1.0)))
    b = b.point(lambda x: int(x * 0.8))
    return Image.merge("RGB", (r, g, b))

def apply_filter(img: Image.Image, name: str) -> Image.Image:
    fn = FILTERS.get(name, lambda i: i)
    return fn(img.convert("RGB"))

# ═══════════════════════════════════════════════════════════
# PNG FRAME SYSTEM
# ═══════════════════════════════════════════════════════════

def detect_transparent_slots(png_path: str, min_area: int = 5000) -> list:
    """
    Detect transparent rectangular regions in a PNG frame.
    Returns list of dicts: [{"x": int, "y": int, "w": int, "h": int}, ...]
    sorted top-to-bottom, left-to-right.
    """
    try:
        import cv2
        img_cv = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
        if img_cv is not None and len(img_cv.shape) == 3 and img_cv.shape[2] == 4:
            alpha = img_cv[:, :, 3]
            _, mask = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            slots = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                # Ignore tiny slivers or noise (minimum 300x300 for a valid photo slot)
                if w >= 300 and h >= 300:
                    slots.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
            slots.sort(key=lambda s: (s["y"], s["x"]))
            
            # Filter out nested/overlapping slots (e.g. shadow + main box)
            # We keep the larger outer box
            final_slots = []
            # Sort by area descending to process larger boxes first
            sorted_by_area = sorted(slots, key=lambda s: s['w'] * s['h'], reverse=True)
            for s in sorted_by_area:
                is_nested = False
                for f in final_slots:
                    # Check if s is substantially inside f
                    if (s['x'] >= f['x'] - 20 and s['y'] >= f['y'] - 20 and 
                        s['x'] + s['w'] <= f['x'] + f['w'] + 20 and 
                        s['y'] + s['h'] <= f['y'] + f['h'] + 20):
                        is_nested = True
                        break
                if not is_nested:
                    final_slots.append(s)
            
            final_slots.sort(key=lambda s: (s["y"], s["x"]))
            return final_slots
    except Exception as e:
        print(f"OpenCV slot detection failed, falling back to PIL BFS: {e}")

    img = Image.open(png_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]  # alpha channel
    
    # Binary mask: True where fully transparent (alpha < 10)
    mask = alpha < 10
    
    # Label connected components using simple flood-fill approach
    visited = np.zeros_like(mask, dtype=bool)
    slots = []
    
    h, w = mask.shape
    
    def flood_fill_bbox(start_y, start_x):
        """BFS flood fill, return bounding box of connected transparent region."""
        from collections import deque
        queue = deque([(start_y, start_x)])
        visited[start_y, start_x] = True
        min_x, max_x = start_x, start_x
        min_y, max_y = start_y, start_y
        count = 0
        
        while queue:
            cy, cx = queue.popleft()
            count += 1
            min_x = min(min_x, cx)
            max_x = max(max_x, cx)
            min_y = min(min_y, cy)
            max_y = max(max_y, cy)
            
            # Check 4-connected neighbors (with step for speed)
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = cy+dy, cx+dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and mask[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        
        return {"x": int(min_x), "y": int(min_y), 
                "w": int(max_x - min_x + 1), "h": int(max_y - min_y + 1),
                "area": count}
    
    # Scan for transparent regions (sample every 4 pixels for speed)
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            if mask[y, x] and not visited[y, x]:
                bbox = flood_fill_bbox(y, x)
                if bbox["area"] >= min_area:
                    slots.append(bbox)
    
    # Sort: top-to-bottom, then left-to-right
    slots.sort(key=lambda s: (s["y"], s["x"]))
    
    # Remove 'area' key from output
    for s in slots:
        del s["area"]
    
    return slots

def get_frame_slots(png_path: str) -> list:
    import json as _json
    from PIL import Image as _Img
    json_path = os.path.splitext(png_path)[0] + ".json"
    
    slots = None
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as jf:
                data = _json.load(jf)
                if "slots" in data and data["slots"]:
                    slots = data["slots"]
        except:
            pass
            
    # Auto-detect if not in JSON or JSON is invalid
    if not slots:
        slots = detect_transparent_slots(png_path)
        if slots:
            data = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as jf:
                        data = _json.load(jf)
                except:
                    pass
            data["slots"] = slots
            try:
                with open(json_path, 'w') as jf:
                    _json.dump(data, jf, indent=2)
            except Exception as e:
                print(f"Failed to save slots to {json_path}: {e}")
    
    if not slots:
        return []
    
    # Normalize slot coordinates to match actual image dimensions
    try:
        with _Img.open(png_path) as img:
            fw, fh = img.size
        max_sx = max(s["x"] + s["w"] for s in slots)
        max_sy = max(s["y"] + s["h"] for s in slots)
        if max_sx > fw * 1.05 or max_sy > fh * 1.05:
            # Use SINGLE uniform scale to preserve aspect ratio
            # min() ensures no slot overflows the image bounds
            sc = min(fw / max_sx if max_sx > fw else 1.0,
                     fh / max_sy if max_sy > fh else 1.0)
            slots = [{"x": int(s["x"]*sc), "y": int(s["y"]*sc),
                      "w": int(s["w"]*sc), "h": int(s["h"]*sc)} for s in slots]
        
        # Sort slots top-to-bottom, left-to-right
        row_height = fh / max(1, len(set(s["y"] for s in slots)))
        slots.sort(key=lambda s: (s["y"] // max(1, int(row_height * 0.5)), s["x"]))
    except:
        pass
    
    return slots


def composite_photos_on_frame(frame_path: str, photos: list, slots: list, 
                                filter_name: str = "Natural", max_width: int = 1800) -> Image.Image:
    """
    Composite photos onto a PNG frame template.
    Photos are placed BEHIND the frame so the frame decorations cover edges.
    """
    frame = Image.open(frame_path).convert("RGBA")
    fw, fh = frame.size
    
    # Memory Optimization: Limit internal resolution to prevent OOM
    scale = 1.0
    if fw > max_width:
        scale = max_width / fw
        fw = max_width
        fh = int(frame.height * scale)
        frame = frame.resize((fw, fh), Image.LANCZOS)
    
    # Create base canvas
    canvas = Image.new("RGBA", (fw, fh), (255, 255, 255, 255))
    
    # Place each photo in its slot
    for i, slot in enumerate(slots):
        if i >= len(photos) or photos[i] is None:
            continue
        
        photo = photos[i].convert("RGB")
        photo = apply_filter(photo, filter_name)
        
        # Scale slot coordinates based on frame resizing
        sx = int(slot["x"] * scale)
        sy = int(slot["y"] * scale)
        sw = int(slot["w"] * scale)
        sh = int(slot["h"] * scale)
        
        # Add bleed (overscan) to eliminate white edge gaps from rounding
        bleed = 3
        bx = max(0, sx - bleed)
        by = max(0, sy - bleed)
        bw = min(fw - bx, sw + bleed * 2)
        bh = min(fh - by, sh + bleed * 2)
        
        # Cover-crop: resize photo to fill slot while maintaining aspect ratio
        pw, ph = photo.size
        p_scale = max(bw / pw, bh / ph)
        new_w = int(pw * p_scale)
        new_h = int(ph * p_scale)
        photo = photo.resize((new_w, new_h), Image.LANCZOS)
        
        # Center crop
        left = (new_w - bw) // 2
        top = (new_h - bh) // 2
        photo = photo.crop((left, top, left + bw, top + bh))
        
        canvas.paste(photo, (bx, by))
    
    # Paste frame on top (frame has transparency where photos show through)
    canvas = Image.alpha_composite(canvas, frame)
    
    return canvas.convert("RGB")


def scan_frames_dir(frames_dir: str = "static/frames") -> list:
    """
    Scan frames directory and return metadata for each frame.
    Supports JSON sidecar: if 'myframe.json' exists alongside 'myframe.png',
    the slots defined in the JSON will be used instead of auto-detection.
    JSON format: {"slots": [{"x":50,"y":100,"w":400,"h":300}, ...]}
    """
    import json as _json
    frames = []
    if not os.path.exists(frames_dir):
        return frames
    
    for fname in sorted(os.listdir(frames_dir)):
        if not fname.lower().endswith(".png"):
            continue
        
        fpath = os.path.join(frames_dir, fname)
        base = os.path.splitext(fname)[0]
        json_path = os.path.join(frames_dir, base + ".json")
        
        try:
            name = base.replace("_", " ").title()
            
            # get_frame_slots handles loading from JSON or auto-detecting and saving to JSON
            slots = get_frame_slots(fpath)
            
            is_private = False
            category = "Other"
            # Load display name if present in JSON
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as jf:
                        jdata = _json.load(jf)
                    if "display_name" in jdata:
                        name = jdata["display_name"]
                    is_private = jdata.get("is_private", False)
                    category = jdata.get("category", "Other")
                except:
                    pass
            
            if not slots:
                continue
            
            with Image.open(fpath) as img:
                fw, fh = img.size
            
            n_photos = len(slots)
            layout = "grid" if n_photos > 4 else "strip"
            
            frames.append({
                "id": fname,
                "name": name,
                "file": fname,
                "photos": n_photos,
                "layout": layout,
                "width": fw,
                "height": fh,
                "slots": slots,
                "is_private": is_private,
                "category": category,
            })
        except Exception as e:
            print(f"Error scanning frame {fname}: {e}")
    
    return frames


def pil_to_bytes(img: Image.Image, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()

def mirror_image(img: Image.Image) -> Image.Image:
    return ImageOps.mirror(img)