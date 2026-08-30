"""Create high-quality PNG icons from scratch"""

from PIL import Image, ImageDraw
from pathlib import Path


def create_play_icon(size=64):
    """Create play button icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White triangle
    margin = size // 4
    points = [
        (margin, margin),
        (margin, size - margin),
        (size - margin, size // 2)
    ]
    draw.polygon(points, fill='#FFFFFF')

    return img


def create_pause_icon(size=64):
    """Create pause button icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White bars
    margin = size // 4
    bar_width = size // 6
    spacing = size // 8

    # Left bar
    draw.rectangle([margin, margin, margin + bar_width, size - margin], fill='#FFFFFF')
    # Right bar
    draw.rectangle([size - margin - bar_width, margin, size - margin, size - margin], fill='#FFFFFF')

    return img


def create_edit_icon(size=64):
    """Create edit/pencil icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White pencil
    margin = size // 6

    # Pencil body
    points = [
        (size - margin, margin),
        (size - margin * 2, margin * 2),
        (margin * 2, size - margin * 2),
        (margin, size - margin)
    ]
    draw.polygon(points, fill='#FFFFFF')

    # Pencil tip
    draw.polygon([
        (margin, size - margin),
        (margin * 2, size - margin * 2),
        (margin, size - margin * 2)
    ], fill='#E0E0E0')

    return img


def create_delete_icon(size=64):
    """Create delete/trash icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White trash can
    margin = size // 4

    # Can body
    draw.rectangle([margin, margin * 2, size - margin, size - margin], fill='#FFFFFF')

    # Can lid
    draw.rectangle([margin - 4, margin * 1.5, size - margin + 4, margin * 2], fill='#E0E0E0')

    # Handle
    handle_width = size // 3
    handle_start = (size - handle_width) // 2
    draw.rectangle([handle_start, margin, handle_start + handle_width, margin * 1.5], fill='#E0E0E0')

    # Lines on can (dark lines on white)
    line_spacing = (size - margin * 3) // 3
    for i in range(1, 3):
        x = margin + i * line_spacing
        draw.rectangle([x, margin * 2.5, x + 4, size - margin * 1.5], fill='#757575')

    return img


def create_folder_icon(size=64):
    """Create folder icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Blue folder
    margin = size // 6

    # Folder body
    draw.rectangle([margin, margin * 2, size - margin, size - margin], fill='#4A90E2')

    # Folder tab
    tab_width = size // 3
    draw.polygon([
        (margin, margin * 2),
        (margin, margin),
        (margin + tab_width, margin),
        (margin + tab_width + margin // 2, margin * 2)
    ], fill='#357ABD')

    return img


def create_ftp_icon(size=64):
    """Create FTP/network icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Purple globe
    margin = size // 6
    center = size // 2
    radius = size // 2 - margin

    # Outer circle
    draw.ellipse([margin, margin, size - margin, size - margin], outline='#9C27B0', width=4)

    # Vertical line
    draw.line([center, margin, center, size - margin], fill='#9C27B0', width=4)

    # Horizontal line
    draw.line([margin, center, size - margin, center], fill='#9C27B0', width=4)

    # Inner ellipse (horizontal)
    ellipse_margin = margin + radius // 3
    draw.ellipse([ellipse_margin, margin * 2, size - ellipse_margin, size - margin * 2],
                 outline='#9C27B0', width=3)

    return img


def create_settings_icon(size=64):
    """Create settings/gear icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gray gear
    center = size // 2
    outer_radius = size // 2 - 4
    inner_radius = size // 4

    # Draw gear teeth
    import math
    teeth = 8
    for i in range(teeth):
        angle1 = (i * 360 / teeth) * math.pi / 180
        angle2 = ((i + 0.4) * 360 / teeth) * math.pi / 180

        x1_out = center + outer_radius * math.cos(angle1)
        y1_out = center + outer_radius * math.sin(angle1)
        x2_out = center + outer_radius * math.cos(angle2)
        y2_out = center + outer_radius * math.sin(angle2)

        x1_in = center + (inner_radius + 8) * math.cos(angle1)
        y1_in = center + (inner_radius + 8) * math.sin(angle1)
        x2_in = center + (inner_radius + 8) * math.cos(angle2)
        y2_in = center + (inner_radius + 8) * math.sin(angle2)

        draw.polygon([(x1_out, y1_out), (x2_out, y2_out), (x2_in, y2_in), (x1_in, y1_in)],
                    fill='#607D8B')

    # Inner circle
    draw.ellipse([center - inner_radius, center - inner_radius,
                  center + inner_radius, center + inner_radius], fill='#607D8B')

    # Center hole
    hole_radius = inner_radius // 2
    draw.ellipse([center - hole_radius, center - hole_radius,
                  center + hole_radius, center + hole_radius], fill=(0, 0, 0, 0))

    return img


def create_export_icon(size=64):
    """Create export/download icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gray download arrow
    margin = size // 4
    center = size // 2

    # Arrow shaft
    shaft_width = 6
    draw.rectangle([center - shaft_width // 2, margin,
                   center + shaft_width // 2, size - margin * 2], fill='#607D8B')

    # Arrow head
    arrow_size = size // 4
    draw.polygon([
        (center, size - margin),
        (center - arrow_size, size - margin * 2),
        (center + arrow_size, size - margin * 2)
    ], fill='#607D8B')

    # Base line
    draw.rectangle([margin, size - margin // 2, size - margin, size - margin // 2 + 4],
                  fill='#607D8B')

    return img


def create_add_icon(size=64):
    """Create add/plus icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # White plus
    margin = size // 4
    center = size // 2
    thickness = 8

    # Vertical bar
    draw.rectangle([center - thickness // 2, margin,
                   center + thickness // 2, size - margin], fill='#FFFFFF')

    # Horizontal bar
    draw.rectangle([margin, center - thickness // 2,
                   size - margin, center + thickness // 2], fill='#FFFFFF')

    return img


def main():
    """Create all icons"""
    icons_dir = Path(__file__).parent.parent / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Create all icons
    icons = {
        'play': create_play_icon,
        'pause': create_pause_icon,
        'edit': create_edit_icon,
        'delete': create_delete_icon,
        'folder': create_folder_icon,
        'ftp': create_ftp_icon,
        'settings': create_settings_icon,
        'export': create_export_icon,
        'add': create_add_icon
    }

    for name, func in icons.items():
        # Create high-res version
        icon = func(64)
        icon.save(icons_dir / f"{name}.png", 'PNG')
        print(f"Created {name}.png")

    print("\nAll icons created successfully!")


if __name__ == "__main__":
    main()
