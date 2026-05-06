/* ═══════════════════════════════════════════════════════════
   Fotosphere — App v8 — Real barcode scan, virtual keyboard,
   invoice overlay, empty frame dummies, retake per slot
   ═══════════════════════════════════════════════════════════ */
const S = {
    sid: null, oid: null,
    frames: [], filters: [],
    frame: null, filter: 'Natural',
    photos: [], max: 1, slot: 0,
    mirror: false, stream: null,
};
const $ = id => document.getElementById(id);
const show = id => { document.querySelectorAll('.screen').forEach(s => s.classList.remove('active')); $('screen-' + id).classList.add('active'); };
function loader(m) { $('loader-msg').textContent = m || 'MEMPROSES...'; $('loader').style.display = 'flex'; }
function noloader() { $('loader').style.display = 'none'; }

// ─── SUCCESS WITH INVOICE ───
function showSuccess(text, sub, invoice, cb) {
    $('success-text').textContent = text;
    $('success-sub').textContent = sub || 'Terima Kasih';
    const box = $('invoice-box');
    if (invoice) {
        $('inv-method').textContent = invoice.method || '-';
        $('inv-order').textContent = invoice.order || '-';
        $('inv-total').textContent = invoice.total || '-';
        box.style.display = 'block';
    } else {
        box.style.display = 'none';
    }
    $('success-overlay').style.display = 'flex';
    setTimeout(() => { $('success-overlay').style.display = 'none'; if (cb) cb(); }, 3000);
}

// ─── VIRTUAL KEYBOARD ───
function vkType(ch) {
    const inp = $('voucher-input');
    inp.value += ch;
}
function vkDel() {
    const inp = $('voucher-input');
    inp.value = inp.value.slice(0, -1);
}

// ─── INIT ───
async function init() {
    try { const r = await fetch('/api/config'); const d = await r.json(); S.frames = d.frames; S.filters = d.filters; } catch (e) { console.error(e); }
}
init();

// ─── SESSION TIMER ───
let _sT = null, _sL = 600;
function startTimer() {
    _sL = 600; updTimers();
    if (_sT) clearInterval(_sT);
    _sT = setInterval(() => { _sL--; updTimers(); if (_sL <= 0) { clearInterval(_sT); goHome(); alert('Sesi habis!'); } }, 1000);
}
function stopTimer() { if (_sT) { clearInterval(_sT); _sT = null; } }
function updTimers() {
    const t = `${String(Math.floor(_sL / 60)).padStart(2, '0')}.${String(_sL % 60).padStart(2, '0')}`;
    ['frame-timer', 'shoot-timer', 'filter-timer'].forEach(id => { const e = $(id); if (e) e.textContent = t; });
}

// ═══════════ HOME ═══════════
function goHome() {
    stopCam(); stopTimer(); clearPay(); stopTicketScan();
    S.sid = null; S.oid = null; S.frame = null; S.filter = 'Natural'; S.photos = []; S.slot = 0;
    const ov = $('emoji-overlay'); if (ov) ov.innerHTML = '';
    show('home');
}

// ═══════════ PAYMENT METHOD ═══════════
function goPaymentMethod() { stopCam(); clearPay(); show('paymethod'); }

// ═══════════════════════════════════════════════════════════
// SCAN TICKET — real barcode scanning with html5-qrcode
// ═══════════════════════════════════════════════════════════
let _scanner = null;
let _scanProcessing = false;

