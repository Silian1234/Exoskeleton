# Builds the Forge icon variants from in-game screenshots in art/source (1024x1536, dark background).
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

ART = os.path.join(os.path.dirname(__file__), "..", "art")
SRC = os.path.join(ART, "source")
ORDER = [("exo1", "EXO-1"), ("exo2", "EXO-2"), ("exo3", "EXO-3"), ("fba", "FBA")]
BG = (10, 14, 24)


def load(n):
    im = Image.open(os.path.join(SRC, n + ".webp")).convert("RGB")
    return ImageEnhance.Contrast(im).enhance(1.08)


def vignette(im, strength=0.55):
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((-w * 0.15, -h * 0.1, w * 1.15, h * 1.1), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(w * 0.12))
    dark = Image.new("RGB", (w, h), BG)
    return Image.composite(im, Image.blend(im, dark, strength), mask)


def font(size):
    for f in ("C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f): return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def label(im, text, size):
    d = ImageDraw.Draw(im)
    f = font(size)
    w = d.textlength(text, font=f)
    x, y = (im.width - w) / 2, im.height - size * 1.45
    d.text((x + 2, y + 2), text, font=f, fill=(0, 0, 0))
    d.text((x, y), text, font=f, fill=(225, 232, 240))


def crop(im, top, side):  # square crop from head (top) down, `side` px wide, centred
    x0 = (im.width - side) // 2
    return im.crop((x0, top, x0 + side, top + side))


# 1) 2x2 grid: head-to-knee crops
cells = []
for n, t in ORDER:
    c = crop(load(n), 70, 780).resize((512, 512), Image.LANCZOS)
    label(c, t, 54)
    cells.append(c)
grid = Image.new("RGB", (1024, 1024), BG)
for i, c in enumerate(cells):
    grid.paste(c, ((i % 2) * 512, (i // 2) * 512))
d = ImageDraw.Draw(grid)
d.line((512, 0, 512, 1024), fill=(40, 52, 70), width=4)
d.line((0, 512, 1024, 512), fill=(40, 52, 70), width=4)
grid.save(os.path.join(ART, "icon_grid_1024.png"))
grid.resize((512, 512), Image.LANCZOS).save(os.path.join(ART, "icon_grid_512.png"))

# 2) single EXO-3, chest-led crop
one = vignette(crop(load("exo3"), 60, 900)).resize((1024, 1024), Image.LANCZOS)
one.save(os.path.join(ART, "icon_exo3_1024.png"))
one.resize((512, 512), Image.LANCZOS).save(os.path.join(ART, "icon_exo3_512.png"))

# 3) banner: all four, full height
cols = []
for n, t in ORDER:
    im = load(n).crop((172, 40, 852, 1536))   # 680 x 1496
    label(im, t, 72)
    cols.append(im)
banner = Image.new("RGB", (680 * 4, 1496), BG)
for i, c in enumerate(cols):
    banner.paste(c, (i * 680, 0))
banner = vignette(banner, 0.35)
banner.resize((1920, int(1496 * 1920 / 2720)), Image.LANCZOS).save(os.path.join(ART, "banner_lineup.png"))

# preview: how the icons read at search-card size
prev = Image.new("RGB", (128 * 2 + 30, 128 + 20), (30, 34, 44))
prev.paste(grid.resize((128, 128), Image.LANCZOS), (10, 10))
prev.paste(one.resize((128, 128), Image.LANCZOS), (148, 10))
prev.save(os.path.join(ART, "_preview_128.png"))
print("ok")
