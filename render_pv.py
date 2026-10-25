# -*- coding: utf-8 -*-
"""忘川彼岸(DJ名龙版) x 棋魂梗图 PV 渲染器
1920x1080 @30fps, 所有动效锁 123.05BPM 节拍网格, 输出 rawvideo 给 ffmpeg
"""
import json, math, os, subprocess, sys
import numpy as np
import cv2
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(ROOT, 'assets')
W, H, FPS = 1920, 1080, 30
DUR = 180.05
NF = int(DUR * FPS)

TL = json.load(open(os.path.join(A, 'timeline.json'), encoding='utf-8'))
BEAT0, PERIOD, BPM = TL['beat0'], TL['period'], TL['bpm']
BAR = PERIOD * 4
SCENES = TL['scenes']

INTRO_END = SCENES[0]['t']            # 16.968
V1_END = SCENES[7]['t'] + 2*BAR       # 主歌8句后 2 小节收束
RAP_START = next(s['t'] for s in SCENES if s['sec'] == 'rap')
RAP_END = C2_START = next(s['t'] for s in SCENES if s['sec'] == 'c2')
C2_END = SCENES[-1]['tnext']
N_V1 = len([s for s in SCENES if s['sec'] == 'v1'])

def bar_t(k): return BEAT0 + BAR * k
def beats_between(a, b): 
    k0 = math.ceil((a - BEAT0) / PERIOD - 1e-6); k1 = int((b - BEAT0) / PERIOD)
    return [BEAT0 + PERIOD * k for k in range(k0, k1 + 1)]

# ---------- 音频驱动的每拍力度 ----------
kick_t = np.load(os.path.join(A, 'flux_t.npy'))
kick_v = np.load(os.path.join(A, 'flux_low.npy'))
def kick_at(t):
    i = int(t * (22050/256))
    if 0 <= i < len(kick_v): return float(kick_v[i])
    return 0.0
beats_all = beats_between(0, DUR)
kick_str = np.array([min(1.0, kick_at(b)*1.6) for b in beats_all])

# ---------- 载入素材 ----------
def load_rgba(name):
    im = Image.open(os.path.join(A, name)).convert('RGBA')
    arr = np.asarray(im).astype(np.float32)
    return arr[..., :3][..., ::-1].copy(), arr[..., 3:4].astype(np.float32) / 255.0  # BGR, A

CARDS, CARD_A = {}, {}
for k in ['shiguang', 'shiman', 'zhayu', 'chuying', 'zouzou']:
    CARDS[k], CARD_A[k] = load_rgba(f'card_{k}.png')

LAYERS, LAYER_A = {}, {}
for k in ['t1', 't2', 't3', 't4', 'sub', 'artist', 'credit', 'warn',
          'end_title', 'end_sub', 'end_credit', 'recap1', 'recap2', 'recap3',
          'drop_tag', 'rap_tag']:
    LAYERS[k], LAYER_A[k] = load_rgba(f'layer_{k}.png')

# 歌词双层
LYR = {}
for s in SCENES:
    key = f"L{int(s['t']*1000)}"
    if key in LYR: continue
    b, ba = load_rgba(f'ly_{key}_base.png')
    h, ha = load_rgba(f'ly_{key}_hi.png')
    LYR[key] = (b, ba, h, ha)

PETALS = []
for i in range(8):
    rgb, a = load_rgba(f'petal_{i}.png')
    PETALS.append((rgb, a))

# ---------- 背景 / 暗角 ----------
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
cx, cy = W/2, H*0.42
r = np.sqrt(((xx-cx)/(W*0.75))**2 + ((yy-cy)/(H*0.75))**2)
glow = np.clip(1-r, 0, 1)**2
bg = np.zeros((H, W, 3), np.float32)
bg[..., 0] = 4 + 20*glow      # B
bg[..., 1] = 3 + 7*glow      # G
bg[..., 2] = 12 + 74*glow     # R
bg = bg.astype(np.uint8)
BG_F = bg.astype(np.float32)

