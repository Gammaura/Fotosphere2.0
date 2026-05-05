"""
generate_frames.py — Generate starter PNG frame templates
Each frame has transparent rectangular areas that become photo slots.
"""
from PIL import Image, ImageDraw, ImageFont
import os, math

W, H = 1080, 1920
FRAMES_DIR = "static/frames"

def _font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

def _font_r(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def draw_gradient(draw, w, h, c1, c2):
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    for y in range(h):
        t = y / h
        r = int(r1*(1-t) + r2*t)
        g = int(g1*(1-t) + g2*t)
        b = int(b1*(1-t) + b2*t)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

def draw_stars(draw, n, area, color, sizes=(4,8)):
    import random
    random.seed(42)
    x1, y1, x2, y2 = area
    for _ in range(n):
        x = random.randint(x1, x2)
        y = random.randint(y1, y2)
        s = random.randint(sizes[0], sizes[1])
        # 4-point star
        pts = []
        for i in range(8):
            angle = math.pi * i / 4 - math.pi / 2
            radius = s if i % 2 == 0 else s * 0.4
            pts.append((x + radius * math.cos(angle), y + radius * math.sin(angle)))
        draw.polygon(pts, fill=color)

def draw_dots(draw, n, area, color, r=3):
    import random
    random.seed(123)
    x1, y1, x2, y2 = area
    for _ in range(n):
        x = random.randint(x1, x2)
        y = random.randint(y1, y2)
        draw.ellipse([(x-r, y-r), (x+r, y+r)], fill=color)

def make_strip_frame(name, bg1, bg2, accent, accent2, deco_color):
    """3-photo vertical strip frame"""
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    
    # Background gradient
    draw_gradient(draw, W, H, bg1, bg2)
    
    # Top/bottom accent bars
    draw.rectangle([(0,0),(W,12)], fill=hex_to_rgb(accent)+(255,))
    draw.rectangle([(0,H-12),(W,H)], fill=hex_to_rgb(accent)+(255,))
    
    # Decorations
    draw_stars(draw, 15, (20, 20, W-20, 160), hex_to_rgb(deco_color)+(180,))
    draw_stars(draw, 10, (20, H-200, W-20, H-30), hex_to_rgb(deco_color)+(150,))
    draw_dots(draw, 25, (20, 160, W-20, H-200), hex_to_rgb(deco_color)+(80,), r=4)
    
    # Header text
    f_big = _font(52)
    f_sm = _font_r(24)
    txt = "FOTOSPHERE"
    bb = draw.textbbox((0,0), txt, font=f_big)
    tw = bb[2]-bb[0]
    draw.text(((W-tw)//2, 40), txt, fill=hex_to_rgb(accent)+(255,), font=f_big)
    
    sub = "✦  self photo studio  ✦"
    bb2 = draw.textbbox((0,0), sub, font=f_sm)
    tw2 = bb2[2]-bb2[0]
    draw.text(((W-tw2)//2, 100), sub, fill=hex_to_rgb(accent2)+(255,), font=f_sm)
    
    # 3 transparent photo slots
    PAD = 50
    TOP = 160
    BOT = H - 120
    GAP = 24
    slot_w = W - 2*PAD
    slot_h = (BOT - TOP - 2*GAP) // 3
    RADIUS = 20
    
    for i in range(3):
        y = TOP + i * (slot_h + GAP)
        # Cut transparent hole with rounded corners
        # First draw a white border/shadow
        draw.rounded_rectangle([(PAD-4, y-4), (PAD+slot_w+4, y+slot_h+4)], 
                              radius=RADIUS+2, fill=(255,255,255,60))
        # Then clear the slot area to transparent
        mask = Image.new("L", (slot_w, slot_h), 255)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([(0,0),(slot_w,slot_h)], radius=RADIUS, fill=0)
        # We need to make the slot area transparent
        # Set alpha to 0 in slot area
        for py in range(slot_h):
            for px in range(slot_w):
                if mask.getpixel((px, py)) == 0:
                    img.putpixel((PAD + px, y + py), (0, 0, 0, 0))
    
    # Footer
    ft = "fotosphere.id"
    bb3 = draw.textbbox((0,0), ft, font=f_sm)
    tw3 = bb3[2]-bb3[0]
    draw.text(((W-tw3)//2, H-80), ft, fill=hex_to_rgb(accent)+(220,), font=f_sm)
    
    # Date placeholder
    f_xs = _font_r(18)
    draw.text(((W-200)//2, H-50), "@fotosphere", fill=hex_to_rgb(accent2)+(180,), font=f_xs)
    
    img.save(os.path.join(FRAMES_DIR, name + ".png"))
    print(f"  ✅ {name}.png ({W}x{H})")


def make_grid_frame(name, bg1, bg2, accent, accent2, deco_color):
    """6-photo 2x3 grid frame"""
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    
    draw_gradient(draw, W, H, bg1, bg2)
    
    draw.rectangle([(0,0),(W,12)], fill=hex_to_rgb(accent)+(255,))
    draw.rectangle([(0,H-12),(W,H)], fill=hex_to_rgb(accent)+(255,))
    
    draw_stars(draw, 12, (20, 20, W-20, 150), hex_to_rgb(deco_color)+(180,))
    draw_dots(draw, 20, (20, H-180, W-20, H-30), hex_to_rgb(deco_color)+(100,), r=5)
    
    f_big = _font(48)
    f_sm = _font_r(22)
    txt = "FOTOSPHERE"
    bb = draw.textbbox((0,0), txt, font=f_big)
    draw.text(((W-(bb[2]-bb[0]))//2, 35), txt, fill=hex_to_rgb(accent)+(255,), font=f_big)
    sub = "✦  self photo studio  ✦"
    bb2 = draw.textbbox((0,0), sub, font=f_sm)
    draw.text(((W-(bb2[2]-bb2[0]))//2, 90), sub, fill=hex_to_rgb(accent2)+(255,), font=f_sm)
    
    # 6 slots in 2x3 grid
    PAD = 40
    TOP = 140
    BOT = H - 110
    GAPX = 20
    GAPY = 20
    RADIUS = 16
    cols, rows = 2, 3
    slot_w = (W - 2*PAD - (cols-1)*GAPX) // cols
    slot_h = (BOT - TOP - (rows-1)*GAPY) // rows
    
    for idx in range(6):
        col = idx % cols
        row = idx // cols
        x = PAD + col * (slot_w + GAPX)
        y = TOP + row * (slot_h + GAPY)
        
        # White border
        draw.rounded_rectangle([(x-3, y-3), (x+slot_w+3, y+slot_h+3)],
                              radius=RADIUS+2, fill=(255,255,255,60))
        # Clear to transparent
        mask = Image.new("L", (slot_w, slot_h), 255)
        ImageDraw.Draw(mask).rounded_rectangle([(0,0),(slot_w,slot_h)], radius=RADIUS, fill=0)
        for py in range(slot_h):
            for px in range(slot_w):
                if mask.getpixel((px, py)) == 0:
                    img.putpixel((x + px, y + py), (0, 0, 0, 0))
    
    # Footer
    ft = "fotosphere.id"
    bb3 = draw.textbbox((0,0), ft, font=f_sm)
    draw.text(((W-(bb3[2]-bb3[0]))//2, H-75), ft, fill=hex_to_rgb(accent)+(220,), font=f_sm)
    f_xs = _font_r(18)
    draw.text(((W-200)//2, H-45), "@fotosphere", fill=hex_to_rgb(accent2)+(180,), font=f_xs)
    
    img.save(os.path.join(FRAMES_DIR, name + ".png"))
    print(f"  ✅ {name}.png ({W}x{H})")


if __name__ == "__main__":
    os.makedirs(FRAMES_DIR, exist_ok=True)
    print("Generating frames...")
    
    # 4 strip frames (3 photos)
    make_strip_frame("aura_pink",    "#ff6eb4","#ffe0f0", "#ff4d8d","#ffb3ce", "#ff8ab5")
    make_strip_frame("noir_film",    "#1a1a1a","#2e2e2e", "#ffffff","#888888", "#555555")
    make_strip_frame("golden_hour",  "#ff9a3c","#ffe4a0", "#e67e00","#ffd166", "#ffb347")
    make_strip_frame("lavender_dream","#a78bfa","#ede9fe", "#7c3aed","#c4b5fd", "#a78bfa")
    
    # 2 grid frames (6 photos)
    make_grid_frame("mint_fresh",    "#34d399","#d1fae5", "#059669","#a7f3d0", "#6ee7b7")
    make_grid_frame("sky_blue",      "#38bdf8","#e0f2fe", "#0284c7","#bae6fd", "#7dd3fc")
    
    print("\nDone! All frames saved to", FRAMES_DIR)