async function goScanTicket() {
    show('ticket');
    _scanProcessing = false;

    try {
        _scanner = new Html5Qrcode("ticket-reader");
        await _scanner.start(
            { facingMode: "environment" },
            { fps: 10, qrbox: { width: 220, height: 220 } },
            async (decodedText) => {
                if (_scanProcessing) return;
                _scanProcessing = true;

                // Validate ticket code against backend
                try {
                    const r = await fetch('/api/ticket/validate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code: decodedText })
                    });
                    const d = await r.json();

                    if (d.valid) {
                        S.sid = d.session_id;
                        stopTicketScan();
                        showSuccess('Scan Ticket Berhasil', 'Terima Kasih', {
                            method: 'Ticket',
                            order: `TICKET-${decodedText}`,
                            total: 'GRATIS (Ticket)'
                        }, () => { startTimer(); goToFrame(); });
                    } else {
                        _scanProcessing = false;
                        // Brief visual feedback for invalid
                        $('success-text').textContent = 'Ticket Tidak Valid';
                        $('success-sub').textContent = 'Coba scan ulang';
                        $('success-overlay').querySelector('.successIcon').textContent = '❌';
                        $('invoice-box').style.display = 'none';
                        $('success-overlay').style.display = 'flex';
                        setTimeout(() => {
                            $('success-overlay').style.display = 'none';
                            $('success-overlay').querySelector('.successIcon').textContent = '✅';
                        }, 1500);
                    }
                } catch (e) {
                    _scanProcessing = false;
                    console.error('Ticket validation error:', e);
                }
            },
            () => { } // ignore errors (no QR found yet)
        );
    } catch (e) {
        console.error('Scanner start error:', e);
    }
}

function stopTicketScan() {
    if (_scanner) {
        try { _scanner.stop().catch(() => { }); } catch (_) { }
        try { _scanner.clear(); } catch (_) { }
        _scanner = null;
    }
}

// ═══════════════════════════════════════════════════════════
// QRIS
// ═══════════════════════════════════════════════════════════
let _pT = null, _pP = null;
function clearPay() { if (_pT) { clearInterval(_pT); _pT = null; } if (_pP) { clearInterval(_pP); _pP = null; } }

async function goQRIS() {
    loader('MEMPERSIAPKAN PEMBAYARAN...');
    try {
        const r = await fetch('/api/payment/create', { method: 'POST' });
        if (!r.ok) throw new Error('Server error');
        const d = await r.json();
        S.sid = d.session_id; S.oid = d.order_id;
        $('qr-box').innerHTML = `<img src="data:image/png;base64,${d.qr_b64}" alt="QR">`;
        noloader(); show('qris');
        _pP = setInterval(async () => {
            try {
                const r2 = await fetch(`/api/payment/status/${S.oid}`);
                const d2 = await r2.json();
                if (d2.status === 'paid') {
                    clearPay();
                    showSuccess('Pembayaran Berhasil', 'Terima Kasih', {
                        method: 'QRIS',
                        order: S.oid,
                        total: 'IDR 30.000'
                    }, () => { startTimer(); goToFrame(); });
                }
            } catch (_) { }
        }, 3000);
    } catch (e) { noloader(); alert('Gagal: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════
// VOUCHER
// ═══════════════════════════════════════════════════════════
function goVoucher() { show('voucher'); $('voucher-input').value = ''; }

async function claimVoucher() {
    const code = $('voucher-input').value.trim();
    if (!code) return alert('Masukkan kode voucher');
    loader('MEMVERIFIKASI...');
    try {
        const r = await fetch('/api/voucher/claim', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) });
        const d = await r.json(); noloader();
        if (d.valid) {
            S.sid = d.session_id;
            showSuccess('Voucher Berhasil', 'Terima Kasih', {
                method: 'Voucher',
                order: `VOUCHER-${code.toUpperCase()}`,
                total: 'GRATIS (Voucher)'
            }, () => { startTimer(); goToFrame(); });
        } else {
            alert('Gagal: ' + (d.error || 'Voucher tidak valid'));
        }
    } catch (e) { noloader(); alert('Error: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════
// FRAME SELECT — dummy placeholders when empty
// ═══════════════════════════════════════════════════════════
async function goToFrame() {
    loader('MEMUAT FRAME...');
    try { const r = await fetch('/api/config'); const d = await r.json(); S.frames = d.frames; S.filters = d.filters; } catch (e) { console.error(e); }
    noloader();

    // Ensure selected frame still exists
    if (S.frame && !S.frames.find(f => f.id === S.frame.id)) { S.frame = null; }

    renderFrames(); updateFramePreview(); show('frame');
}

function renderFrames() {
    const g = $('frame-grid'); g.innerHTML = '';

    if (S.frames.length === 0) {
        // Show dummy placeholders + message
        g.innerHTML = '<div class="emptyFrameMsg">Belum ada frame tersedia.<br>Admin perlu menambahkan frame di panel admin.</div>';
        for (let i = 0; i < 6; i++) {
            const c = document.createElement('div');
            c.className = 'fc fc-empty';
            c.innerHTML = `<div class="fcThumb"></div><div class="fcName">Kosong</div><div class="fcBadge">- Foto</div>`;
            g.appendChild(c);
        }
        return;
    }

    S.frames.forEach(f => {
        const sel = S.frame && S.frame.id === f.id;
        const c = document.createElement('div');
        c.className = 'fc' + (sel ? ' sel' : '');
        c.innerHTML = `<div class="fcThumb"><img src="${f.thumb}" alt="${f.name}"></div><div class="fcName">${f.name}</div><div class="fcBadge">${f.photos} Foto</div>`;
        c.onclick = () => { S.frame = f; S.max = f.photos; renderFrames(); updateFramePreview(); };
        g.appendChild(c);
    });
}

function updateFramePreview() {
    const body = $('frame-prev-body');
    const label = $('frame-name-label');
    const btn = $('btn-go-shoot');
    if (!S.frame) {
        body.innerHTML = '<p class="prevPlaceholder">Pilih frame di sebelah kiri</p>';
        label.textContent = '-'; btn.style.display = 'none'; return;
    }
    body.innerHTML = `<img src="${S.frame.thumb}" alt="${S.frame.name}">`;
    label.textContent = S.frame.name;
    btn.style.display = 'flex';
}

// ═══════════════════════════════════════════════════════════
// SHOOT — camera left, frame preview right with retake
// ═══════════════════════════════════════════════════════════
function backToFrame() { stopCam(); show('frame'); }

async function goToShoot() {
    if (!S.frame) return;
    S.photos = new Array(S.max).fill(null);
    S.slot = 0;
    loader('MENGAKSES KAMERA...');
    try {
        S.stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 960 }, facingMode: 'user' }, audio: false
        });
        const vid = $('cam-vid');
        vid.srcObject = S.stream;
        vid.style.transform = S.mirror ? 'scaleX(-1)' : 'none';
        await vid.play();
        noloader(); show('shoot');
        updateShootPreview();
        showTapOverlay();
        // Wait a moment for video to render, then show crop guide
        setTimeout(() => updateCropGuide(), 500);
    } catch (e) { noloader(); alert('Gagal akses kamera:\n' + e.message); }
}

