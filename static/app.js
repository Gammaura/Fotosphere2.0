/* Fotosphere App v9 */
// Lock content size to initial viewport — prevents resize on fullscreen
(function(){const h=(window.innerHeight-80)+'px',w=(window.innerWidth-80)+'px';document.documentElement.style.setProperty('--init-h',h);document.documentElement.style.setProperty('--init-w',w)})();
function showModal(t,s,i='✨'){document.getElementById('modal-title').innerText=t;document.getElementById('modal-sub').innerText=s;document.getElementById('modal-icon').innerText=i;document.getElementById('overlay-modal').style.display='flex'}
function hideModal(){document.getElementById('overlay-modal').style.display='none'}
const S={sid:null,oid:null,frames:[],filters:[],categories:{},frame:null,filter:'Natural',emoji:'Original',photos:[],max:1,slot:0,mirror:false,stream:null,timerSec:3,livePhoto:true,stripUrl:'',gifUrl:'',liveClips:[],photoUrls:[],liveUrls:[],qrisPrice:30000};
let _idleT=null,_idleLimit=120000; // 2 min idle auto-return
function resetIdle(){if(_idleT)clearTimeout(_idleT);_idleT=setTimeout(()=>{const cur=document.querySelector('.screen.active');if(cur&&(cur.id==='screen-paymethod'||cur.id==='screen-qris'||cur.id==='screen-voucher'||cur.id==='screen-ticket')){goHome();showModal('Sesi Idle','Kembali ke halaman utama karena tidak ada aktivitas','⏳')}},_idleLimit)}
['click','touchstart','keydown'].forEach(e=>document.addEventListener(e,resetIdle,{passive:true}));
const $=id=>document.getElementById(id);
const show=id=>{document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));$('screen-'+id).classList.add('active')};
let _progInt=null,_progStage=0,_progTarget=0;
function loader(m){
    const pm=$('progress-modal');
    if(pm){
        $('prog-sub').textContent=m||'MEMPROSES...';$('prog-bar').style.width='0%';
        $('prog-left').textContent='0/100';$('prog-right').textContent='0%';
        pm.style.display='flex';_progStage=0;_progTarget=0;
        if(_progInt)clearInterval(_progInt);
        _progInt=setInterval(()=>{
            if(_progStage<_progTarget)_progStage+=Math.min(2,_progTarget-_progStage);
            $('prog-bar').style.width=_progStage+'%';$('prog-left').textContent=Math.floor(_progStage)+'/100';$('prog-right').textContent=Math.floor(_progStage)+'%';
        },80);
    } else {
        $('loader-msg').textContent=m||'MEMPROSES...';$('loader').style.display='flex';
    }
}
function setProgress(pct,msg){_progTarget=Math.min(pct,100);if(msg){const s=$('prog-sub');if(s)s.textContent=msg}}
function noloader(){
    const pm=$('progress-modal');
    if(pm){
        if(_progInt)clearInterval(_progInt);
        $('prog-bar').style.width='100%';$('prog-left').textContent='100/100';$('prog-right').textContent='100%';
        setTimeout(()=>{pm.style.display='none'},300);
    } else {
        $('loader').style.display='none';
    }
}
function showSuccess(t,s,inv,cb){$('success-text').textContent=t;$('success-sub').textContent=s||'Terima Kasih';const b=$('invoice-box');if(inv){$('inv-method').textContent=inv.method||'-';$('inv-order').textContent=inv.order||'-';$('inv-total').textContent=inv.total||'-';b.style.display='block'}else b.style.display='none';$('success-overlay').style.display='flex';setTimeout(()=>{$('success-overlay').style.display='none';if(cb)cb()},3000)}
function vkType(ch){$('voucher-input').value+=ch}
function vkDel(){$('voucher-input').value=$('voucher-input').value.slice(0,-1)}

// Init
async function init(){try{const r=await fetch('/api/config');const d=await r.json();S.frames=d.frames;S.filters=d.filters;if(d.qris_price)S.qrisPrice=d.qris_price;buildCats();updateQrisPrice()}catch(e){console.error(e)}}
function updateQrisPrice(){const el=document.querySelector('.qrPrice');if(el)el.textContent='Rp. '+S.qrisPrice.toLocaleString('id-ID')}
function buildCats(){S.categories={};S.frames.forEach(f=>{if(f.is_private)return;let c=f.category||'Other';if(!S.categories[c])S.categories[c]=[];S.categories[c].push(f)})}
init();

