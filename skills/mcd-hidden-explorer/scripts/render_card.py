#!/usr/bin/env python3
"""Developer-only Pillow renderer. Photos are read locally and never copied out."""
from pathlib import Path
import warnings


def render(submission, number, photo, card, thumbnail, font_path=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    Image.MAX_IMAGE_PIXELS = 24_000_000
    fonts = [font_path] if font_path else [
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']
    font_path = next((str(p) for p in fonts if p and Path(p).is_file()), None)
    if not font_path:
        raise ValueError('缺少中文字体；请通过 --font 指定可用的中文字体文件')
    def font(size):
        return ImageFont.truetype(font_path, size)
    def wrapped(draw, text, face, width):
        result, line = [], ''
        for char in text:
            if char == '\n':
                result.append(line); line = ''; continue
            if line and draw.textlength(line + char, font=face) > width:
                result.append(line); line = ''
            line += char
        if line:
            result.append(line)
        return result
    def block(draw, value, box, maximum, minimum, fill):
        x, y, width, height = box
        for size in range(maximum, minimum - 1, -1):
            face = font(size); lines = wrapped(draw, value, face, width)
            line_height = size + 10
            if len(lines) * line_height <= height:
                for line in lines:
                    draw.text((x, y), line, font=face, fill=fill, anchor='lt'); y += line_height
                return
        raise ValueError('卡面文字过长，请精简 display 中的展示文案；完整步骤仍保留在资料中')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(photo) as original:
            if original.format not in {'PNG', 'JPEG', 'WEBP'} or getattr(original, 'n_frames', 1) != 1:
                raise ValueError('投稿配图只支持静态 PNG/JPEG/WebP')
            original.load()
            photograph = ImageOps.fit(ImageOps.exif_transpose(original).convert('RGB'), (1020, 840))
    red, cream, ink, gold = '#d5281b', '#fff7e2', '#352820', '#dbac56'
    image = Image.new('RGB', (1080, 1440), cream); draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1080, 164), fill=red)
    # Repo-native burger mark; no third-party logo/font files enter the package.
    draw.arc((48, 53, 118, 104), 180, 360, fill='#ffdb66', width=5)
    draw.line((48, 80, 118, 80), fill='#ffdb66', width=5)
    draw.line((48, 97, 118, 97), fill='#ffdb66', width=5)
    draw.arc((48, 87, 118, 122), 0, 180, fill='#ffdb66', width=5)
    draw.text((150, 55), '麦门老吃家', font=font(58), fill='white', anchor='lt')
    draw.line((898, 0, 898, 164), fill=gold, width=2)
    draw.text((926, 34), '唯一编号', font=font(23), fill='#ffe3a4', anchor='lt')
    draw.text((918, 76), 'U{:02d}'.format(number), font=font(55), fill='white', anchor='lt')
    image.paste(photograph, (30, 190))
    draw.rounded_rectangle((28, 188, 1052, 1032), 14, outline=gold, width=3)
    block(draw, submission['title'], (54, 1054, 974, 110), 55, 38, ink)
    draw.text((54, 1176), '餐品', font=font(26), fill=red, anchor='lt')
    block(draw, ' ＋ '.join(submission['display']['products']), (132, 1174, 876, 82), 31, 26, ink)
    draw.line((54, 1260, 780, 1260), fill=gold, width=2)
    draw.text((54, 1280), '做法', font=font(26), fill=red, anchor='lt')
    block(draw, '；'.join(submission['display']['steps']), (132, 1278, 632, 110), 30, 23, ink)
    draw.rounded_rectangle((822, 1270, 1028, 1396), 8, outline=red, width=3)
    draw.text((854, 1285), '麦门', font=font(32), fill=red, anchor='lt')
    draw.text((839, 1323), '老吃家', font=font(35), fill=red, anchor='lt')
    draw.text((851, 1365), '灵感收录', font=font(20), fill=red, anchor='lt')
    # Do not copy a calorie number from a photo. The basket uses official nutrition.
    image.save(card, format='PNG')
    image.resize((360, 480), Image.Resampling.LANCZOS).save(thumbnail, format='PNG')