// Crop guide — shows dark bars on camera to indicate what will be cropped
function updateCropGuide() {
    const f = S.frame;
    if (!f || !f.slots || !f.slots.length) return;
    const slot = f.slots[S.slot] || f.slots[0];
    const slotRatio = slot.w / slot.h; // target aspect ratio

    const camCard = document.querySelector('.camCard');
    const cardW = camCard.offsetWidth;
    const cardH = camCard.offsetHeight;
    const vid = $('cam-vid');
    const vidRatio = vid.videoWidth / vid.videoHeight || (16 / 9);
    const cardRatio = cardW / cardH;

    // The camera fills the card with object-fit:cover
    // Calculate visible area and where crop bars go
    let cropW, cropH;
    if (cardRatio > slotRatio) {
        // Card is wider than slot — bars on left/right
        cropH = cardH;
        cropW = cardH * slotRatio;
    } else {
        // Card is taller than slot — bars on top/bottom
        cropW = cardW;
        cropH = cardW / slotRatio;
    }

    const topBar = (cardH - cropH) / 2;
    const leftBar = (cardW - cropW) / 2;

    $('crop-top').style.height = topBar + 'px';
    $('crop-top').style.left = '0';
    $('crop-top').style.right = '0';

    $('crop-bot').style.height = topBar + 'px';
    $('crop-bot').style.left = '0';
    $('crop-bot').style.right = '0';

    $('crop-left').style.width = leftBar + 'px';
    $('crop-left').style.top = topBar + 'px';
    $('crop-left').style.bottom = topBar + 'px';

    $('crop-right').style.width = leftBar + 'px';
    $('crop-right').style.top = topBar + 'px';
    $('crop-right').style.bottom = topBar + 'px';

    // Center dashed border
    const center = $('crop-center');
    center.style.left = leftBar + 'px';
    center.style.top = topBar + 'px';
    center.style.width = cropW + 'px';
    center.style.height = cropH + 'px';
}

