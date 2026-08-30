"""Create Windows .ico file for the application"""

from PIL import Image

# Load the folder icon
icon_path = "assets/icons/folder.png"
ico_path = "assets/fylorra.ico"

# Open the PNG
img = Image.open(icon_path)

# Convert to RGBA if needed
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Create multiple sizes for Windows icon (16, 32, 48, 64, 128, 256)
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
icon_images = []

for size in sizes:
    resized = img.resize(size, Image.Resampling.LANCZOS)
    icon_images.append(resized)

# Save as .ico
icon_images[0].save(
    ico_path,
    format='ICO',
    sizes=[(img.width, img.height) for img in icon_images],
    append_images=icon_images[1:]
)

print(f"Created {ico_path}")
