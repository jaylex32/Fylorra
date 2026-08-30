"""
Create AI feature icons as PNG - WHITE and CLEAN
"""

from PIL import Image, ImageDraw
from pathlib import Path

icons_folder = Path("assets/icons")
size = 256

def create_brain_icon():
    """Create brain icon - clean white outline"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color = (255, 255, 255, 255)

    # Clean brain outline - two connected circles
    # Left hemisphere
    draw.ellipse([50, 60, 130, 190], outline=color, width=10)
    # Right hemisphere
    draw.ellipse([126, 60, 206, 190], outline=color, width=10)

    # Brain details - minimal curves
    draw.arc([65, 75, 115, 125], 30, 150, fill=color, width=7)
    draw.arc([141, 75, 191, 125], 30, 150, fill=color, width=7)
    draw.arc([75, 135, 115, 175], 210, 330, fill=color, width=7)
    draw.arc([141, 135, 181, 175], 210, 330, fill=color, width=7)

    return img

def create_grid_icon():
    """Create grid icon - clean 3x3 grid"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color = (255, 255, 255, 255)

    # 3x3 grid - clean squares
    cell_size = 55
    gap = 15
    start = 50

    for row in range(3):
        for col in range(3):
            x = start + col * (cell_size + gap)
            y = start + row * (cell_size + gap)
            draw.rounded_rectangle([x, y, x + cell_size, y + cell_size],
                                  radius=6, outline=color, width=8)

    return img

def create_shield_icon():
    """Create shield icon - clean outline with check"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color = (255, 255, 255, 255)

    # Shield outline
    shield_points = [
        (128, 50),   # Top
        (70, 75),    # Top left
        (70, 145),   # Mid left
        (128, 210),  # Bottom point
        (186, 145),  # Mid right
        (186, 75),   # Top right
    ]
    draw.polygon(shield_points, outline=color, width=10)

    # Clean check mark
    draw.line([95, 128, 118, 151], fill=color, width=14, joint="curve")
    draw.line([118, 151, 161, 108], fill=color, width=14, joint="curve")

    return img

# Create icons
print("Creating brain icon...")
brain = create_brain_icon()
brain.save(icons_folder / "brain.png")
print("Created brain.png")

print("Creating grid icon...")
grid = create_grid_icon()
grid.save(icons_folder / "grid.png")
print("Created grid.png")

print("Creating shield icon...")
shield = create_shield_icon()
shield.save(icons_folder / "shield.png")
print("Created shield.png")

print("\nAll WHITE icons created successfully!")