function stopCam() {
    if (S.stream) { S.stream.getTracks().forEach(t => t.stop()); S.stream = null; }
    if (_cdI) { clearInterval(_cdI); _cdI = null; }
}

function setMirror(on) {
    S.mirror = on;
    $('cam-vid').style.transform = on ? 'scaleX(-1)' : 'none';
    $('mb-mirror').classList.toggle('act', on);
    $('mb-normal').classList.toggle('act', !on);
}

function updateShootPreview() {
    const body = $('shoot-prev-body');
    const f = S.frame;
    if (!f) return;

    let html = `<div class="framePrev" style="width:100%;aspect-ratio:${f.width}/${f.height};max-height:100%">`;
    html += `<img class="frameImg" src="${f.thumb}" alt="Frame">`;

    f.slots.forEach((s, i) => {
        const left = (s.x / f.width * 100).toFixed(2);
        const top = (s.y / f.height * 100).toFixed(2);
        const w = (s.w / f.width * 100).toFixed(2);
        const h = (s.h / f.height * 100).toFixed(2);
        const isActive = (i === S.slot && !S.photos[i]);

        let content = '';
        if (S.photos[i]) {
            content = `<img src="${URL.createObjectURL(S.photos[i])}" onclick="confirmRetake(${i})">`;
            content += `<button class="retakeBtn" onclick="confirmRetake(${i})">Retake</button>`;
        } else if (isActive) {
            content = `<div style="width:100%;height:100%;background:rgba(233,30,99,.06);display:flex;align-items:center;justify-content:center"><span class="slotNumber" style="color:var(--pink);font-size:.7rem">${i + 1}</span></div>`;
        } else {
            content = `<div style="width:100%;height:100%;background:#f5f5f5;display:flex;align-items:center;justify-content:center"><span class="slotNumber">${i + 1}</span></div>`;
        }

        html += `<div class="slotWrap${isActive ? ' slotActive' : ''}" style="left:${left}%;top:${top}%;width:${w}%;height:${h}%">${content}</div>`;
    });

    html += '</div>';
    body.innerHTML = html;

    const filled = S.photos.filter(p => p !== null).length;
    $('shoot-status').textContent = filled >= S.max ? '✅ Semua foto selesai' : `📸 Foto ${S.slot + 1}/${S.max}`;
    $('btn-to-filter').style.display = filled >= S.max ? 'flex' : 'none';
    $('mb-retake').style.display = filled > 0 ? 'inline-block' : 'none';
}

function confirmRetake(i) {
    if (confirm('Ulangi foto ini?')) {
        retakeSlot(i);
    }
}

function retakeSlot(i) {
    if (!S.photos[i]) return;
    S.photos[i] = null;
    if (i < S.slot) S.slot = i;
    $('btn-to-filter').style.display = 'none';
    updateShootPreview();
    updateCropGuide();
    showTapOverlay();
}

function retakeLast() {
    let lastFilled = -1;
    for (let i = S.max - 1; i >= 0; i--) {
        if (S.photos[i]) { lastFilled = i; break; }
    }
    if (lastFilled >= 0) retakeSlot(lastFilled);
}

// Show/hide tap overlay
function showTapOverlay() {
    const tap = $('cam-tap');
    tap.classList.remove('hidden');
    const filled = S.photos.filter(p => p !== null).length;
    $('cam-tap-sub').textContent = `Foto ${S.slot + 1}/${S.max}`;
}
function tapToShoot() {
    $('cam-tap').classList.add('hidden');
    startCountdown();
}

let _cdI = null;
function startCountdown() {
    if (_cdI) { clearInterval(_cdI); _cdI = null; }
    $('cam-cd').style.display = 'flex';
    let c = 5;
    $('cam-cd-n').textContent = c;

    _cdI = setInterval(() => {
        c--;
        if (c > 0) {
            $('cam-cd-n').textContent = c;
        } else {
            clearInterval(_cdI); _cdI = null;
            $('cam-cd').style.display = 'none';
            capturePhoto();
        }
    }, 1000);
}