vin = np.clip((r-0.55)/0.45, 0, 1)**1.6
VIN = (vin * 0.82)[..., None].astype(np.float32)
DARK = (BG_F * (1 - VIN)).astype(np.uint8)  # 静态底图(带暗角) 不对——暗角要叠加在内容上
VIG_MUL = (1 - vin*0.72).astype(np.float32)[..., None]  # 内容乘法暗角

# ---------- 花瓣池 ----------
NP_PETAL = 90
rng0 = np.random.default_rng(7)
p_x = rng0.uniform(0, W, NP_PETAL); p_y = rng0.uniform(-H, H, NP_PETAL)
p_sp = rng0.uniform(55, 150, NP_PETAL); p_dr = rng0.uniform(-45, 45, NP_PETAL)
p_sw = rng0.uniform(18, 52, NP_PETAL); p_ph = rng0.uniform(0, 6.28, NP_PETAL)
p_sz = rng0.uniform(0.7, 1.5, NP_PETAL); p_idx = rng0.integers(0, 8, NP_PETAL)
PETAL_BURST = 0.0  # 突发风速

def draw_petals(canvas, t, dt, intensity):
    global p_y, p_x, PETAL_BURST
    spd = 1.0 + intensity*1.6 + PETAL_BURST
    p_y += (p_sp*spd) * dt
    p_x += (p_dr + np.sin(t*1.7 + p_ph)*p_sw) * dt
    PETAL_BURST *= 0.92
    for i in range(NP_PETAL):
        if p_y[i] > H + 60:
            p_y[i] = rng0.uniform(-160, -40); p_x[i] = rng0.uniform(0, W)
        xi, yi = int(p_x[i]), int(p_y[i])
        if xi < -60 or xi > W+60 or yi < -60: continue
        rgb, a = PETALS[p_idx[i]]
        if p_sz[i] != 1.0:
            nw, nh = max(2, int(rgb.shape[1]*p_sz[i])), max(2, int(rgb.shape[0]*p_sz[i]))
            sp = cv2.resize(rgb, (nw, nh)); sa = cv2.resize(a, (nw, nh))[..., None]
        else:
            sp, sa = rgb, a
        x0, y0 = xi - sp.shape[1]//2, yi - sp.shape[0]//2
        x1, y1 = x0 + sp.shape[1], y0 + sp.shape[0]
        sx0, sy0 = max(0, -x0), max(0, -y0)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W, x1), min(H, y1)
        if x1 <= x0 or y1 <= y0: continue
        reg = canvas[y0:y1, x0:x1].astype(np.float32)
        s = sp[sy0:sy0+y1-y0, sx0:sx0+x1-x0]; sa2 = sa[sy0:sy0+y1-y0, sx0:sx0+x1-x0]
        canvas[y0:y1, x0:x1] = (reg*(1-sa2) + s*sa2).astype(np.uint8)

# ---------- 合成工具 ----------
def blend(canvas, rgb, a, x, y, alpha_mul=1.0):
    """把 rgba 层按左上角(x,y)混合到 canvas"""
    h, w = a.shape[:2]
    x0, y0 = int(x), int(y)
    x1, y1 = x0 + w, y0 + h
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0: return
    reg = canvas[y0:y1, x0:x1].astype(np.float32)
    s = rgb[sy0:sy0+y1-y0, sx0:sx0+x1-x0]
    sa = a[sy0:sy0+y1-y0, sx0:sx0+x1-x0] * alpha_mul
    canvas[y0:y1, x0:x1] = (reg*(1-sa) + s*sa).astype(np.uint8)

def draw_scaled(canvas, key, cx, cy, scale, alpha=1.0, rot=0.0, rgb=None, amap=None):
    """以中心(cx,cy)、缩放、旋转绘制卡片/图层"""
    if rgb is None: rgb, amap = CARDS[key], CARD_A[key]
    h, w = amap.shape[:2]
    nw, nh = max(2, int(w*scale)), max(2, int(h*scale))
    if abs(nw-w) < 2: sr, sa = rgb, amap
    else:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        sr = cv2.resize(rgb, (nw, nh), interpolation=interp)
        sa = cv2.resize(amap, (nw, nh), interpolation=interp)[..., None]
    if rot != 0.0:
        pil = Image.fromarray(cv2.cvtColor(sr, cv2.COLOR_BGR2RGBA) if False else np.dstack([sr, sa*255]).astype(np.uint8))
        pil = pil.rotate(rot, expand=True, resample=Image.BICUBIC)
        arr = np.asarray(pil).astype(np.float32)
        sr, sa = arr[..., :3][..., ::-1].copy(), arr[..., 3:4]/255.0
        nw, nh = sr.shape[1], sr.shape[0]
    blend(canvas, sr, sa, cx - nw/2, cy - nh/2, alpha)