// Timer
let _sT=null,_sL=600;
function startTimer(){_sL=600;updT();if(_sT)clearInterval(_sT);_sT=setInterval(()=>{_sL--;updT();if(_sL===120)showModal('⏰ 2 Menit Lagi','Segera selesaikan foto kamu!','⏰');if(_sL===30)showModal('⚠️ 30 Detik!','Cepat cetak foto kamu sekarang!','🔥');if(_sL<=0){clearInterval(_sT);goHome();showModal('Sesi Habis','Mohon lakukan pembayaran kembali','⏳')}},1000)}
function stopTimer(){if(_sT){clearInterval(_sT);_sT=null}}
function updT(){const t=`${String(Math.floor(_sL/60)).padStart(2,'0')}.${String(_sL%60).padStart(2,'0')}`;['frame-timer','shoot-timer','emoji-timer','filter-timer'].forEach(id=>{const e=$(id);if(e){e.textContent=t;e.classList.toggle('danger',_sL<=120)}})}

function goHome(){stopCam();stopTimer();clearPay();stopTicketScan();S.sid=null;S.oid=null;S.frame=null;S.filter='Natural';S.emoji='Original';S.photos=[];S.slot=0;S.liveClips=[];(S.photoUrls||[]).forEach(u=>{if(u)URL.revokeObjectURL(u)});S.photoUrls=[];(S.liveUrls||[]).forEach(u=>{if(u)URL.revokeObjectURL(u)});S.liveUrls=[];const o=$('emoji-overlay');if(o)o.innerHTML='';show('home')}
function goPaymentMethod(){stopCam();clearPay();show('paymethod')}

// Ticket scan
let _scanner=null,_scanP=false;
async function goScanTicket(){
    show('ticket');_scanP=false;
    try {
        const devices = await Html5Qrcode.getCameras();
        if(devices && devices.length) {
            _scanner=new Html5Qrcode("ticket-reader");
            await _scanner.start(devices[0].id, {fps:20}, async(txt)=>{
                if(_scanP)return;_scanP=true;
                try {
                    const r=await fetch('/api/ticket/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:txt})});
                    const d=await r.json();
                    if(d.valid){
                        S.sid=d.session_id; stopTicketScan();
                        if(d.custom_frame_data){
                            S.frame=d.custom_frame_data;
                            if(S.frame){ S.max=S.frame.photos; showSuccess('Scan Ticket Berhasil','Terima Kasih',{method:'Ticket',order:'TICKET-'+txt,total:'GRATIS'},()=>{startTimer();goToShoot()}); return; }
                        }
                        showSuccess('Scan Ticket Berhasil','Terima Kasih',{method:'Ticket',order:'TICKET-'+txt,total:'GRATIS'},()=>{startTimer();goToFrame()});
                    } else {
                        _scanP=false; showModal('Ticket Tidak Valid','Coba scan ulang','❌');
                    }
                }catch(e){_scanP=false;}
            }, ()=>{});
        } else {
            showModal('Kamera Error','Kamera tidak ditemukan','❌');
        }
    } catch(e) {
        console.error(e);
        showModal('Kamera Error','Gagal mengakses kamera','❌');
    }
}
function stopTicketScan(){if(_scanner){try{_scanner.stop().catch(()=>{})}catch(_){}try{_scanner.clear()}catch(_){}_scanner=null}}

// QRIS
let _pT=null,_pP=null;
function clearPay(){if(_pT){clearInterval(_pT);_pT=null}if(_pP){clearInterval(_pP);_pP=null}}
async function goQRIS(){loader('MEMPERSIAPKAN PEMBAYARAN...');try{const r=await fetch('/api/payment/create',{method:'POST'});if(!r.ok)throw new Error('err');const d=await r.json();S.sid=d.session_id;S.oid=d.order_id;$('qr-box').innerHTML=`<img src="data:image/png;base64,${d.qr_b64}">`;noloader();show('qris');_pP=setInterval(async()=>{try{const r2=await fetch('/api/payment/status/'+S.oid);const d2=await r2.json();if(d2.status==='paid'){clearPay();showSuccess('Pembayaran Berhasil','Terima Kasih',{method:'QRIS',order:S.oid,total:'IDR 30.000'},()=>{startTimer();goToFrame()})}}catch(_){}},3000)}catch(e){noloader();showModal('Gagal',e.message,'⚠️')}}

// Voucher
function goVoucher(){show('voucher');$('voucher-input').value=''}
async function claimVoucher(){const code=$('voucher-input').value.trim();if(!code)return showModal('Perhatian','Masukkan kode voucher','💡');loader('MEMVERIFIKASI...');try{const r=await fetch('/api/voucher/claim',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});const d=await r.json();noloader();if(d.valid){S.sid=d.session_id;if(d.custom_frame_data){S.frame=d.custom_frame_data;if(S.frame){S.max=S.frame.photos;showSuccess('Voucher Berhasil','Terima Kasih',{method:'Voucher',order:'VOUCHER-'+code.toUpperCase(),total:'GRATIS'},()=>{startTimer();goToShoot()});return}}showSuccess('Voucher Berhasil','Terima Kasih',{method:'Voucher',order:'VOUCHER-'+code.toUpperCase(),total:'GRATIS'},()=>{startTimer();goToFrame()})}else showModal('Gagal',d.error||'Tidak valid','❌')}catch(e){noloader();showModal('Error',e.message,'⚠️')}}

