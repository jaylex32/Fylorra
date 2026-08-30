"""SVG Icon Loader - Converts SVG files to PhotoImage for tkinter"""

from pathlib import Path
from PIL import Image, ImageTk
import customtkinter as ctk
from io import BytesIO
import base64


class SVGIcon:
    """Simple SVG to image converter using PIL"""

    def __init__(self):
        self.icons_path = Path(__file__).parent.parent / "assets" / "icons"
        self.cache = {}

    def load_svg_as_image(self, icon_name: str, size: tuple = (24, 24), color: str = None):
        """
        Load SVG and return as CTkImage

        Args:
            icon_name: Name of the icon (without .svg)
            size: Tuple of (width, height)
            color: Optional color to replace in SVG

        Returns:
            CTkImage object
        """
        cache_key = f"{icon_name}_{size[0]}_{size[1]}_{color}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        svg_path = self.icons_path / f"{icon_name}.svg"

        if not svg_path.exists():
            return None

        try:
            # For now, use PNG versions or convert
            # Since we have SVGs, let's create a simple converter

            # Read SVG content
            with open(svg_path, 'r') as f:
                svg_content = f.read()

            # Try using cairosvg if available, otherwise use PIL with PNG fallback
            try:
                import cairosvg
                png_data = cairosvg.svg2png(
                    bytestring=svg_content.encode('utf-8'),
                    output_width=size[0],
                    output_height=size[1]
                )
                image = Image.open(BytesIO(png_data))

            except ImportError:
                # Fallback: Create a colored rectangle as placeholder
                # This is temporary until cairosvg is installed
                image = Image.new('RGBA', size, (255, 255, 255, 0))

            # Convert to CTkImage
            ctk_image = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=size
            )

            self.cache[cache_key] = ctk_image
            return ctk_image

        except Exception as e:
            print(f"Error loading SVG {icon_name}: {e}")
            return None


# Global instance
_svg_loader = None


def get_svg_loader():
    """Get global SVG loader instance"""
    global _svg_loader
    if _svg_loader is None:
        _svg_loader = SVGIcon()
    return _svg_loader