def ease_out_quint(p): return 1 - (1-p)**5
def ease_out_back(p, s=1.9):
    p -= 1; return 1 + p*p*((s+1)*p + s)
def clamp01(x): return max(0.0, min(1.0, x))

# 节拍相位: 距上一拍的进度 0..1
def beat_phase(t):
    ph = (t - BEAT0) / PERIOD
    return ph - math.floor(ph)
def bar_phase(t):
    ph = (t - BEAT0) / BAR
    return ph - math.floor(ph)
def pulse_env(t, decay=5.0):
    return math.exp(-decay * beat_phase(t))

# ---------- 间奏 montage ----------
drop_slots = []
t = bar_t(math.ceil((V1_END + 0.3 - BEAT0)/BAR))
MONT_CARDS = ['zhayu', 'zouzou', 'shiguang', 'shiman', 'chuying']
MONT_EFF = ['slam', 'slideR', 'tilt', 'spin', 'shake', 'rgb', 'slideL', 'bounce']
mi = 0
while t < RAP_START - 0.4:
    tend = min(t + BAR, RAP_START)
    if tend - t > BAR*0.45:
        drop_slots.append(dict(t0=t, t1=tend, card=MONT_CARDS[mi % 5], eff=MONT_EFF[mi % 8]))
        mi += 1
    t += BAR

# ---------- 歌词场景辅助 ----------
def scene_at(t):
    for s in SCENES:
        if s['t'] <= t < s['tnext'] + 0.35:
            return s
    return None

V1S = [s for s in SCENES if s['sec'] == 'v1']
C2S = [s for s in SCENES if s['sec'] == 'c2']
RAPS = [s for s in SCENES if s['sec'] == 'rap']

# ================= 渲染循环 =================
PREVIEW = None
if len(sys.argv) > 2 and sys.argv[1] == 'preview':
    PREVIEW = set(int(x) for x in sys.argv[2].split(','))
    out_name = None
else:
    out_name = '忘川彼岸DJ·棋魂梗图PV.mp4'
if out_name:
    cmd = ['ffmpeg', '-y', '-v', 'error',
           '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', 'pipe:',
           '-i', os.path.join(A, 'audio_full.m4a'),
           '-map', '0:v', '-map', '1:a',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart',
           out_name]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
else:
    proc = None

INTENSITY = {'v1': 0.72, 'rap': 0.92, 'c2': 1.0, 'outro': 0.32}

def sec_of(t):
    if t < INTRO_END: return 'intro'
    if t < V1_END: return 'v1'
    if t < RAP_START: return 'drop'
    if t < C2_START: return 'rap'
    if t < C2_END: return 'c2'
    return 'outro'

rng = np.random.default_rng(123)
_tw = [LAYER_A[f't{i+1}'].shape[1] for i in range(4)]   # 含 80px padding
_glyph = min(_tw) - 80
_step = 0.62 * _glyph
_total = 3*_step + _glyph
_first = 960 - _total/2 + _glyph/2
TITLE_POS = [(_first + i*_step, 430) for i in range(4)]
TITLE_BEAT = [2, 4, 6, 8]

