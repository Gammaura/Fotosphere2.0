import os
import sys
import json
from PIL import Image
sys.path.append(os.getcwd())
from utils import detect_transparent_slots

frames_dir = "static/frames"
frame_names = ["Barbie", "Sea", "Space"]

for name in frame_names:
    png_path = os.path.join(frames_dir, f"{name}.png")
    json_path = os.path.join(frames_dir, f"{name}.json")
    
    if os.path.exists(png_path):
        print(f"Processing {name}...")
        with Image.open(png_path) as img:
            w, h = img.size
            print(f"  Resolution: {w}x{h}")
        
        slots = detect_transparent_slots(png_path)
        if slots:
            print(f"  Detected {len(slots)} slots.")
            
            # Preserve display_name if it exists
            data = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                except:
                    pass
            
            data["slots"] = slots
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"  Updated {json_path}")
        else:
            print(f"  No slots detected for {name}!")
    else:
        print(f"  {png_path} not found.")
