# -*- coding: utf-8 -*-
"""构建 PV 素材：图片卡片、文字梗卡、节拍吸附时间线"""
import json, math, os, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(ROOT, 'assets')
os.makedirs(A, exist_ok=True)

# ---------- 字体 ----------
F_TITLE   = r'C:\Windows\Fonts\STXINGKA.TTF'          # 华文行楷（标题）
F_LYRIC   = r'C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf'
F_MED     = r'C:\Windows\Fonts\Noto Sans SC Medium (TrueType).otf'
F_REG     = r'C:\Windows\Fonts\NotoSansSC-VF.ttf'
F_XINWEI  = r'C:\Windows\Fonts\STXINWEI.TTF'

def font(path, size):
    return ImageFont.truetype(path, size)

# ---------- 节拍网格 (analyze_beats.py 产出; 无 grid.json 时用实测默认值) ----------
_default = dict(beat0=0.3893, period=0.4876)
_grid = _default
if os.path.exists(os.path.join(A, 'grid.json')):
    _grid = json.load(open(os.path.join(A, 'grid.json'), encoding='utf-8'))
BEAT0, PERIOD = _grid['beat0'], _grid['period']
BPM = 60.0/PERIOD

def snap(t):
    """把时间吸附到最近的节拍点"""
    k = round((t - BEAT0)/PERIOD)
    return BEAT0 + k*PERIOD

# ---------- 解析 LRC ----------
lrc_lines = []
with open(os.path.join(ROOT, 'w.lrc'), encoding='utf-8') as fp:
    for ln in fp:
        m = re.match(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)', ln.strip())
        if m:
            t = int(m.group(1))*60 + float(m.group(2))
            txt = m.group(3).strip()
            lrc_lines.append((t, txt))
# 跳过元信息行（00:00-00:02 的歌手/词曲信息另行使用）
meta = {t: txt for t, txt in lrc_lines if t <= 5}
lyrics = [(t, txt) for t, txt in lrc_lines if t > 5]
print("歌词行数:", len(lyrics))

# ---------- 歌词 -> 节拍吸附 + 归属图片 ----------
# 归属：verse1/chorus2 同映射；rap 段穿插小卡
IMG_MAP_VERSE = ['shiman', 'shiguang', 'chuying', 'shiguang',
                 'shiman', 'chuying', 'zhayu', 'zhayu']
IMG_MAP_RAP = ['chuying', 'zouzou', 'zhayu', 'shiguang',
               'shiman', 'chuying', 'zouzou', 'zhayu',
               'shiguang', 'chuying', 'zouzou', 'shiman',
               'zhayu', 'chuying', 'shiguang', 'zhayu']

# 划分段落
rap_start, rap_end = 79.0, 110.5
chorus2_start = 110.5
scenes = []
for i, (t, txt) in enumerate(lyrics):
    st = snap(t)
    nt = snap(lyrics[i+1][0]) if i+1 < len(lyrics) else st + 4*PERIOD*2
    if t < 17:      # 元信息行跳过
        continue
    if t < rap_start:      # verse1
        scenes.append(dict(kind='lyric', sec='v1', t=st, tnext=nt, text=txt,
                           img=IMG_MAP_VERSE[len([s for s in scenes if s['sec']=='v1'])]))
    elif t < rap_end:      # rap
        ridx = len([s for s in scenes if s['sec']=='rap'])
        scenes.append(dict(kind='lyric', sec='rap', t=st, tnext=nt, text=txt,
                           img=IMG_MAP_RAP[ridx]))
    else:                  # chorus2
        cidx = len([s for s in scenes if s['sec']=='c2'])
        scenes.append(dict(kind='lyric', sec='c2', t=st, tnext=nt, text=txt,
                           img=IMG_MAP_VERSE[cidx]))

for s in scenes:
    print(f"{s['sec']} {s['t']:7.3f} -> {s['tnext']:7.3f} [{s['img']}] {s['text']}")

with open(os.path.join(A, 'timeline.json'), 'w', encoding='utf-8') as fp:
    json.dump(dict(beat0=BEAT0, period=PERIOD, bpm=BPM, scenes=scenes), fp, ensure_ascii=False, indent=1)

