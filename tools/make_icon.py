"""assets/icon.png ve assets/icon.ico dosyalarını üretir."""
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
c1, c2 = (79, 140, 255), (189, 123, 255)
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=255)
img.paste(grad, (0, 0), mask)

over = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(over)
cx, cy = 430, 420
for r, w, a in ((250, 26, 110), (170, 30, 180)):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, a), width=w)
d.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], fill=(255, 255, 255, 255))
img = Image.alpha_composite(img, over)

d = ImageDraw.Draw(img)
ax, ay = 470, 460
d.polygon([(ax, ay), (ax, ay + 420), (ax + 105, ay + 320), (ax + 175, ay + 470), (ax + 250, ay + 438),
           (ax + 180, ay + 290), (ax + 320, ay + 290)], fill=(17, 24, 39, 255))
d.polygon([(ax + 30, ay + 70), (ax + 30, ay + 345), (ax + 110, ay + 268), (ax + 185, ay + 425),
           (ax + 212, ay + 413), (ax + 138, ay + 258), (ax + 245, ay + 258)], fill=(255, 255, 255, 255))
img.save("assets/icon.png")
img.resize((256, 256), Image.LANCZOS).save(
    "assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ok")