function capturePhoto() {
    const vid = $('cam-vid'), cvs = $('cam-cvs');
    cvs.width = vid.videoWidth; cvs.height = vid.videoHeight;
    const ctx = cvs.getContext('2d');
    ctx.save();
    if (S.mirror) { ctx.translate(cvs.width, 0); ctx.scale(-1, 1); }
    ctx.drawImage(vid, 0, 0);
    ctx.restore();

    const fl = $('cam-flash');
    fl.style.transition = 'none'; fl.style.opacity = '1';
    setTimeout(() => { fl.style.transition = 'opacity .4s'; fl.style.opacity = '0'; }, 60);

    cvs.toBlob(blob => {
        S.photos[S.slot] = blob;
        updateShootPreview();

        const filled = S.photos.filter(p => p !== null).length;
        if (filled < S.max) {
            for (let i = 0; i < S.max; i++) {
                if (S.photos[i] === null) { S.slot = i; break; }
            }
            updateShootPreview();
            // Show tap overlay for next photo instead of auto-countdown
            setTimeout(() => showTapOverlay(), 800);
        }
    }, 'image/png');
}

// ═══════════════════════════════════════════════════════════
// FILTER — each item shows actual preview thumbnail
// ═══════════════════════════════════════════════════════════
async function goToFilter() {
    stopCam();
    loader('MENYIMPAN FOTO...');
    const fd = new FormData();
    fd.append('frame_id', S.frame.id);
    fd.append('mirror', S.mirror);
    S.photos.forEach((b, i) => { if (b) fd.append('photos', b, `photo_${i}.png`); });
    try {
        const r = await fetch(`/api/session/${S.sid}/upload`, { method: 'POST', body: fd });
        if (!r.ok) throw new Error('Upload failed');
        noloader();
        $('filter-frame-name').textContent = S.frame.name;
        renderFilters();
        show('filter');
        loadPreview();
    } catch (e) { noloader(); alert('Gagal upload: ' + e.message); }
}

function renderFilters() {
    const g = $('filter-grid');
    if (g.children.length === 0) {
        S.filters.forEach(f => {
            const c = document.createElement('div');
            c.className = 'fltItem' + (S.filter === f.name ? ' sel' : '');
            c.dataset.name = f.name;
            c.innerHTML = `<div class="fltBox"><div class="fltName">${f.name}</div></div>`;
            c.onclick = () => {
                S.filter = f.name;
                renderFilters();
                loadPreview();
            };
            g.appendChild(c);
        });
    } else {
        Array.from(g.children).forEach(c => {
            if (c.dataset.name === S.filter) c.classList.add('sel');
            else c.classList.remove('sel');
        });
    }
}

function loadPreview() {
    const img = $('prev-img'), spin = $('prev-spin');
    img.style.opacity = '.3'; spin.style.display = 'block';
    const url = `/api/session/${S.sid}/preview?filter_name=${encodeURIComponent(S.filter)}`;
    const t = new Image();
    t.onload = () => { img.src = url; img.style.opacity = '1'; spin.style.display = 'none'; };
    t.onerror = () => { spin.style.display = 'none'; img.style.opacity = '1'; };
    t.src = url;
}

// ═══════════════════════════════════════════════════════════
// EMOJIS / STICKERS
// ═══════════════════════════════════════════════════════════
const EMOJIS = ['💖', '✨', '🌸', '🎀', '🦋', '🧸', '🍓', '🍒', '🎈', '👑', '🐱', '🐰', '🐻', '💕', '🥳', '🔥', '⭐', '🥑', '🍄', '🌈'];

function toggleEmojiDrawer() {
    const d = $('emoji-drawer');
    if (!d.classList.contains('open')) {
        const g = $('emoji-grid');
        if (g.children.length === 0) {
            EMOJIS.forEach(e => {
                const btn = document.createElement('button');
                btn.className = 'emjBtn';
                btn.textContent = e;
                btn.onclick = () => addSticker(e);
                g.appendChild(btn);
            });
        }
        d.classList.add('open');
    } else {
        d.classList.remove('open');
    }
}

