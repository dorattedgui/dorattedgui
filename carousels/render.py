#!/usr/bin/env python3
"""
Instagram Carousel Renderer
Editorial-style carousel slides with dark navy brand theme.
Supports accent-colored keywords, handwritten annotations,
curved arrows, grid textures, and rich visual layouts.

Usage:
    python3 render.py <carousel-dir>
    python3 render.py workspace/my-carousel

The carousel directory must contain a config.json file.
Output PNGs are saved in the same directory.
"""

import json
import math
import sys
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# -- Constants ----------------------------------------------------------------

SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1350  # Instagram max portrait

ASSETS_DIR = Path(__file__).parent / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
HEADSHOT_PATH = ASSETS_DIR / "headshot.jpg"

# Brand colors - deep navy theme (customize these to match your brand)
COLORS = {
    "bg_dark": "#0D1B2A",          # Deep navy background
    "bg_card": "#152238",           # Navy card background
    "accent": "#5DCCFF",            # Bright cyan-blue for text accents
    "accent_dark": "#0871B8",       # Darker blue (buttons, bars)
    "accent_secondary": "#E91E63",  # Vibrant magenta-pink
    "white": "#FFFFFF",
    "off_white": "#F0F0F0",         # Near-white for body text
    "cream": "#D4D4D4",
    "gray": "#94A3B8",              # Secondary text
    "light_gray": "#CBD5E1",
    "blue": "#1976D2",              # Gradient bar left
    "red": "#E91E63",               # Gradient bar right
    "grid_line": "#1A2D42",         # Grid overlay lines
}

# Layout
PADDING = 80
CONTENT_WIDTH = SLIDE_WIDTH - (PADDING * 2)
FOOTER_HEIGHT = 80


# -- Font Loading -------------------------------------------------------------

def load_fonts():
    """Load all font families: Inter (sans), Bebas Neue (condensed), Caveat (hand)."""
    inter_ttc = str(FONT_DIR / "Inter.ttc")
    inter_var = str(FONT_DIR / "InterVariable.ttf")
    inter_path = inter_ttc if os.path.exists(inter_ttc) else inter_var
    bebas_path = str(FONT_DIR / "BebasNeue-Regular.ttf")
    caveat_path = str(FONT_DIR / "Caveat.ttf")

    fonts = {}
    is_ttc = inter_path.endswith(".ttc")

    def inter(size, index=3):
        if is_ttc:
            return ImageFont.truetype(inter_path, size, index=index)
        return ImageFont.truetype(inter_path, size)

    def bebas(size):
        return ImageFont.truetype(bebas_path, size)

    def caveat(size):
        return ImageFont.truetype(caveat_path, size)

    try:
        # Bebas Neue headlines
        fonts["headline_xl"] = bebas(148)
        fonts["headline_lg"] = bebas(110)
        fonts["headline_md"] = bebas(72)
        fonts["headline_sm"] = bebas(56)
        fonts["headline_italic"] = bebas(88)

        # Inter body text
        fonts["body_lg"] = inter(50, 7)
        fonts["body"] = inter(46, 7)
        fonts["body_sm"] = inter(36, 6)
        fonts["body_bold"] = inter(46, 7)
        fonts["caption"] = inter(32, 7)
        fonts["handle"] = inter(28, 3)
        fonts["display_name"] = inter(36, 6)

        # Handwritten
        fonts["hand_lg"] = caveat(58)
        fonts["hand_md"] = caveat(48)
        fonts["hand_sm"] = caveat(40)

    except Exception as e:
        print(f"Warning: Font loading issue ({e}), falling back to defaults")
        default = ImageFont.load_default()
        for key in ["headline_xl", "headline_lg", "headline_md", "headline_sm",
                     "headline_italic", "body_lg", "body", "body_sm", "body_bold",
                     "caption", "handle", "display_name", "hand_lg", "hand_md", "hand_sm"]:
            fonts[key] = default

    return fonts


# -- Drawing Helpers ----------------------------------------------------------

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def create_circular_image(image, size):
    big = size * 2
    image = image.resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, big, big), fill=255)
    output = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)
    return output.resize((size, size), Image.LANCZOS)