// Frame select
let _activeCat='all';
async function goToFrame(){loader('MEMUAT FRAME...');try{const r=await fetch('/api/config');const d=await r.json();S.frames=d.frames;S.filters=d.filters;buildCats()}catch(e){}noloader();_activeCat='all';if(S.frame&&!S.frames.find(f=>f.id===S.frame.id))S.frame=null;renderFramePanel();updateFPrev();show('frame')}

function renderFramePanel(){
    const body=$('frame-body');body.innerHTML='';
    const catKeys=Object.keys(S.categories);
    $('frame-card-head').textContent='ADD FRAME';

    // Category tabs (horizontal scroll)
    let tabsH='<div class="catTabs"><div class="catTabsInner">';
    tabsH+=`<button class="catTab${_activeCat==='all'?' active':''}" onclick="filterCat('all')">All Frame</button>`;
    catKeys.forEach(cat=>{
        tabsH+=`<button class="catTab${_activeCat===cat?' active':''}" onclick="filterCat('${cat}')">${cat}</button>`;
    });
    tabsH+='</div></div>';

    // Filtered frames (vertical scroll)
    const frames=_activeCat==='all'?S.frames.filter(f=>!f.is_private):(S.categories[_activeCat]||[]);
    let gridH='<div class="frameGrid">';
    if(!frames.length){gridH+='<div class="emptyFrameMsg">Belum ada frame.</div>'}
    else frames.forEach(f=>{const sel=S.frame&&S.frame.id===f.id;const thumbUrl=`/api/frames/thumb/${f.file||f.id}`;gridH+=`<div class="fc${sel?' sel':''}" onclick="pickFrame('${f.id}')"><div class="fcThumb"><img src="${thumbUrl}" loading="lazy"></div><div class="fcName">${f.name}</div><div class="fcBadge">${f.photos} Foto</div></div>`});
    gridH+='</div>';

    body.innerHTML=tabsH+gridH;
}
function filterCat(cat){_activeCat=cat;renderFramePanel()}
function pickFrame(id){S.frame=S.frames.find(f=>f.id===id);if(S.frame)S.max=S.frame.photos;renderFramePanel();updateFPrev()}
function updateFPrev(){
    const b=$('frame-prev-body'),l=$('frame-name-label'),c=$('frame-photo-count'),btn=$('btn-go-shoot');
    if(!S.frame){b.innerHTML='<p class="prevPh">Pilih frame</p>';l.textContent='-';c.textContent='-';btn.style.display='none';return}
    b.innerHTML=`<img src="${S.frame.thumb}">`;l.textContent=S.frame.name;c.textContent=S.frame.photos+' Photo';btn.style.display='flex';
}

