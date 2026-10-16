# -*- coding: utf-8 -*-
"""샘플 공급사 송장 이미지(PNG) 생성 — Multimodal 심화 데모용.
시스템 python3(PIL 필요)로 1회 실행:  python3 setup/make_sample_invoice.py
결과: setup/sample_invoice.png (에이전트가 '보고' 품목/수량/금액을 추출하는 대상)
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_invoice.png")

def font(size, bold=False):
    # 맥 기본 한글 폰트
    for p in ["/System/Library/Fonts/AppleSDGothicNeo.ttc",
              "/System/Library/Fonts/Supplemental/AppleGothic.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size, index=(2 if bold else 0))
            except Exception:
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()

W, H = 760, 520
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)

ACCENT = (11, 102, 227)
GRAY = (90, 90, 90)
LINE = (210, 210, 210)

# 헤더
d.rectangle([0, 0, W, 72], fill=ACCENT)
d.text((28, 20), "공급사 송장  SUPPLIER INVOICE", font=font(26, True), fill="white")

# 메타
d.text((28, 92),  "공급사(Supplier): S1  ·  Global Materials Co.", font=font(18), fill=(30, 30, 30))
d.text((28, 120), "송장번호(Invoice No.): INV-2026-1012-A", font=font(16), fill=GRAY)
d.text((28, 144), "일자(Date): 2026-10-12", font=font(16), fill=GRAY)

# 표 헤더
y = 190
d.rectangle([28, y, W-28, y+34], fill=(240, 244, 252))
cols = [("품목코드", 40), ("품명", 150), ("수량", 360), ("단가(USD)", 470), ("금액(USD)", 610)]
for label, x in cols:
    d.text((x, y+8), label, font=font(15, True), fill=(40, 40, 40))

# 표 본문 1행
y += 34
d.line([28, y, W-28, y], fill=LINE)
row = [("A", 40), ("수입 원자재", 150), ("300", 370), ("12.00", 480), ("3,600.00", 620)]
for val, x in row:
    d.text((x, y+10), val, font=font(16), fill=(20, 20, 20))

y += 46
d.line([28, y, W-28, y], fill=LINE)

# 비고/조건
d.text((28, y+22), "리드타임(Lead time): 21일", font=font(16), fill=(30, 30, 30))
d.text((28, y+48), "비고: 500개 이상 주문 시 8% 할인 적용", font=font(16), fill=(30, 30, 30))

# 합계
d.rectangle([W-320, y+84, W-28, y+128], outline=ACCENT, width=2)
d.text((W-305, y+96), "합계(Total)", font=font(16, True), fill=GRAY)
d.text((W-150, y+94), "USD 3,600.00", font=font(20, True), fill=ACCENT)

img.save(OUT)
print("saved:", OUT, img.size)