for fi in range(NF):
    t = fi / FPS
    dt = 1.0 / FPS
    sec = sec_of(t)
    inten = INTENSITY.get(sec, 0.6) if sec in INTENSITY else (0.55 if sec == 'intro' else 0.32)
    if sec == 'intro': inten = 0.45 + 0.5*clamp01((t-11)/5.5)
    bp = beat_phase(t); brp = bar_phase(t)
    pk = pulse_env(t, 5.0)
    bar_pk = math.exp(-4.0*brp)
    # 每拍力度
    bi = min(len(kick_str)-1, max(0, int(round((t-BEAT0)/PERIOD - 0.5))))
    kv = kick_str[bi] if sec not in ('outro',) else kick_str[bi]*0.6

    canvas = bg.copy()

    # ---------- 背景/全局事件 ----------
    slam_flash = 0.0; rgb_dx = 0; shake_amp = 0.0

    # ---------- 绘制 petals ----------
    draw_petals(canvas, t, dt, inten if sec != 'outro' else 0.25)

    # ================= INTRO =================
    if sec == 'intro':
        # 标题逐字
        for ci in range(4):
            t0 = BEAT0 + PERIOD*TITLE_BEAT[ci]
            if t >= t0 - 0.05:
                p = clamp01((t - t0) / 0.30)
                sc = 2.3 - 1.3*ease_out_back(p)
                al = clamp01(p*2.5)
                cx, cy = TITLE_POS[ci]
                cy += -16*pk
                draw_scaled(canvas, None, cx, cy, sc, al,
                            rgb=LAYERS[f't{ci+1}'], amap=LAYER_A[f't{ci+1}'])
        if t >= BEAT0 + PERIOD*10:
            p = clamp01((t-(BEAT0+PERIOD*10))/0.25)
            draw_scaled(canvas, None, 960, 655+(-8*pk), 0.9+0.1*ease_out_back(p), p,
                        rgb=LAYERS['sub'], amap=LAYER_A['sub'])
        if t >= BEAT0 + PERIOD*12:
            p = clamp01((t-(BEAT0+PERIOD*12))/0.25)
            draw_scaled(canvas, None, 960, 745, 1, p, rgb=LAYERS['artist'], amap=LAYER_A['artist'])
        if t >= BEAT0 + PERIOD*14:
            p = clamp01((t-(BEAT0+PERIOD*14))/0.25)
            draw_scaled(canvas, None, 960, 815, 1, p, rgb=LAYERS['credit'], amap=LAYER_A['credit'])
        # 褚嬴小卡 + 预警
        if t >= BEAT0 + PERIOD*18:
            p = clamp01((t-(BEAT0+PERIOD*18))/0.35)
            sc = 0.42 + 0.04*pk
            draw_scaled(canvas, 'chuying', 1620, 900, sc, p)
        if t >= BEAT0 + PERIOD*20:
            p = clamp01((t-(BEAT0+PERIOD*20))/0.3)
            draw_scaled(canvas, None, 640, 935, 1, p*(0.75+0.25*math.sin(t*6)),
                        rgb=LAYERS['warn'], amap=LAYER_A['warn'])
        # 结尾蓄力: 全屏缓慢推近 + 边缘闪
        if t > INTRO_END - 1.6:
            ramp = clamp01((t-(INTRO_END-1.6))/1.6)
            slam_flash = ramp*0.28
        if t < 0.4:
            g = clamp01(t/0.4)
            canvas[:] = (canvas * g).astype(np.uint8)

    # ================= 主歌 / 副歌: 歌词 + 梗图卡 =================
    if sec in ('v1', 'c2'):
        sc_list = V1S if sec == 'v1' else C2S
        idx_local = next((i for i, s in enumerate(sc_list) if s['t'] <= t < s['tnext']+0.4), None)
        if idx_local is not None:
            s = sc_list[idx_local]
            t_in = t - s['t']
            line_dur = min(s['tnext'], V1_END if sec == 'v1' else C2_END) - s['t']
            # --- 卡片 ---
            p = clamp01(t_in / 0.16)
            sc = 1.45 - 0.45*ease_out_back(p) if t_in < 0.16 else 1.0
            side = -1 if idx_local % 2 == 0 else 1
            ccx = 960 + side*205
            ccy = 415
            csc = 0.80 * (1 + 0.035*pk)
            exit_p = clamp01((t_in - (line_dur-0.14))/0.14) if line_dur > 0.3 else 0
            if exit_p > 0:
                csc *= 1 - 0.25*exit_p
            alpha = p * (1-exit_p)
            if t_in < 0.09: shake_amp = 10*(1-t_in/0.09)
            draw_scaled(canvas, s['img'], ccx, ccy, csc, alpha)
            # --- 歌词 ---
            key = f"L{int(s['t']*1000)}"
            base, base_a, hi, hi_a = LYR[key]
            lw = base_a.shape[1]
            p2 = clamp01(t_in/0.13)
            ly_sc = 1.18 - 0.18*ease_out_back(p2)
            ly_y = 885 + 26*(1-p2) - 7*pk
            lam = p2 * (1 - exit_p)
            nh, nw = int(base_a.shape[0]*ly_sc), int(base_a.shape[1]*ly_sc)
            br = cv2.resize(base, (nw, nh)); ba_ = cv2.resize(base_a, (nw, nh))[..., None]
            blend(canvas, br, ba_, 960-nw/2, ly_y-nh/2, lam)
            # 卡拉OK扫色
            prog = clamp01(t_in / max(0.6, line_dur*0.92))
            cut = int(nw * prog)
            if cut > 0:
                hr = cv2.resize(hi, (nw, nh)); ha_ = cv2.resize(hi_a, (nw, nh))[..., None]
                ha_ = ha_.copy(); ha_[:, cut:] = 0
                blend(canvas, hr, ha_, 960-nw/2, ly_y-nh/2, lam)
            if t_in < 0.06: slam_flash = 0.30
            if sec == 'c2' and brp < 0.06: rgb_dx = 12; shake_amp = max(shake_amp, 7)

    # ================= DJ 间奏: 梗图 montage =================
    if sec == 'drop':
        # 45-49s: 主歌末句卡片保持 + 蓄力推近
        if t < drop_slots[0]['t0']:
            s = V1S[-1]
            t_in = t - s['t']
            p = 1.0
            csc = 0.80*(1+0.035*pk) * (1 + 0.10*clamp01((t-(V1_END-1.9))/1.9))
            draw_scaled(canvas, s['img'], 960, 415, csc, 1.0)
            key = f"L{int(s['t']*1000)}"
            base, base_a, hi, hi_a = LYR[key]
            lw = base_a.shape[1]
            prog = clamp01(t_in/3.6)
            cut = int(lw*prog)
            ba_ = base_a
            blend(canvas, base, base_a, 960-lw/2, 885-base_a.shape[0]/2)
            if cut > 0:
                ha_ = hi_a.copy(); ha_[:, cut:] = 0
                blend(canvas, hi, ha_, 960-lw/2, 885-lw and base_a.shape[0]/2)
            slam_flash = 0.06 + 0.16*clamp01((t-(V1_END-1.0))/1.0)
        else:
            slot = next((d for d in drop_slots if d['t0'] <= t < d['t1']), None)
            if slot:
                tin = t - slot['t0']
                key = slot['card']; eff = slot['eff']
                ccx, ccy, csc, alpha, rot = 960, 470, (1.04 if key in ('zhayu','chuying','zouzou') else 0.92), 1.0, 0.0
                pl = clamp01(tin/0.18)
                if eff == 'slam':
                    csc = 1.7 - 0.7*ease_out_back(pl) if tin < 0.18 else 0.92 + 0.05*pk
                    if tin < 0.07: shake_amp = 16
                elif eff == 'slideR':
                    ccx = 960 + 1100*(1-ease_out_quint(clamp01(tin/0.30)))
                elif eff == 'slideL':
                    ccx = 960 - 1100*(1-ease_out_quint(clamp01(tin/0.30)))
                elif eff == 'tilt':
                    rot = -9*(1-ease_out_quint(clamp01(tin/0.28)))
                    csc = 0.92 + 0.04*pk
                elif eff == 'spin':
                    rot = 200*(1-ease_out_quint(clamp01(tin/0.34)))
                    csc = 1.5 - 0.58*ease_out_quint(clamp01(tin/0.34))
                elif eff == 'shake':
                    csc = 0.95 + 0.05*pk
                    shake_amp = 6
                elif eff == 'rgb':
                    csc = 1.6 - 0.68*ease_out_back(pl) if tin < 0.18 else 0.92
                    if tin < 0.10: rgb_dx = int(18*(1-tin/0.10))
                elif eff == 'bounce':
                    csc = 0.92 + 0.05*pk
                    ccy = 470 + 60*abs(math.sin(tin*7))*math.exp(-tin*2.2)
                draw_scaled(canvas, key, ccx, ccy, csc, alpha, rot)
                if tin < 0.06: slam_flash = 0.32
            # montage 标签
            if t < drop_slots[0]['t0'] + 6.5:
                al = 0.85*math.exp(-3*bar_phase(t)) if t > drop_slots[0]['t0']+5 else 0.9
                draw_scaled(canvas, None, 250 + (-5*pk), 120, 1, al,
                            rgb=LAYERS['drop_tag'], amap=LAYER_A['drop_tag'])
            if brp < 0.05: rgb_dx = max(rgb_dx, 9); shake_amp = max(shake_amp, 8)

    # ================= RAP =================
    if sec == 'rap':
        s = next(x for x in RAPS if x['t'] <= t < x['tnext']+0.4)
        t_in = t - s['t']; line_dur = s['tnext'] - s['t']
        idx_local = RAPS.index(s)
        p = clamp01(t_in/0.12)
        csc = 0.74*(1.35-0.35*ease_out_back(p)) if t_in < 0.12 else 0.74*(1+0.05*pk)
        side = 1 if idx_local % 2 == 0 else -1
        draw_scaled(canvas, s['img'], 960 + side*560, 620, csc, p)
        if t_in < 0.06: slam_flash = 0.22; shake_amp = 8
        # 歌词(顶部)
        key = f"L{int(s['t']*1000)}"
        base, base_a, hi, hi_a = LYR[key]
        lw, lh = base_a.shape[1], base_a.shape[0]
        ly_sc = 0.82
        nw, nh = int(lw*ly_sc), int(lh*ly_sc)
        prog = clamp01(t_in / max(0.5, line_dur*0.9))
        br = cv2.resize(base, (nw, nh)); ba_ = cv2.resize(base_a, (nw, nh))[..., None]
        blend(canvas, br, ba_, 960-nw/2, 165-nh/2 + 16*(1-p) - 5*pk, p)
        cut = int(nw*prog)
        if cut > 0:
            hr = cv2.resize(hi, (nw, nh)); ha_ = cv2.resize(hi_a, (nw, nh))[..., None]
            ha_ = ha_.copy(); ha_[:, cut:] = 0
            blend(canvas, hr, ha_, 960-nw/2, 165-nh/2 + 16*(1-p) - 5*pk, p)
        # RAP! 标签
        if t < RAP_START + 5.5:
            sc2 = 1 + 0.12*math.exp(-6*beat_phase(t))
            draw_scaled(canvas, None, 1750, 130, sc2, 0.9,
                        rgb=LAYERS['rap_tag'], amap=LAYER_A['rap_tag'])
        if brp < 0.05: shake_amp = max(shake_amp, 5)

    # ================= 尾声 =================
    if sec == 'outro':
        o = t - C2_END
        dim = 0.75
        # 回顾1: 时光哭 + 文案
        if o < 8.2:
            csc = 0.72*(1 + 0.02*math.sin(t*1.2))
            draw_scaled(canvas, 'shiguang', 960, 460, csc, 1.0)
            p = clamp01(o/0.5)
            draw_scaled(canvas, None, 960, 915, 1, p*(0.8+0.2*math.sin(t*2.1)),
                        rgb=LAYERS['recap1'], amap=LAYER_A['recap1'])
        # 棋谱回顾 2x2
        elif o < 22.6:
            quad = [(610, 390), (1310, 390), (610, 745), (1310, 745)]
            names = ['shiman', 'shiguang', 'zhayu', 'chuying']
            base_t = 8.2 + (o-8.2)
            for qi, nm in enumerate(names):
                t0 = bar_t(math.ceil((C2_END+9.6-BEAT0)/BAR)) + qi*BAR
                if t >= t0:
                    pl = clamp01((t-t0)/0.22)
                    sc = 0.62*(1.5-0.5*ease_out_back(pl)) if (t-t0) < 0.22 else 0.62
                    draw_scaled(canvas, nm, quad[qi][0], quad[qi][1], sc, pl)
            p2 = clamp01((o-8.2)/0.5)
            draw_scaled(canvas, None, 960, 130, 1, p2,
                        rgb=LAYERS['recap2'], amap=LAYER_A['recap2'])
            if o > 15.5:  # 缓慢整体推近由全局zoom实现
                pass
        # 结语
        elif o < 28.8:
            al = clamp01((o-22.6)/0.6) * (0.9 if o < 27.6 else max(0.0, 0.9*(1-(o-27.6)/1.2)))
            draw_scaled(canvas, None, 960, 500, 1+0.004*(o-22.6), al,
                        rgb=LAYERS['recap3'], amap=LAYER_A['recap3'])
        # 结束卡
        else:
            p = clamp01((o-28.8)/0.8)
            draw_scaled(canvas, None, 960, 430, 1, p,
                        rgb=LAYERS['end_title'], amap=LAYER_A['end_title'])
            draw_scaled(canvas, None, 960, 640, 1, clamp01((o-29.3)/0.6),
                        rgb=LAYERS['end_sub'], amap=LAYER_A['end_sub'])
            draw_scaled(canvas, None, 960, 745, 1, clamp01((o-29.8)/0.6),
                        rgb=LAYERS['end_credit'], amap=LAYER_A['end_credit'])
        if brp < 0.06: shake_amp = max(shake_amp, 3)

    # ---------- 全局节拍推近 (camera pump) ----------
    slam_boost = 0.0
    if t < V1_END and any(abs(t - s['t']) < 0.06 for s in V1S): slam_boost = 0.5
    zoom = 1.0 + (0.030*inten + 0.010*slam_boost)*pk*min(1.0, kv+0.35)
    if sec == 'drop' and t < drop_slots[0]['t0']:
        zoom += 0.05*clamp01((t-(V1_END-1.9))/1.9)
    if zoom > 1.002:
        cw, ch = W/zoom, H/zoom
        x0, y0 = (W-cw)/2, (H-ch)/2
        M = cv2.getRotationMatrix2D((W/2, H/2), 0, zoom)
        M[0, 2] -= x0; M[1, 2] -= y0
        canvas = cv2.warpAffine(canvas, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # ---------- 震屏 ----------
    if shake_amp > 0.3:
        rngf = np.random.default_rng(9000+fi)
        dx, dy = int(rngf.uniform(-shake_amp, shake_amp)), int(rngf.uniform(-shake_amp, shake_amp)*0.6)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        canvas = cv2.warpAffine(canvas, M, (W, H), borderMode=cv2.BORDER_REPLICATE)

    # ---------- RGB 分离 ----------
    if rgb_dx > 0:
        r_ch = canvas[..., 2].copy(); b_ch = canvas[..., 0].copy()
        canvas[..., 2] = np.roll(r_ch, rgb_dx, axis=1)
        canvas[..., 0] = np.roll(b_ch, -rgb_dx, axis=1)

    # ---------- 暗角 ----------
    canvas = (canvas.astype(np.float32) * VIG_MUL).astype(np.uint8)

    # ---------- 闪白 ----------
    flash = slam_flash + (0.085*inten*kv)*math.exp(-6*bp)
    if sec == 'drop' and t < drop_slots[0]['t0']: pass
    if flash > 0.01:
        f = min(0.5, flash)
        canvas = (canvas*(1-f) + 255*f).astype(np.uint8)

    # ---------- 进度条 ----------
    canvas[H-7:, :] = (18, 14, 16)
    pw = int(W * t / DUR)
    canvas[H-7:, :pw] = (36, 34, 208)

    # ---------- 整体淡入淡出 ----------
    g = 1.0
    if t < 0.5: g = t/0.5
    if t > 176.2: g = max(0.0, 1-(t-176.2)/2.0)
    if g < 1.0:
        canvas = (canvas*g).astype(np.uint8)

    if proc is not None:
        proc.stdin.write(canvas.tobytes())
    elif PREVIEW and fi in PREVIEW:
        cv2.imwrite(os.path.join(A, f'pv_frame_{fi:05d}_t{t:07.2f}.jpg'), canvas,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
    if fi % 300 == 0:
        print(f"{fi}/{NF}  t={t:6.2f}s  sec={sec}", flush=True)

if proc is not None:
    proc.stdin.close()
    proc.wait()
    print("RENDER DONE, rc =", proc.returncode)
else:
    print("PREVIEW DONE")