// Shoot
function backToFrame(){stopCam();show('frame')}
async function goToShoot(){
    if(!S.frame)return;S.photos=new Array(S.max).fill(null);S.slot=0;S.liveClips=new Array(S.max).fill(null);(S.photoUrls||[]).forEach(u=>{if(u)URL.revokeObjectURL(u)});S.photoUrls=new Array(S.max).fill(null);(S.liveUrls||[]).forEach(u=>{if(u)URL.revokeObjectURL(u)});S.liveUrls=new Array(S.max).fill(null);
    loader('MENGAKSES KAMERA...');
    try{S.stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1920},height:{ideal:1080},facingMode:'user'},audio:false});
    const v=$('cam-vid');v.srcObject=S.stream;v.style.transform=S.mirror?'scaleX(-1)':'none';await v.play();
    noloader();show('shoot');$('shoot-frame-name').textContent=S.frame.name;$('shoot-photo-total').textContent=S.max+' Photo';updateShootPrev();showTapOv();}
    catch(e){noloader();showModal('Gagal','Kamera error: '+e.message,'📷')}
}
function updateCropGuide(){const f=S.frame;if(!f||!f.slots||!f.slots.length)return;const s=f.slots[S.slot]||f.slots[0];const sr=s.w/s.h;const cc=document.querySelector('.camCard');const cw=cc.offsetWidth,ch=cc.offsetHeight;let cropW,cropH;if(cw/ch>sr){cropH=ch;cropW=ch*sr}else{cropW=cw;cropH=cw/sr}const tb=(ch-cropH)/2,lb=(cw-cropW)/2;$('crop-top').style.height=tb+'px';$('crop-top').style.left='0';$('crop-top').style.right='0';$('crop-bot').style.height=tb+'px';$('crop-bot').style.left='0';$('crop-bot').style.right='0';$('crop-left').style.width=lb+'px';$('crop-left').style.top=tb+'px';$('crop-left').style.bottom=tb+'px';$('crop-right').style.width=lb+'px';$('crop-right').style.top=tb+'px';$('crop-right').style.bottom=tb+'px';const cn=$('crop-center');cn.style.left=lb+'px';cn.style.top=tb+'px';cn.style.width=cropW+'px';cn.style.height=cropH+'px'}
function stopCam(){if(S.stream){S.stream.getTracks().forEach(t=>t.stop());S.stream=null}if(_cdI){clearInterval(_cdI);_cdI=null}stopLiveRec()}
function setMirror(on){S.mirror=on;$('cam-vid').style.transform=on?'scaleX(-1)':'none';$('mb-mirror').classList.toggle('on',on);$('mb-normal').classList.toggle('on',!on)}
function setTimer(s){S.timerSec=s;[3,5,7].forEach(v=>$('timer-'+v).classList.toggle('on',v===s))}
function setLivePhoto(on){S.livePhoto=on;$('lp-on').classList.toggle('on',on);$('lp-off').classList.toggle('on',!on)}

function updateShootPrev(){
    const b=$('shoot-prev-body'),f=S.frame;if(!f)return;
    let h=`<div class="framePrev" style="width:100%;aspect-ratio:${f.width}/${f.height};max-height:100%"><img class="frameImg" src="${f.thumb}">`;
    f.slots.forEach((s,i)=>{const l=(s.x/f.width*100).toFixed(2),t=(s.y/f.height*100).toFixed(2),w=(s.w/f.width*100).toFixed(2),hh=(s.h/f.height*100).toFixed(2);const act=i===S.slot&&!S.photos[i];let c='';if(S.photos[i])c=`<img src="${S.photoUrls[i]}" onclick="confirmRetake(${i})"><button class="retakeBtn" onclick="confirmRetake(${i})">Retake</button>`;else if(act)c=`<div style="width:100%;height:100%;background:rgba(139,26,26,.08);display:flex;align-items:center;justify-content:center"><span class="slotNumber" style="color:var(--accent)">${i+1}</span></div>`;else c=`<div style="width:100%;height:100%;background:#f5f5f5;display:flex;align-items:center;justify-content:center"><span class="slotNumber">${i+1}</span></div>`;h+=`<div class="slotWrap${act?' slotActive':''}" style="left:${l}%;top:${t}%;width:${w}%;height:${hh}%">${c}</div>`});
    h+='</div>';b.innerHTML=h;
    const filled=S.photos.filter(p=>p!==null).length;$('shoot-progress').textContent=`${filled}/${S.max}`;$('btn-to-emoji').style.display=filled>=S.max?'flex':'none';
}
let _retakeI=null;function confirmRetake(i){_retakeI=i;const rm=$('retake-modal');rm.style.display='flex';const prevEl=$('retake-preview');if(prevEl&&S.photoUrls[i])prevEl.innerHTML=`<img src="${S.photoUrls[i]}" style="width:120px;height:auto;border-radius:10px;border:2px solid #eee;margin-bottom:0.5rem">`;else if(prevEl)prevEl.innerHTML='';$('btn-confirm-retake').onclick=()=>{rm.style.display='none';retakeSlot(_retakeI)};}
function retakeSlot(i){if(!S.photos[i])return;S.photos[i]=null;S.liveClips[i]=null;if(i<S.slot)S.slot=i;$('btn-to-emoji').style.display='none';updateShootPrev();updateCropGuide();showTapOv()}
function showTapOv(){$('cam-tap').classList.remove('hidden');$('cam-tap-sub').textContent=`Foto ${S.slot+1}/${S.max}`;document.querySelector('.cropGuide').style.display='none'}
function tapToShoot(){$('cam-tap').classList.add('hidden');document.querySelector('.cropGuide').style.display='block';setTimeout(()=>updateCropGuide(),100);startCountdown()}