def draw_grid_texture(img, color="#2A2A2A", spacing=40, alpha=30):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r, g, b = hex_to_rgb(color)
    for x in range(0, SLIDE_WIDTH, spacing):
        draw.line([(x, 0), (x, SLIDE_HEIGHT)], fill=(r, g, b, alpha), width=1)
    for y in range(0, SLIDE_HEIGHT, spacing):
        draw.line([(0, y), (SLIDE_WIDTH, y)], fill=(r, g, b, alpha), width=1)
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def draw_gradient_bar(img, y, height, color_left, color_right):
    left_rgb = hex_to_rgb(color_left)
    right_rgb = hex_to_rgb(color_right)
    pixels = img.load()
    for x in range(SLIDE_WIDTH):
        ratio = x / SLIDE_WIDTH
        r = int(left_rgb[0] + (right_rgb[0] - left_rgb[0]) * ratio)
        g = int(left_rgb[1] + (right_rgb[1] - left_rgb[1]) * ratio)
        b = int(left_rgb[2] + (right_rgb[2] - left_rgb[2]) * ratio)
        for dy in range(height):
            pixels[x, y + dy] = (r, g, b)


def draw_curved_arrow(draw, start, end, color, width=3):
    sx, sy = start
    ex, ey = end
    cx = (sx + ex) // 2 + (ey - sy) // 3
    cy = (sy + ey) // 2 - (ex - sx) // 3
    points = []
    for t_i in range(21):
        t = t_i / 20.0
        x = (1-t)**2 * sx + 2*(1-t)*t * cx + t**2 * ex
        y = (1-t)**2 * sy + 2*(1-t)*t * cy + t**2 * ey
        points.append((x, y))
    for i in range(len(points)-1):
        draw.line([points[i], points[i+1]], fill=hex_to_rgb(color), width=width)
    angle = math.atan2(ey - points[-2][1], ex - points[-2][0])
    arrow_len = 18
    for offset in [-0.5, 0.5]:
        a = angle + math.pi + offset
        ax = ex + arrow_len * math.cos(a)
        ay = ey + arrow_len * math.sin(a)
        draw.line([(ex, ey), (ax, ay)], fill=hex_to_rgb(color), width=width)


def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def get_line_height(font, draw, spacing=1.4):
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return int((bbox[3] - bbox[1]) * spacing)


def get_text_height(text, font, max_width, draw, line_spacing=1.4):
    lines = wrap_text(text, font, max_width, draw)
    if not lines:
        return 0
    return get_line_height(font, draw, line_spacing) * len(lines)