# ---------- 图片卡片 ----------
def rounded(img, rad, border=6, bcolor=(255,255,255,235)):
    w, h = img.size
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w-1, h-1], rad, fill=255)
    base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    base.paste(img, (0, 0), mask if img.mode != 'RGBA' else Image.composite(img.split()[-1], Image.new('L',(w,h),0), mask))
    # 简化：直接用 mask 粘贴
    base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if img.mode == 'RGBA':
        base.paste(img, (0,0), mask)
    else:
        base.paste(img.convert('RGB'), (0,0), mask)
    if border:
        d2 = ImageDraw.Draw(base)
        d2.rounded_rectangle([border//2, border//2, w-1-border//2, h-1-border//2], rad, outline=bcolor, width=border)
    return base

def make_card(img, target_w, caption=None, cap_h=76, rad=22, sharpen=True, border=True):
    """等比裁切到目标宽度、圆角、白边、底部字幕条、投影 -> 返回带 padding 的 RGBA"""
    im = img.convert('RGB')
    w, h = im.size
    tw = target_w
    th = int(round(h * tw / w))
    im = im.resize((tw, th), Image.LANCZOS)
    if sharpen and tw >= 400:
        im = im.filter(ImageFilter.UnsharpMask(radius=3, percent=90, threshold=2))
    if caption:
        canvas = Image.new('RGB', (tw, th + cap_h), (12, 8, 10))
        canvas.paste(im, (0, 0))
        d = ImageDraw.Draw(canvas)
        f = font(F_LYRIC, int(cap_h*0.52))
        bbox = d.textbbox((0,0), caption, font=f)
        tx = (tw - (bbox[2]-bbox[0]))//2
        ty = th + (cap_h - (bbox[3]-bbox[1]))//2 - bbox[1]
        # 描边
        for dx in (-2,0,2):
            for dy in (-2,0,2):
                d.text((tx+dx, ty+dy), caption, font=f, fill=(255,255,255,255),
                       stroke_width=0)
        d.text((tx, ty), caption, font=f, fill=(255, 230, 230))
        im = canvas
    im = rounded(im, rad, border=6 if border else 0)
    pad = 34
    out = Image.new('RGBA', (im.width + pad*2, im.height + pad*2), (0,0,0,0))
    sh = Image.new('RGBA', out.size, (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.rounded_rectangle([pad+6, pad+10, pad+im.width+6, pad+im.height+10], rad, fill=(0,0,0,170))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    out = Image.alpha_composite(out, sh)
    out.paste(im, (pad, pad), im)
    return out

# 加载原图
shot1 = Image.open(os.path.join(A, 'shot1.jpg'))     # 时光大哭
shot2 = Image.open(os.path.join(A, 'shot2.jpg'))     # 老叟戏顽童
chuying_src = Image.open(os.path.join(A, 'meme_small.png'))   # 褚嬴原版·微笑 (真人剧) 256x250
zhayu_src = Image.open(os.path.join(A, 'avatar.png'))         # 褚嬴炸鱼梗图 (我就炸鱼你气不气) 176x176

# 炸鱼梗图: 4x 放大 + 锐化
zhayu_big = zhayu_src.convert('RGB').resize((zhayu_src.width*4, zhayu_src.height*4), Image.LANCZOS)
zhayu_big = zhayu_big.filter(ImageFilter.UnsharpMask(radius=4, percent=110, threshold=2))
# 原版: 2.5x 放大 + 轻锐化
av_w = int(chuying_src.width*2.5); av_h = int(chuying_src.height*2.5)
avatar_big = chuying_src.convert('RGB').resize((av_w, av_h), Image.LANCZOS)
avatar_big = avatar_big.filter(ImageFilter.UnsharpMask(radius=3, percent=70, threshold=2))

cards = {}
cards['shiguang'] = make_card(shot1, 900, caption='时光：谁在乎啊！！')
cards['shiman']   = make_card(shot2, 860, caption='棋魂 · 官方盖章名场面')
cards['zhayu']    = make_card(zhayu_big, 560, caption='褚嬴 · 快乐炸鱼')
cards['chuying']  = make_card(avatar_big, 560, caption='褚嬴（原版·微笑）')

# ---------- 生成"余亮：你走"文字梗卡 ----------
def make_zou_card(size=(700, 640)):
    W, H = size
    img = Image.new('RGB', (W, H), (10, 14, 24))
    d = ImageDraw.Draw(img)
    # 竖向冷蓝渐变
    for yy in range(H):
        k = yy/H
        d.line([(0, yy), (W, yy)], fill=(int(10+16*k), int(14+24*k), int(24+46*k)))
    # 围棋盘淡纹理
    fnt_grid = ImageDraw.Draw(img)
    step = W//10
    for gx in range(1, 10):
        fnt_grid.line([(gx*step, 40), (gx*step, H-40)], fill=(46, 58, 84), width=2)
    for gy in range(1, 9):
        fnt_grid.line([(40, gy*(H-80)//8+40), (W-40, gy*(H-80)//8+40)], fill=(46, 58, 84), width=2)
    # 大字"你走"
    f = font(F_LYRIC, 330)
    txt = '你走'
    bbox = d.textbbox((0,0), txt, font=f)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    tx, ty = (W-tw)//2 - bbox[0], (H-th)//2 - 90 - bbox[1]
    # 冷蓝光晕
    glow = Image.new('RGBA', (W, H), (0,0,0,0))
    gd = ImageDraw.Draw(glow)
    gd.text((tx, ty), txt, font=f, fill=(120, 180, 255, 220))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')
    d = ImageDraw.Draw(img)
    for dx in range(-6, 7, 2):
        for dy in range(-6, 7, 2):
            d.text((tx+dx, ty+dy), txt, font=f, fill=(20, 40, 80))
    d.text((tx, ty), txt, font=f, fill=(235, 244, 255))
    # 两颗棋子
    def stone(cx, cy, r, dark=True):
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(18,18,20) if dark else (238,238,240),
                  outline=(90,90,100) if dark else (150,150,160), width=3)
        d.ellipse([cx-r*0.45, cy-r*0.55, cx-r*0.05, cy-r*0.2],
                  fill=(70,70,78) if dark else (255,255,255))
    stone(120, H-92, 46, True)
    stone(216, H-92, 46, False)
    # 署名
    d.text((W-56, H-92), '—— 余亮', font=font(F_MED, 44), fill=(200, 214, 235), anchor='rm')
    # 黑条标题
    d.rounded_rectangle([28, 26, 250, 82], 12, fill=(0, 0, 0, 200))
    d.text((139, 54), '名场面', font=font(F_LYRIC, 40), fill=(255, 255, 255), anchor='mm')
    return img

cards['zouzou'] = make_card(make_zou_card(), 560, caption=None)

# 存卡片
for k, v in cards.items():
    v.save(os.path.join(A, f'card_{k}.png'))
    print('card', k, v.size)

# ---------- 标题层（行楷） ----------
def text_layer(txt, fpath, size, fill=(255,255,255,255), stroke=0, sfill=(0,0,0,255), glow=None, glow_r=14):
    f = font(fpath, size)
    dummy = Image.new('RGBA', (10,10))
    bb = ImageDraw.Draw(dummy).textbbox((0,0), txt, font=f, stroke_width=stroke)
    W, H = bb[2]-bb[0]+80, bb[3]-bb[1]+80
    layer = Image.new('RGBA', (W, H), (0,0,0,0))
    d = ImageDraw.Draw(layer)
    ox, oy = 40-bb[0], 40-bb[1]
    if glow:
        glow_img = Image.new('RGBA', (W, H), (0,0,0,0))
        ImageDraw.Draw(glow_img).text((ox, oy), txt, font=f, fill=glow, stroke_width=stroke, stroke_fill=glow)
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(glow_r))
        layer = Image.alpha_composite(layer, glow_img)
    d = ImageDraw.Draw(layer)
    d.text((ox, oy), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill)
    return layer

# 标题字逐字层
title_chars = []
for ch in '忘川彼岸':
    title_chars.append(text_layer(ch, F_TITLE, 300, fill=(255, 245, 244, 255), glow=(255, 30, 50, 160), glow_r=22))
sub_title = text_layer('· DJ 名龙版 ·', F_TITLE, 110, fill=(255, 120, 130, 255), glow=(255, 30, 50, 120), glow_r=14)
artist = text_layer('零一九零贰', F_MED, 64, fill=(235, 225, 225, 255))
credit = text_layer('作词：浮生   作曲：浮生', F_REG, 44, fill=(200, 180, 180, 255))
warn = text_layer('前方梗图高能预警', F_LYRIC, 56, fill=(255, 200, 90, 255), glow=(255, 120, 0, 120), glow_r=10)
for name, layer in [('t1', title_chars[0]), ('t2', title_chars[1]), ('t3', title_chars[2]), ('t4', title_chars[3]),
                    ('sub', sub_title), ('artist', artist), ('credit', credit), ('warn', warn)]:
    layer.save(os.path.join(A, f'layer_{name}.png'))

# outro 文本层
end_title = text_layer('忘川彼岸', F_TITLE, 200, fill=(255,245,244,255), glow=(255,30,50,150), glow_r=18)
end_sub   = text_layer('DJ 名龙版 · 完', F_TITLE, 84, fill=(255,140,150,255))
end_credit= text_layer('棋魂梗图友情出演 · ZCode 渲染', F_REG, 40, fill=(190,170,170,255))
recap1    = text_layer('等到最后，她还是没有回头看', F_LYRIC, 72, fill=(255,210,210,255), glow=(255,40,60,110), glow_r=10)
recap2    = text_layer('本局 · 棋谱回顾', F_LYRIC, 64, fill=(255,215,150,255))
recap3    = text_layer('棋逢对手 · 来日方长', F_TITLE, 110, fill=(240,225,225,255), glow=(255,30,50,110), glow_r=14)
drop_tag  = text_layer('间奏 · 梗图时刻', F_LYRIC, 58, fill=(255,215,140,255), glow=(255,120,0,110), glow_r=10)
rap_tag   = text_layer('RAP!', F_LYRIC, 90, fill=(255,240,120,255), glow=(255,160,0,140), glow_r=12)
for name, layer in [('end_title', end_title), ('end_sub', end_sub), ('end_credit', end_credit),
                    ('recap1', recap1), ('recap2', recap2), ('recap3', recap3),
                    ('drop_tag', drop_tag), ('rap_tag', rap_tag)]:
    layer.save(os.path.join(A, f'layer_{name}.png'))

# ---------- 歌词层（大字 + 描边，双层：底/亮） ----------
def lyric_layers(txt, size=112):
    base = text_layer(txt, F_LYRIC, size, fill=(255, 235, 235, 255), stroke=10, sfill=(60, 8, 14, 255),
                      glow=(255, 25, 45, 130), glow_r=16)
    hi = text_layer(txt, F_LYRIC, size, fill=(255, 240, 120, 255), stroke=10, sfill=(90, 20, 8, 255))
    return base, hi

lyric_store = {}
for s in scenes:
    key = f"L{int(s['t']*1000)}"
    if key in lyric_store: continue
    b, h = lyric_layers(s['text'], 112 if len(s['text']) <= 10 else 92)
    b.save(os.path.join(A, f'ly_{key}_base.png'))
    h.save(os.path.join(A, f'ly_{key}_hi.png'))
    lyric_store[key] = 1
print("歌词层:", len(lyric_store))

# ---------- 花瓣 sprite ----------
petals = []
rng = np.random.default_rng(7)
for i in range(8):
    w, h = int(18+rng.integers(0, 14)), int(34+rng.integers(0, 26))
    p = Image.new('RGBA', (w*2, h*2), (0,0,0,0))
    d = ImageDraw.Draw(p)
    col = [(208, 16, 32), (176, 8, 28), (232, 48, 64), (150, 6, 22)][i % 4]
    d.ellipse([w//2, h//4, w + w//2, h + h//2 - h//5], fill=col + (235,))
    d.ellipse([w//2 + w//3, h//4 + h//6, w + w//2 - w//6, h//2 + h//5], fill=(255, 120, 130, 120))
    p = p.resize((w, h), Image.LANCZOS).rotate(rng.integers(0, 180), expand=True, resample=Image.BICUBIC)
    petals.append(p)
for i, p in enumerate(petals):
    p.save(os.path.join(A, f'petal_{i}.png'))

print('DONE assets')