// Live Photo recording
let _mediaRec=null,_liveChunks=[],_liveCvs=null,_liveCvsInterval=null;
function startLiveRec(){
    if(!S.livePhoto||!S.stream)return;
    try{
        _liveChunks=[];
        let recStream=S.stream;
        if(S.mirror){
            const vid=$('cam-vid');
            _liveCvs=document.createElement('canvas');
            _liveCvs.width=vid.videoWidth||1920;
            _liveCvs.height=vid.videoHeight||1080;
            const ctx=_liveCvs.getContext('2d');
            _liveCvsInterval=setInterval(()=>{
                ctx.save();ctx.translate(_liveCvs.width,0);ctx.scale(-1,1);
                ctx.drawImage(vid,0,0,_liveCvs.width,_liveCvs.height);
                ctx.restore();
            },33);
            recStream=_liveCvs.captureStream(30);
        }
        let mime = 'video/webm;codecs=vp9';
        if (!MediaRecorder.isTypeSupported(mime)) mime = 'video/webm;codecs=vp8';
        if (!MediaRecorder.isTypeSupported(mime)) mime = 'video/webm';
        if (!MediaRecorder.isTypeSupported(mime)) mime = ''; // let browser decide
        
        let opts = mime ? {mimeType: mime, videoBitsPerSecond: 2500000} : {};
        try {
            _mediaRec = new MediaRecorder(recStream, opts);
        } catch(e) {
            console.log('MediaRecorder high bitrate failed, trying default:', e);
            _mediaRec = new MediaRecorder(recStream);
        }
        _mediaRec.ondataavailable = e => { if(e.data.size > 0) _liveChunks.push(e.data); };
        _mediaRec.start(100);
    } catch(e) {
        console.error('MediaRecorder completely failed:', e);
    }
}
function stopLiveRec(){
    if(_liveCvsInterval){clearInterval(_liveCvsInterval);_liveCvsInterval=null;_liveCvs=null}
    if(_mediaRec&&_mediaRec.state!=='inactive'){try{_mediaRec.stop()}catch(e){}_mediaRec=null}
}
function saveLiveClip(){
    return new Promise(resolve=>{
        if(!_mediaRec||_liveChunks.length===0){resolve(null);return}
        _mediaRec.onstop=()=>{const blob=new Blob(_liveChunks,{type:'video/webm'});_liveChunks=[];resolve(blob)};
        try{_mediaRec.stop()}catch(e){resolve(null)}_mediaRec=null;
        if(_liveCvsInterval){clearInterval(_liveCvsInterval);_liveCvsInterval=null;_liveCvs=null}
    });
}