function addSticker(char) {
    toggleEmojiDrawer();
    const ov = $('emoji-overlay');
    const el = document.createElement('div');
    el.className = 'draggable-emoji';
    el.innerHTML = `${char}<button class="del-btn" onclick="this.parentElement.remove()">×</button>`;

    const rect = ov.getBoundingClientRect();
    let x = rect.width / 2;
    let y = rect.height / 2;
    el.style.left = x + 'px';
    el.style.top = y + 'px';

    ov.appendChild(el);

    let isDragging = false;
    let startX, startY, initialX, initialY;

    const dragStart = (e) => {
        if (e.target.classList.contains('del-btn')) return;
        isDragging = true;
        const pt = e.touches ? e.touches[0] : e;
        startX = pt.clientX;
        startY = pt.clientY;
        initialX = el.offsetLeft;
        initialY = el.offsetTop;
        e.preventDefault();
    };

    const dragMove = (e) => {
        if (!isDragging) return;
        const pt = e.touches ? e.touches[0] : e;
        const dx = pt.clientX - startX;
        const dy = pt.clientY - startY;
        el.style.left = (initialX + dx) + 'px';
        el.style.top = (initialY + dy) + 'px';
    };

    const dragEnd = () => { isDragging = false; };

    el.addEventListener('mousedown', dragStart);
    el.addEventListener('touchstart', dragStart, { passive: false });
    document.addEventListener('mousemove', dragMove);
    document.addEventListener('touchmove', dragMove, { passive: false });
    document.addEventListener('mouseup', dragEnd);
    document.addEventListener('touchend', dragEnd);
}

// ═══════════════════════════════════════════════════════════
// DONE
// ═══════════════════════════════════════════════════════════
async function finalizeStrip() {
    loader('MENCETAK STRIP...');
    const fd = new FormData(); fd.append('filter_name', S.filter);

    // Capture stickers
    const ov = $('emoji-overlay');
    const emojis = ov.querySelectorAll('.draggable-emoji');
    if (emojis.length > 0) {
        const img = $('prev-img');
        const imgRect = img.getBoundingClientRect();

        const cvs = document.createElement('canvas');
        cvs.width = img.naturalWidth;
        cvs.height = img.naturalHeight;
        const ctx = cvs.getContext('2d');

        const rRatio = img.naturalWidth / img.naturalHeight;
        const dRatio = imgRect.width / imgRect.height;

        let drawW, drawH, offsetX, offsetY;
        if (dRatio > rRatio) {
            drawH = imgRect.height;
            drawW = drawH * rRatio;
            offsetX = (imgRect.width - drawW) / 2;
            offsetY = 0;
        } else {
            drawW = imgRect.width;
            drawH = drawW / rRatio;
            offsetX = 0;
            offsetY = (imgRect.height - drawH) / 2;
        }

        const scale = img.naturalWidth / drawW;

        emojis.forEach(e => {
            const char = e.childNodes[0].nodeValue;
            const eRect = e.getBoundingClientRect();
            const cx = eRect.left + eRect.width / 2 - imgRect.left;
            const cy = eRect.top + eRect.height / 2 - imgRect.top;

            const nx = (cx - offsetX) * scale;
            const ny = (cy - offsetY) * scale;
            const nSize = 48 * scale;

            ctx.font = `${nSize}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(char, nx, ny);
        });

        const blob = await new Promise(r => cvs.toBlob(r, 'image/png'));
        fd.append('sticker_overlay', blob, 'stickers.png');
    }

    try {
        const r = await fetch(`/api/session/${S.sid}/finalize`, { method: 'POST', body: fd });
        if (!r.ok) throw new Error('Finalize failed');
        const d = await r.json();
        $('done-img').src = d.strip_url;
        if (d.qr_b64) $('done-qr').innerHTML = `<img src="data:image/png;base64,${d.qr_b64}" alt="QR">`;
        noloader(); stopTimer(); show('done');
    } catch (e) { noloader(); alert('Gagal: ' + e.message); }
}
