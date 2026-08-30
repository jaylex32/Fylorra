"""
Convert AI feature SVG icons to PNG
"""

from pathlib import Path
from PIL import Image
import cairosvg
import io

icons_folder = Path("assets/icons")

# Icons to convert
svg_icons = ["brain", "grid", "shield"]

for icon_name in svg_icons:
    svg_path = icons_folder / f"{icon_name}.svg"
    png_path = icons_folder / f"{icon_name}.png"

    print(f"Converting {svg_path} to {png_path}...")

    # Read SVG
    with open(svg_path, 'r') as f:
        svg_data = f.read()

    # Convert to PNG at high resolution
    png_data = cairosvg.svg2png(
        bytestring=svg_data.encode('utf-8'),
        output_width=256,
        output_height=256,
        background_color='transparent'
    )

    # Save PNG
    with open(png_path, 'wb') as f:
        f.write(png_data)

    print(f"✓ Created {png_path}")

print("\nAll icons converted successfully!")