// Sound Effects Synthesis
const _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
function playBeep(){
    if(_audioCtx.state==='suspended')_audioCtx.resume();
    const osc=_audioCtx.createOscillator(),gain=_audioCtx.createGain();
    osc.type='sine';osc.frequency.setValueAtTime(880,_audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440,_audioCtx.currentTime+0.1);
    gain.gain.setValueAtTime(0.1,_audioCtx.currentTime);gain.gain.exponentialRampToValueAtTime(0.01,_audioCtx.currentTime+0.1);
    osc.connect(gain);gain.connect(_audioCtx.destination);osc.start();osc.stop(_audioCtx.currentTime+0.1);
}
function playShutter(){
    if(_audioCtx.state==='suspended')_audioCtx.resume();
    const osc=_audioCtx.createOscillator(),gain=_audioCtx.createGain();
    osc.type='square';osc.frequency.setValueAtTime(150,_audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(40,_audioCtx.currentTime+0.15);
    gain.gain.setValueAtTime(0.2,_audioCtx.currentTime);gain.gain.exponentialRampToValueAtTime(0.01,_audioCtx.currentTime+0.15);
    osc.connect(gain);gain.connect(_audioCtx.destination);osc.start();osc.stop(_audioCtx.currentTime+0.15);
}

let _cdI=null;
function startCountdown(){
    if(_cdI){clearInterval(_cdI);_cdI=null}
    // Start live recording before countdown
    startLiveRec();
    $('cam-cd').style.display='flex';let c=S.timerSec;$('cam-cd-n').textContent=c;
    playBeep();
    _cdI=setInterval(()=>{c--;if(c>0){$('cam-cd-n').textContent=c;playBeep();}else{clearInterval(_cdI);_cdI=null;$('cam-cd').style.display='none';capturePhoto()}},1000);
}

async function capturePhoto(){
    playShutter();
    const vid=$('cam-vid'),cvs=$('cam-cvs');cvs.width=vid.videoWidth;cvs.height=vid.videoHeight;
    const ctx=cvs.getContext('2d');ctx.save();if(S.mirror){ctx.translate(cvs.width,0);ctx.scale(-1,1)}ctx.drawImage(vid,0,0);ctx.restore();
    const fl=$('cam-flash');fl.style.transition='none';fl.style.opacity='1';setTimeout(()=>{fl.style.transition='opacity .4s';fl.style.opacity='0'},60);

    // Capture current slot index BEFORE it changes
    const capturedSlot=S.slot;

    // Save live clip for this slot (wait a moment for last frames)
    setTimeout(async()=>{
        const liveBlob=await saveLiveClip();
        if(liveBlob){
            S.liveClips[capturedSlot]=liveBlob;
            if(S.liveUrls[capturedSlot]) URL.revokeObjectURL(S.liveUrls[capturedSlot]);
            S.liveUrls[capturedSlot] = URL.createObjectURL(liveBlob);
        }
    },800);

    cvs.toBlob(blob=>{
        S.photos[capturedSlot]=blob;
        if(S.photoUrls[capturedSlot]) URL.revokeObjectURL(S.photoUrls[capturedSlot]);
        S.photoUrls[capturedSlot] = URL.createObjectURL(blob);
        updateShootPrev();
        const filled=S.photos.filter(p=>p!==null).length;
        if(filled<S.max){for(let i=0;i<S.max;i++){if(S.photos[i]===null){S.slot=i;break}}updateShootPrev();setTimeout(()=>showTapOv(),800)}
    },'image/png');
}

// Emoji
const EMOJI_SETS={Original:{c:'✨',l:'Original'},Kitten:{c:'🐱',l:'Kitten'},Flower:{c:'🌸',l:'Flower'},Heart:{c:'💖',l:'Heart'},Star:{c:'⭐',l:'Star'},Bear:{c:'🐻',l:'Bear'},Bunny:{c:'🐰',l:'Bunny'},Butterfly:{c:'🦋',l:'Butterfly'},Cherry:{c:'🍒',l:'Cherry'},Fire:{c:'🔥',l:'Fire'},Rainbow:{c:'🌈',l:'Rainbow'},Crown:{c:'👑',l:'Crown'},Strawberry:{c:'🍓',l:'Strawberry'},Ribbon:{c:'🎀',l:'Ribbon'},Moon:{c:'🌙',l:'Moon'},Sun:{c:'☀️',l:'Sun'},Cloud:{c:'☁️',l:'Cloud'},Leaf:{c:'🍃',l:'Leaf'},Balloon:{c:'🎈',l:'Balloon'},Candy:{c:'🍬',l:'Candy'},Diamond:{c:'💎',l:'Diamond'},Mushroom:{c:'🍄',l:'Mushroom'},Paw:{c:'🐾',l:'Paw'},Sparkle:{c:'✨',l:'Sparkle'}};

async function goToEmoji(){
    stopCam();loader('MENGUNGGAH FOTO...');setProgress(10,'Mengunggah foto...');
    const fd=new FormData();fd.append('frame_id',S.frame.id);fd.append('mirror',S.mirror);
    S.photos.forEach((b,i)=>{if(b)fd.append('photos',b,`photo_${i}.png`)});
    try{setProgress(40,'Memproses...');const r=await fetch(`/api/session/${S.sid}/upload`,{method:'POST',body:fd});if(!r.ok)throw new Error('Upload failed');setProgress(100,'Selesai!');noloader();$('emoji-frame-name').textContent=S.frame.name;$('emoji-photo-total').textContent=S.max+' Photo';renderEmojis();loadEmojiPrev();show('emoji')}catch(e){noloader();showModal('Gagal',e.message,'⚠️')}
}
function renderEmojis(){
    const g=$('emoji-grid2');g.innerHTML='';
    Object.keys(EMOJI_SETS).forEach(k=>{const e=EMOJI_SETS[k];const sel=S.emoji===k;const d=document.createElement('div');d.className='emojiItem'+(sel?' sel':'');d.innerHTML=`<span class="eChar">${e.c}</span><span class="eName">${e.l}</span>`;d.onclick=()=>{S.emoji=k;renderEmojis();applyEmojiOv();$('emoji-status').textContent=k};g.appendChild(d)});
}
function loadEmojiPrev(){$('emoji-prev-img').src=`/api/session/${S.sid}/preview?filter_name=Natural`;applyEmojiOv()}
function applyEmojiOv(){
    const ov=$('emoji-overlay');ov.innerHTML='';if(S.emoji==='Original')return;
    const e=EMOJI_SETS[S.emoji];if(!e)return;
    // Calculate image bounds within the phoneScr to clip emojis to frame
    const img=$('emoji-prev-img');const container=$('emoji-prev-body');
    if(!img||!container)return;
    const ir=img.getBoundingClientRect(),cr=container.getBoundingClientRect();
    const offL=ir.left-cr.left,offT=ir.top-cr.top,iW=ir.width,iH=ir.height;
    if(iW<10||iH<10)return;
    // Sparsely scatter emojis ONLY on the edges (border) of the frame
    const numE = 8 + Math.floor(Math.random() * 4); // 8 to 11 emojis
    for(let i=0; i<numE; i++){
        const el=document.createElement('span');el.className='emojiOverlayItem';el.textContent=e.c;
        let px, py;
        const edge = Math.floor(Math.random() * 4); // 0: top, 1: right, 2: bottom, 3: left
        if (edge === 0) { px = offL + Math.random()*iW; py = offT + Math.random()*(iH*0.12); } 
        else if (edge === 1) { px = offL + iW - Math.random()*(iW*0.15); py = offT + Math.random()*iH; } 
        else if (edge === 2) { px = offL + Math.random()*iW; py = offT + iH - Math.random()*(iH*0.12); } 
        else { px = offL + Math.random()*(iW*0.15); py = offT + Math.random()*iH; }

        const sz=0.6+Math.random()*0.4, rot=Math.random()*60-30;
        el.style.cssText=`left:${px}px;top:${py}px;font-size:${sz}rem;transform:translate(-50%,-50%) rotate(${rot}deg);opacity:${.7+Math.random()*.3};position:absolute`;
        ov.appendChild(el);
    }
}

// Filter
async function goToFilter(){
    $('filter-frame-name').textContent=S.frame.name;
    $('filter-photo-total').textContent=S.max+' Photo';
    $('filter-status').textContent=S.filter;
    // Copy emoji overlay to filter page
    const srcOv=$('emoji-overlay'),dstOv=$('filter-emoji-overlay');
    if(srcOv&&dstOv)dstOv.innerHTML=srcOv.innerHTML;
    renderFilters();show('filter');loadPreview();
}
function renderFilters(){
    const g=$('filter-grid');g.innerHTML='';
    S.filters.forEach(f=>{
        if(f.name==='Original')return; // skip Original, use Natural instead
        const d=document.createElement('div');d.className='filterItem'+(S.filter===f.name?' sel':'');d.dataset.name=f.name;
        const thumbUrl=`/api/session/${S.sid}/preview?filter_name=${encodeURIComponent(f.name)}&thumb=1`;
        d.innerHTML=`<div class="fcThumb" style="border-radius:10px"><img class="fltThumb" src="${thumbUrl}" loading="lazy" style="border-radius:10px;object-fit:contain;background:#000"></div><div class="fcName" style="font-size:0.8rem;margin-top:8px">${f.name}</div>`;
        d.onclick=()=>{S.filter=f.name;renderFilters();loadPreview();$('filter-status').textContent=f.name};
        g.appendChild(d);
    });
}
function loadPreview(){const img=$('prev-img'),sp=$('prev-spin');img.style.opacity='.3';sp.style.display='block';const url=`/api/session/${S.sid}/preview?filter_name=${encodeURIComponent(S.filter)}`;const t=new Image();t.onload=()=>{img.src=url;img.style.opacity='1';sp.style.display='none'};t.onerror=()=>{sp.style.display='none';img.style.opacity='1'};t.src=url}

// Finalize
async function finalizeStrip(){
    loader('MENCETAK STRIP...');setProgress(5,'Menyiapkan...');const fd=new FormData();fd.append('filter_name',S.filter);
    // Sticker overlay from emoji
    setProgress(15,'Membuat stiker...');
    const ov=$('emoji-overlay');const ems=ov.querySelectorAll('.emojiOverlayItem');
    if(ems.length>0){const img=$('emoji-prev-img')||$('prev-img');if(img&&img.naturalWidth){const cvs=document.createElement('canvas');cvs.width=img.naturalWidth;cvs.height=img.naturalHeight;const ctx=cvs.getContext('2d');const ir=img.getBoundingClientRect();const rr=img.naturalWidth/img.naturalHeight,dr=ir.width/ir.height;let dw,dh,ox,oy;if(dr>rr){dh=ir.height;dw=dh*rr;ox=(ir.width-dw)/2;oy=0}else{dw=ir.width;dh=dw/rr;ox=0;oy=(ir.height-dh)/2}const sc=img.naturalWidth/dw;ems.forEach(e=>{const ch=e.textContent,er=e.getBoundingClientRect(),pr=ov.getBoundingClientRect(),cx=er.left+er.width/2-pr.left,cy=er.top+er.height/2-pr.top,nx=(cx-ox)*sc,ny=(cy-oy)*sc;const fs=parseFloat(window.getComputedStyle(e).fontSize);const ns=fs*sc;let rot=0;const trans=e.style.transform;if(trans.includes('rotate(')){rot=parseFloat(trans.split('rotate(')[1].split('deg)')[0])*Math.PI/180;}ctx.save();ctx.font=`${ns}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.translate(nx,ny);ctx.rotate(rot);ctx.fillText(ch,0,0);ctx.restore()});const blob=await new Promise(r=>cvs.toBlob(r,'image/png'));fd.append('sticker_overlay',blob,'stickers.png')}}
    // Upload live clips
    setProgress(30,'Mengunggah live photo...');
    S.liveClips.forEach((clip,i)=>{if(clip)fd.append('live_clips',clip,`live_${i}.webm`)});
    try{
        setProgress(45,'Menggabungkan foto ke frame...');
        const r=await fetch(`/api/session/${S.sid}/finalize`,{method:'POST',body:fd});
        setProgress(75,'Membuat GIF animasi...');
        if(!r.ok){const et=await r.text();throw new Error(et||'Finalize failed')}
        const d=await r.json();
        setProgress(95,'Hampir selesai...');
        S.stripUrl=d.strip_url||'';S.gifUrl=d.gif_url||'';if(d.qr_b64)$('done-qr').innerHTML=`<img src="data:image/png;base64,${d.qr_b64}">`;noloader();stopTimer();show('done');doneToggle('photo')
    }catch(e){noloader();showModal('Gagal',e.message,'⚠️')}
}

// Done toggles
function doneToggle(type){
    ['photo','live','gif'].forEach(t=>{$('dt-'+t).classList.toggle('on',t===type)});
    const scr=document.querySelector('.donePhScr');
    // Clean up old object URLs
    scr.querySelectorAll('video[src]').forEach(v=>{try{URL.revokeObjectURL(v.src)}catch(_){}});

    if(type==='photo'){
        scr.innerHTML=`<img src="${S.stripUrl}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:3px">`;
    }
    else if(type==='gif'){
        scr.innerHTML=`<img src="${S.gifUrl||S.stripUrl}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:3px">`;
    }
    else if(type==='live'){
        const f=S.frame;
        if(!f||!S.liveClips.some(c=>c)){
            scr.innerHTML=`<img src="${S.stripUrl}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:3px">`;
            return;
        }
        // Render frame with video in each slot
        let h=`<div class="framePrev" style="width:100%;aspect-ratio:${f.width}/${f.height};max-height:100%">`;
        h+=`<img class="frameImg" src="${f.thumb}">`;
        f.slots.forEach((s,i)=>{
            const l=(s.x/f.width*100).toFixed(2),t=(s.y/f.height*100).toFixed(2),w=(s.w/f.width*100).toFixed(2),hh=(s.h/f.height*100).toFixed(2);
            let c='';
            if(S.liveClips[i]){
                c=`<video src="${S.liveUrls[i]}" autoplay loop muted playsinline style="width:100%;height:100%;object-fit:cover"></video>`;
            }else if(S.photos[i]){
                c=`<img src="${S.photoUrls[i]}" style="width:100%;height:100%;object-fit:cover">`;
            }
            h+=`<div class="slotWrap" style="left:${l}%;top:${t}%;width:${w}%;height:${hh}%">${c}</div>`;
        });
        h+='</div>';
        scr.innerHTML=h;
    }
}