def draw_rich_text(draw, text, xy, font, default_color, accent_color, max_width,
                   line_spacing=1.25, align="left", accent_font=None):
    """Draw text with *accent* word highlighting."""
    x, y = xy
    if accent_font is None:
        accent_font = font

    segments = []
    parts = text.split("*")
    for i, part in enumerate(parts):
        if part:
            segments.append((part, i % 2 == 1))

    colored_words = []
    for seg_text, is_accent in segments:
        words = seg_text.split()
        for w in words:
            colored_words.append((w, accent_color if is_accent else default_color,
                                  accent_font if is_accent else font))

    lines = []
    current_line = []
    for word, color, wfont in colored_words:
        test_text = " ".join([w for w, _, _ in current_line] + [word])
        bbox = draw.textbbox((0, 0), test_text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append((word, color, wfont))
        else:
            if current_line:
                lines.append(current_line)
            current_line = [(word, color, wfont)]
    if current_line:
        lines.append(current_line)

    lh = get_line_height(font, draw, line_spacing)

    for line in lines:
        full_text = " ".join([w for w, _, _ in line])
        if align == "center":
            bbox = draw.textbbox((0, 0), full_text, font=font)
            line_w = bbox[2] - bbox[0]
            draw_x = x + (max_width - line_w) // 2
        else:
            draw_x = x

        for i, (word, color, wfont) in enumerate(line):
            draw.text((draw_x, y), word, font=wfont, fill=hex_to_rgb(color))
            bbox = draw.textbbox((0, 0), word + " ", font=wfont)
            draw_x += bbox[2] - bbox[0]

        y += lh

    return y


def draw_wrapped_text(draw, text, xy, font, fill, max_width, line_spacing=1.4, align="left"):
    x, y = xy
    lines = wrap_text(text, font, max_width, draw)
    lh = get_line_height(font, draw, line_spacing)
    for line in lines:
        if align == "center":
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            dx = x + (max_width - lw) // 2
        else:
            dx = x
        draw.text((dx, y), line, font=font, fill=fill)
        y += lh
    return y


def load_and_fit_image(image_path, max_width, max_height, radius=16):
    img = Image.open(image_path).convert("RGBA")
    ratio = min(max_width / img.width, max_height / img.height)
    new_w = int(img.width * ratio)
    new_h = int(img.height * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    mask = Image.new("L", (new_w, new_h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([(0, 0), (new_w, new_h)], radius=radius, fill=255)
    output = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)
    return output


def resolve_image_path(image_name, carousel_dir):
    """Resolve image path: 'asset:foo.png' looks in assets/, otherwise in reference/."""
    if image_name.startswith("asset:"):
        return ASSETS_DIR / image_name[6:]
    return carousel_dir / "reference" / image_name


def draw_editorial_footer(img, draw, config, fonts):
    """Draw footer: @handle on left, 'save for later' on right."""
    ig_size = 28
    row_center_y = SLIDE_HEIGHT - 70 + ig_size // 2

    handle = config["profile"]["handle"]
    handle_font = fonts["caption"]
    handle_bbox = draw.textbbox((0, 0), handle, font=handle_font)
    handle_text_h = handle_bbox[3] - handle_bbox[1]
    handle_top_offset = handle_bbox[1]
    handle_y = row_center_y - handle_text_h // 2 - handle_top_offset
    draw.text(
        (PADDING, handle_y),
        handle,
        font=handle_font,
        fill=hex_to_rgb(COLORS["off_white"]),
    )

    save_text = "save for later"
    save_font = fonts["caption"]
    save_bbox = draw.textbbox((0, 0), save_text, font=save_font)
    save_w = save_bbox[2] - save_bbox[0]
    save_text_h = save_bbox[3] - save_bbox[1]
    save_top_offset = save_bbox[1]
    save_x = SLIDE_WIDTH - PADDING - save_w

    bk_w, bk_h = 16, 22
    bk_x = save_x - bk_w - 10
    bk_y = row_center_y - bk_h // 2
    draw.polygon(
        [(bk_x, bk_y), (bk_x + bk_w, bk_y),
         (bk_x + bk_w, bk_y + bk_h),
         (bk_x + bk_w // 2, bk_y + bk_h - 7),
         (bk_x, bk_y + bk_h)],
        outline=hex_to_rgb(COLORS["off_white"]),
        width=2,
    )

    save_y = row_center_y - save_text_h // 2 - save_top_offset
    draw.text(
        (save_x, save_y),
        save_text,
        font=save_font,
        fill=hex_to_rgb(COLORS["off_white"]),
    )


def create_dark_slide():
    """Create a base slide with deep navy gradient background and subtle glow."""
    bg = hex_to_rgb(COLORS["bg_dark"])
    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), bg)

    glow = Image.new("RGBA", (SLIDE_WIDTH, SLIDE_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [SLIDE_WIDTH // 2 - 600, SLIDE_HEIGHT // 2 - 700,
         SLIDE_WIDTH // 2 + 600, SLIDE_HEIGHT // 2 + 700],
        fill=(20, 55, 100, 30),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    draw_grid_texture(img, color=COLORS["grid_line"], spacing=40, alpha=18)
    return img


# -- Slide Renderers ----------------------------------------------------------

def render_hook_slide(config, slide, fonts, carousel_dir):
    img = create_dark_slide()
    draw = ImageDraw.Draw(img)

    draw_gradient_bar(img, 0, 6, COLORS["blue"], COLORS["red"])

    if slide.get("image"):
        image_path = resolve_image_path(slide["image"], carousel_dir)
        if image_path.exists():
            hook_img = Image.open(str(image_path)).convert("RGBA")
            cover_ratio = 0.62
            ratio = SLIDE_WIDTH / hook_img.width
            new_w = int(hook_img.width * ratio)
            new_h = int(hook_img.height * ratio)
            hook_img = hook_img.resize((new_w, new_h), Image.LANCZOS)
            crop_h = min(new_h, int(SLIDE_HEIGHT * cover_ratio))
            hook_img = hook_img.crop((0, 0, SLIDE_WIDTH, crop_h))

            bg_sample = img.getpixel((SLIDE_WIDTH // 2, crop_h))
            bg_r, bg_g, bg_b = bg_sample[0], bg_sample[1], bg_sample[2]

            gradient = Image.new("RGBA", hook_img.size, (0, 0, 0, 0))
            fade_start = 0.65
            for y_pos in range(hook_img.height):
                progress = y_pos / hook_img.height
                if progress < fade_start:
                    alpha = 0
                else:
                    t = (progress - fade_start) / (1.0 - fade_start)
                    alpha = int(min(255, t * t * t * 800))
                for x_pos in range(hook_img.width):
                    gradient.putpixel((x_pos, y_pos), (bg_r, bg_g, bg_b, alpha))
            hook_img = Image.alpha_composite(hook_img, gradient)
            img.paste(hook_img.convert("RGB"), (0, 0))
            draw = ImageDraw.Draw(img)

    hook_text = slide["text"].upper()
    text_font = fonts["headline_xl"]

    text_h = get_text_height(hook_text.replace("*", ""), text_font, CONTENT_WIDTH, draw, 1.1)
    text_y = SLIDE_HEIGHT - FOOTER_HEIGHT - text_h - 100

    y_end = draw_rich_text(
        draw, hook_text, (PADDING, text_y),
        text_font, COLORS["white"], COLORS["accent"],
        CONTENT_WIDTH, line_spacing=1.1,
    )

    if slide.get("subtitle"):
        sub_font = fonts["body_lg"]
        sub_text = slide["subtitle"]
        sub_y = y_end + 20
        draw_wrapped_text(
            draw, sub_text, (PADDING, sub_y),
            sub_font,
            hex_to_rgb(COLORS["gray"]),
            CONTENT_WIDTH,
            line_spacing=1.3,
        )
        y_end = sub_y + get_text_height(sub_text, sub_font, CONTENT_WIDTH, draw, 1.3)

    if slide.get("annotation"):
        ann_font = fonts["hand_lg"]
        ann_y = y_end + 16
        draw.text(
            (PADDING, ann_y),
            slide["annotation"],
            font=ann_font,
            fill=hex_to_rgb(COLORS["accent"]),
        )
        ann_bbox = draw.textbbox((0, 0), slide["annotation"], font=ann_font)
        ann_w = ann_bbox[2] - ann_bbox[0]
        arrow_start = (PADDING + ann_w + 20, ann_y + 25)
        arrow_end = (PADDING + ann_w + 110, ann_y + 20)
        draw_curved_arrow(draw, arrow_start, arrow_end, COLORS["accent"], width=3)

    draw_editorial_footer(img, draw, config, fonts)
    return img


def _measure_body_content(slide, fonts, draw, carousel_dir, max_width):
    blocks = []
    GAP = 28

    has_image = False
    if slide.get("image"):
        image_path = resolve_image_path(slide["image"], carousel_dir)
        has_image = image_path.exists()

    content_count = sum([
        bool(slide.get("title")),
        bool(slide.get("text")),
        has_image,
        bool(slide.get("bullets")),
    ])
    is_sparse = content_count <= 2 and not has_image

    if slide.get("title"):
        title_font = fonts["headline_xl"] if is_sparse else fonts["headline_lg"]
        title = slide["title"].upper()
        clean = title.replace("*", "")
        if not clean.endswith("."):
            clean += "."
        th = get_text_height(clean, title_font, max_width, draw, 1.1)
        blocks.append(("title", th + 40, {"font": title_font, "sparse": is_sparse}))

    if slide.get("text"):
        text_font = fonts["body_lg"] if is_sparse else fonts["body"]
        line_sp = 1.6 if is_sparse else 1.5
        clean = slide["text"].replace("*", "")
        th = get_text_height(clean, text_font, max_width, draw, line_sp)
        blocks.append(("text", th + GAP, {"font": text_font, "line_spacing": line_sp}))

    if has_image:
        blocks.append(("image", 0, {"expandable": True}))

    if slide.get("annotation"):
        ann_font = fonts["hand_md"]
        ah = get_text_height(slide["annotation"], ann_font, max_width, draw, 1.3)
        blocks.append(("annotation", ah + 20, {"font": ann_font}))

    if slide.get("bullets"):
        bullet_font = fonts["body_lg"] if is_sparse else fonts["body"]
        total_bh = 0
        for bullet in slide["bullets"]:
            btext = bullet.replace("*", "")
            bh = get_text_height(btext, bullet_font, max_width - 44, draw, 1.35)
            total_bh += bh
        num_gaps = len(slide["bullets"]) - 1
        bullet_gap = 36 if is_sparse else 28
        total_bh += num_gaps * bullet_gap + 12
        blocks.append(("bullets", total_bh, {"font": bullet_font, "gap": bullet_gap}))

    return blocks, is_sparse


def render_body_slide(config, slide, fonts, carousel_dir):
    img = create_dark_slide()
    draw = ImageDraw.Draw(img)

    draw_gradient_bar(img, 0, 6, COLORS["blue"], COLORS["red"])

    usable_top = PADDING
    usable_bottom = SLIDE_HEIGHT - FOOTER_HEIGHT - 40
    usable_height = usable_bottom - usable_top

    blocks, is_sparse = _measure_body_content(slide, fonts, draw, carousel_dir, CONTENT_WIDTH)

    has_image = False
    image_path = None
    if slide.get("image"):
        image_path = resolve_image_path(slide["image"], carousel_dir)
        has_image = image_path.exists()

    fixed_height = sum(b[1] for b in blocks if b[0] != "image")
    block_gaps = max(0, len(blocks) - 1) * 20

    if has_image:
        src_img = Image.open(str(image_path))
        aspect = src_img.width / max(1, src_img.height)
        is_logo = (0.5 < aspect < 2.0) and slide.get("bullets")
        if is_logo:
            img_max_h = 150
        else:
            available_for_image = usable_height - fixed_height - block_gaps
            img_max_h = max(300, min(900, available_for_image))
        src_img.close()
    else:
        img_max_h = 0

    total_height = fixed_height + block_gaps
    if has_image:
        body_img = load_and_fit_image(str(image_path), CONTENT_WIDTH, img_max_h, radius=12)
        actual_img_h = body_img.height
        total_height += actual_img_h
    else:
        body_img = None
        actual_img_h = 0

    y_start = usable_top + max(0, (usable_height - total_height) // 2)
    if is_sparse:
        y_start = min(y_start, int(SLIDE_HEIGHT * 0.35))
    else:
        y_start = min(y_start, int(SLIDE_HEIGHT * 0.20))
    y_start = max(usable_top, y_start)

    y = y_start

    remaining_space = usable_height - total_height
    num_gaps = max(1, len(blocks) - 1)
    extra_gap = max(0, min(40, remaining_space // num_gaps))
    inter_gap = 20 + extra_gap

    if slide.get("title"):
        title = slide["title"].upper()
        title_font = fonts["headline_xl"] if is_sparse else fonts["headline_lg"]

        if "*" in title:
            marked_title = title
        else:
            if not title.endswith("."):
                title += "."
            title_parts = title.rsplit(" ", 1)
            if len(title_parts) == 2:
                marked_title = title_parts[0] + " *" + title_parts[1] + "*"
            else:
                marked_title = title

        y = draw_rich_text(
            draw, marked_title, (PADDING, y),
            title_font, COLORS["white"], COLORS["accent"],
            CONTENT_WIDTH, line_spacing=1.1,
        )

        draw.rounded_rectangle(
            [(PADDING, y + 8), (PADDING + 80, y + 14)],
            radius=3,
            fill=hex_to_rgb(COLORS["accent"]),
        )
        y += 32 + extra_gap // 2

    if slide.get("text"):
        text_font = fonts["headline_sm"] if is_sparse else fonts["body"]
        text_color = COLORS["white"] if is_sparse else COLORS["off_white"]
        line_sp = 1.4 if is_sparse else 1.5

        y = draw_rich_text(
            draw, slide["text"], (PADDING, y),
            text_font, text_color, COLORS["accent"],
            CONTENT_WIDTH, line_spacing=line_sp,
        )
        y += inter_gap

    if has_image and body_img is not None:
        src_check = Image.open(str(image_path))
        logo_aspect = src_check.width / max(1, src_check.height)
        is_logo_img = (0.5 < logo_aspect < 2.0) and slide.get("bullets")
        src_check.close()

        if not is_logo_img:
            shadow = Image.new("RGBA", (body_img.width + 20, body_img.height + 20), (0, 0, 0, 0))
            shadow_base = Image.new("RGBA", (body_img.width, body_img.height), (0, 0, 0, 60))
            shadow.paste(shadow_base, (10, 10))
            shadow = shadow.filter(ImageFilter.GaussianBlur(8))
            paste_x = PADDING
            paste_y = y
            crop_right = min(SLIDE_WIDTH, paste_x + shadow.width)
            crop_bottom = min(SLIDE_HEIGHT, paste_y + shadow.height)
            if crop_right > paste_x and crop_bottom > paste_y:
                bg_crop = img.convert("RGBA").crop((paste_x, paste_y, crop_right, crop_bottom))
                shadow_crop = shadow.crop((0, 0, crop_right - paste_x, crop_bottom - paste_y))
                composited = Image.alpha_composite(bg_crop, shadow_crop)
                img.paste(composited.convert("RGB"), (paste_x, paste_y))

        img_x = PADDING + (CONTENT_WIDTH - body_img.width) // 2
        img.paste(body_img, (img_x, y), body_img)
        draw = ImageDraw.Draw(img)
        y += body_img.height + inter_gap

    if slide.get("annotation"):
        ann_font = fonts["hand_md"]
        ann_text = slide["annotation"]
        draw.text(
            (PADDING + 20, y),
            ann_text,
            font=ann_font,
            fill=hex_to_rgb(COLORS["accent"]),
        )
        ann_bbox = draw.textbbox((0, 0), ann_text, font=ann_font)
        ann_w = ann_bbox[2] - ann_bbox[0]

        arrow_start = (PADDING + 20 + ann_w + 10, y + 20)
        arrow_end = (PADDING + 20 + ann_w + 60, y + 55)
        draw_curved_arrow(draw, arrow_start, arrow_end, COLORS["accent"], width=3)
        y += 50

    if slide.get("bullets"):
        bullet_font = fonts["body_lg"] if is_sparse else fonts["body"]
        bullets = slide["bullets"]

        bullet_heights = []
        for bullet in bullets:
            btext = bullet.replace("*", "")
            bh = get_text_height(btext, bullet_font, CONTENT_WIDTH - 44, draw, 1.35)
            bullet_heights.append(bh)

        total_bullet_h = sum(bullet_heights)
        remaining = usable_bottom - y - 20
        raw_gap = (remaining - total_bullet_h) // max(1, len(bullets))
        gap = max(24, min(raw_gap, 100))

        bullet_y = y + 12

        for i, bullet in enumerate(bullets):
            dot_y = bullet_y + 14
            draw.ellipse(
                [(PADDING, dot_y), (PADDING + 14, dot_y + 14)],
                fill=hex_to_rgb(COLORS["accent"]),
            )

            end_y = draw_rich_text(
                draw, bullet, (PADDING + 44, bullet_y),
                bullet_font, COLORS["off_white"], COLORS["accent"],
                CONTENT_WIDTH - 44, line_spacing=1.35,
            )
            bullet_y = end_y + gap

    draw_editorial_footer(img, draw, config, fonts)
    return img


def render_cta_slide(config, slide, fonts, carousel_dir):
    img = create_dark_slide()
    draw = ImageDraw.Draw(img)

    draw_gradient_bar(img, 0, 8, COLORS["blue"], COLORS["red"])

    center_x = SLIDE_WIDTH // 2

    headshot = Image.open(HEADSHOT_PATH).convert("RGBA")
    hs_size = 240
    headshot_circle = create_circular_image(headshot, hs_size)

    ring_size = hs_size + 20
    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.ellipse(
        [(0, 0), (ring_size, ring_size)],
        fill=hex_to_rgb(COLORS["accent"]) + (40,),
    )
    ring_draw.ellipse(
        [(8, 8), (ring_size - 8, ring_size - 8)],
        fill=(0, 0, 0, 0),
    )

    content_h = 740
    usable_top = PADDING + 8
    footer_y = SLIDE_HEIGHT - 70
    hs_y = usable_top + (footer_y - usable_top - content_h) // 2
    img.paste(ring, (center_x - ring_size // 2, hs_y - 8), ring)
    img.paste(headshot_circle, (center_x - hs_size // 2, hs_y), headshot_circle)

    name = config["profile"]["display_name"]
    name_font = fonts["headline_md"]
    name_y = hs_y + hs_size + 40
    draw.text(
        (center_x, name_y),
        name, font=name_font,
        fill=hex_to_rgb(COLORS["white"]),
        anchor="mt",
    )

    handle = config["profile"]["handle"]
    h_font = fonts["body_sm"]
    h_bbox = draw.textbbox((0, 0), handle, font=h_font)
    h_w = h_bbox[2] - h_bbox[0]
    handle_y = name_y + 72
    draw.text(
        ((SLIDE_WIDTH - h_w) // 2, handle_y),
        handle, font=h_font,
        fill=hex_to_rgb(COLORS["gray"]),
    )

    div_y = handle_y + 64
    div_w = 120
    draw.rounded_rectangle(
        [(center_x - div_w // 2, div_y), (center_x + div_w // 2, div_y + 3)],
        radius=2,
        fill=hex_to_rgb(COLORS["accent"]),
    )

    cta_text = slide.get("text", "Follow for more")
    cta_font = fonts["body_lg"]
    cta_y = div_y + 52
    draw_wrapped_text(
        draw, cta_text, (PADDING + 20, cta_y),
        cta_font,
        hex_to_rgb(COLORS["off_white"]),
        CONTENT_WIDTH - 40,
        line_spacing=1.4,
        align="center",
    )

    if slide.get("button_text"):
        btn_text = slide["button_text"]
        btn_font = fonts["body"]
        btn_bbox = draw.textbbox((0, 0), btn_text, font=btn_font)
        btn_text_w = btn_bbox[2] - btn_bbox[0]
        btn_text_h = btn_bbox[3] - btn_bbox[1]
        btn_text_y_offset = btn_bbox[1]
        btn_w = btn_text_w + 80
        btn_h = btn_text_h + 48
        btn_x = center_x - btn_w // 2
        btn_y = cta_y + get_text_height(cta_text, cta_font, CONTENT_WIDTH - 40, draw, 1.4) + 56

        draw.rounded_rectangle(
            [(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
            radius=btn_h // 2,
            fill=hex_to_rgb(COLORS["accent_secondary"]),
        )
        btn_text_x = btn_x + (btn_w - btn_text_w) // 2
        btn_text_y = btn_y + (btn_h - btn_text_h) // 2 - btn_text_y_offset
        draw.text(
            (btn_text_x, btn_text_y),
            btn_text, font=btn_font,
            fill=hex_to_rgb(COLORS["white"]),
        )

        arrow_start = (center_x, btn_y + btn_h + 20)
        arrow_end = (center_x, btn_y + btn_h + 70)
        draw_curved_arrow(draw, arrow_start, arrow_end, COLORS["accent_secondary"], 3)

    draw_gradient_bar(img, SLIDE_HEIGHT - 8, 8, COLORS["blue"], COLORS["red"])
    draw_editorial_footer(img, draw, config, fonts)
    return img


# -- Main Renderer ------------------------------------------------------------

def render_carousel(carousel_dir):
    carousel_dir = Path(carousel_dir)
    config_path = carousel_dir / "config.json"

    if not config_path.exists():
        print(f"Error: {config_path} not found")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    fonts = load_fonts()
    (carousel_dir / "reference").mkdir(exist_ok=True)

    slides = config["slides"]
    config["total_slides"] = len(slides)

    print(f"Rendering {len(slides)} slides for '{config.get('title', 'carousel')}'...")

    for i, slide in enumerate(slides):
        slide["number"] = i + 1
        slide_type = slide.get("type", "body")

        if slide_type == "hook":
            rendered = render_hook_slide(config, slide, fonts, carousel_dir)
        elif slide_type == "cta":
            rendered = render_cta_slide(config, slide, fonts, carousel_dir)
        else:
            rendered = render_body_slide(config, slide, fonts, carousel_dir)

        output_path = carousel_dir / f"slide_{i + 1}.png"
        rendered.save(str(output_path), "PNG", quality=95)
        print(f"  Saved {output_path.name} ({slide_type})")

    print(f"\nDone! {len(slides)} slides saved to {carousel_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 render.py <carousel-directory>")
        print("Example: python3 render.py workspace/my-carousel")
        sys.exit(1)

    render_carousel(sys.argv[1])
