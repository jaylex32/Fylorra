"""PNG Icon Loader - Loads high-quality PNG icons"""

from pathlib import Path
from PIL import Image
import customtkinter as ctk


class PNGIconLoader:
    """Loads and manages PNG icons"""

    def __init__(self):
        self.icons_path = Path(__file__).parent.parent / "assets" / "icons"
        self.cache = {}

    def load_icon(self, icon_name: str, size: tuple = (24, 24)):
        """Load icon as CTkImage from PNG file"""
        cache_key = f"{icon_name}_{size[0]}_{size[1]}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        png_path = self.icons_path / f"{icon_name}.png"

        if not png_path.exists():
            print(f"Icon not found: {png_path}")
            return None

        try:
            # Load the PNG file
            img = Image.open(png_path)

            # Resize if needed
            if img.size != size:
                img = img.resize(size, Image.Resampling.LANCZOS)

            # Create CTkImage
            ctk_img = ctk.CTkImage(
                light_image=img,
                dark_image=img,
                size=size
            )

            self.cache[cache_key] = ctk_img
            return ctk_img

        except Exception as e:
            print(f"Error loading icon {icon_name}: {e}")
            return None


_icon_loader = None

def get_icon_loader():
    """Get global icon loader"""
    global _icon_loader
    if _icon_loader is None:
        _icon_loader = PNGIconLoader()
    return _icon_loader
