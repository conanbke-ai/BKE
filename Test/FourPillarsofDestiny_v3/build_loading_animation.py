"""Build the background-integrated loading rabbit loop from the generated sprite sheet.

This is a build-time helper. Run it with a Python environment that provides Pillow.
The Flask application only consumes the generated WebP and PNG assets.
"""

from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "static" / "assets"
SPRITE_SHEET = ASSETS / "loading-bunny-run-sprites-v1.png"
BACKGROUND = ASSETS / "app-background-clouds-v2.png"
ANIMATION = ASSETS / "loading-bunny-short-loop-v1.webp"
POSTER = ASSETS / "loading-bunny-short-loop-poster-v1.png"

CELL_SIZE = 444
OUTPUT_SIZE = (720, 240)
FRAME_DURATIONS_MS = (280, 140, 140, 180, 140, 160, 220, 340)
FRAME_LIFT = (0, 14, 30, 68, 48, 16, 0, 0)
FRAME_X = (-4, 0, 5, 8, 5, 2, -2, -4)


def largest_component_mask(alpha: Image.Image, threshold: int = 24) -> Image.Image:
    """Keep the rabbit and discard detached generation speckles."""
    width, height = alpha.size
    source = bytearray(alpha.point(lambda value: 255 if value >= threshold else 0).tobytes())
    visited = bytearray(width * height)
    largest: list[int] = []

    for start, value in enumerate(source):
        if not value or visited[start]:
            continue
        component: list[int] = []
        queue = deque([start])
        visited[start] = 1
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                row = ny * width
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row + nx
                    if source[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        queue.append(neighbor)
        if len(component) > len(largest):
            largest = component

    keep = bytearray(width * height)
    for index in largest:
        keep[index] = 255
    mask = Image.frombytes("L", (width, height), bytes(keep))
    return mask.filter(ImageFilter.MaxFilter(5))


def clean_sprite(cell: Image.Image) -> Image.Image:
    sprite = cell.convert("RGBA")
    alpha = sprite.getchannel("A")
    keep = largest_component_mask(alpha)
    sprite.putalpha(ImageChops.multiply(alpha, keep))
    box = sprite.getchannel("A").getbbox()
    if not box:
        raise ValueError("A sprite frame did not contain a rabbit.")
    return sprite.crop(box)


def scene_background() -> Image.Image:
    background = Image.open(BACKGROUND).convert("RGBA")
    scene = ImageOps.fit(
        background,
        OUTPUT_SIZE,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.54),
    )
    veil = Image.new("RGBA", OUTPUT_SIZE, (255, 248, 252, 22))
    return Image.alpha_composite(scene, veil)


def compose_frame(background: Image.Image, sprite: Image.Image, index: int) -> Image.Image:
    frame = background.copy()
    scale = 0.44
    sprite = sprite.resize(
        (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
        Image.Resampling.LANCZOS,
    )
    center_x = OUTPUT_SIZE[0] // 2 + FRAME_X[index]
    ground_y = 222 - FRAME_LIFT[index]
    left = center_x - sprite.width // 2
    top = ground_y - sprite.height

    shadow = Image.new("RGBA", OUTPUT_SIZE, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_width = round(112 - FRAME_LIFT[index] * 1.05)
    shadow_alpha = max(20, 54 - FRAME_LIFT[index])
    shadow_draw.ellipse(
        (
            center_x - shadow_width // 2,
            216,
            center_x + shadow_width // 2,
            229,
        ),
        fill=(137, 78, 108, shadow_alpha),
    )
    frame = Image.alpha_composite(frame, shadow.filter(ImageFilter.GaussianBlur(7)))
    frame.alpha_composite(sprite, (left, top))
    return frame


def main() -> None:
    sheet = Image.open(SPRITE_SHEET).convert("RGBA").resize(
        (CELL_SIZE * 4, CELL_SIZE * 2),
        Image.Resampling.LANCZOS,
    )
    sprites = []
    for index in range(8):
        column, row = index % 4, index // 4
        cell = sheet.crop(
            (
                column * CELL_SIZE,
                row * CELL_SIZE,
                (column + 1) * CELL_SIZE,
                (row + 1) * CELL_SIZE,
            )
        )
        sprites.append(clean_sprite(cell))

    background = scene_background()
    frames = [compose_frame(background, sprite, index) for index, sprite in enumerate(sprites)]
    frames[0].save(POSTER, optimize=True)
    frames[0].save(
        ANIMATION,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATIONS_MS,
        loop=0,
        quality=86,
        method=6,
        minimize_size=True,
    )
    print(f"poster={POSTER} ({POSTER.stat().st_size:,} bytes)")
    print(f"animation={ANIMATION} ({ANIMATION.stat().st_size:,} bytes)")
    for index, sprite in enumerate(sprites, start=1):
        print(f"frame {index}: cleaned sprite {sprite.width}x{sprite.height}")


if __name__ == "__main__":
    main()
