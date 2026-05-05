"""style.py — Shared CSS landscape kiosk style"""

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');

:root {
    --bg:     #f8f8f8;
    --card:   #ffffff;
    --pink:   #ff4d8d;
    --pink-l: #ffb3ce;
    --pink-d: #e0005a;
    --gray:   #4a4a5a;
    --muted:  #9a9aaa;
    --border: #e8e8f0;
    --shadow: 0 6px 30px rgba(0,0,0,0.08);
}

*, html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--gray) !important;
    font-family: 'Nunito', sans-serif !important;
}

.stApp {
    background: var(--bg) !important;
    min-height: 100vh;
}

/* Sembunyiin semua elemen Streamlit yang tidak perlu */
#MainMenu,
footer,
header,
header[data-testid="stHeader"],
.stDeployButton,
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
section[data-testid="stSidebarNav"] {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
}

.block-container {
    padding: 1.5rem 2rem !important;
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* Primary button */
.stButton > button {
    background: linear-gradient(135deg, var(--pink), var(--pink-d)) !important;
    color: white !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Nunito', sans-serif !important;
    font-size: 1.1rem !important;
    font-weight: 900 !important;
    letter-spacing: 1px !important;
    padding: 0.85rem 2rem !important;
    width: 100% !important;
    box-shadow: 0 6px 20px rgba(255,77,141,0.4) !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 10px 30px rgba(255,77,141,0.55) !important;
}

/* Ghost button */
.btn-ghost > button {
    background: white !important;
    color: var(--muted) !important;
    border: 2px solid var(--border) !important;
    box-shadow: none !important;
    font-size: 0.9rem !important;
    font-weight: 700 !important;
    padding: 0.6rem !important;
}
.btn-ghost > button:hover {
    color: var(--pink) !important;
    border-color: var(--pink-l) !important;
    transform: none !important;
    box-shadow: none !important;
}

/* Selected button */
.btn-sel > button {
    background: #fff0f5 !important;
    color: var(--pink) !important;
    border: 2px solid var(--pink-l) !important;
    box-shadow: none !important;
    transform: none !important;
}

/* Card */
.card {
    background: white;
    border-radius: 24px;
    padding: 1.5rem;
    box-shadow: var(--shadow);
    border: 1.5px solid var(--border);
}

.divider { border: none; border-top: 1.5px solid var(--border); margin: 1.2rem 0; }
</style>
"""

def step_bar(current: int):
    steps = [("💳","Bayar"),("🎨","Frame"),("📸","Foto"),("✨","Filter"),("⬇️","Unduh")]
    html = '<div style="display:flex; justify-content:center; align-items:center; gap:0; margin-bottom:1.5rem;">'
    for i, (icon, label) in enumerate(steps):
        n = i + 1
        if n < current:
            bg, color, border = "#ff4d8d", "white", "#ff4d8d"
            txt = "✓"
        elif n == current:
            bg, color, border = "#ff4d8d", "white", "#ff4d8d"
            txt = icon
        else:
            bg, color, border = "white", "#9a9aaa", "#e8e8f0"
            txt = icon

        html += f'''
        <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
            <div style="width:40px; height:40px; border-radius:50%; background:{bg}; border:2px solid {border};
                display:flex; align-items:center; justify-content:center; font-size:1rem;
                color:{color}; font-weight:900; box-shadow:{"0 4px 12px rgba(255,77,141,0.3)" if n==current else "none"};">
                {txt}
            </div>
            <span style="font-size:0.6rem; font-weight:800; color:{"#ff4d8d" if n==current else "#9a9aaa"}; letter-spacing:1px;">{label}</span>
        </div>
        '''
        if i < len(steps)-1:
            html += f'<div style="flex:1; height:2px; background:{"#ffb3ce" if n < current else "#e8e8f0"}; max-width:50px; margin-bottom:16px;"></div>'
    html += '</div>'
    return html