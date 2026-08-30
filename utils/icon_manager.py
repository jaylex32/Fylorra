"""Icon Manager - Handles SVG icons for the UI"""

from pathlib import Path
from PIL import Image, ImageTk
import io
import cairosvg
from tkinter import PhotoImage


class IconManager:
    """Manages SVG icons and converts them to usable formats"""

    def __init__(self):
        self.icons_path = Path(__file__).parent.parent / "assets" / "icons"
        self.icon_cache = {}

    def get_icon(self, name: str, size: int = 24, color: str = None) -> PhotoImage:
        """
        Get an icon as PhotoImage for use in tkinter/customtkinter

        Args:
            name: Icon name (without .svg extension)
            size: Size in pixels (default 24)
            color: Optional color override

        Returns:
            PhotoImage object
        """
        cache_key = f"{name}_{size}_{color}"

        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]

        svg_path = self.icons_path / f"{name}.svg"

        if not svg_path.exists():
            # Return empty image if icon not found
            return None

        try:
            # Read SVG
            with open(svg_path, 'r') as f:
                svg_data = f.read()

            # Replace color if specified
            if color:
                # Simple color replacement (you can make this more sophisticated)
                svg_data = svg_data.replace('fill="#', f'fill_original="#')
                svg_data = svg_data.replace('fill="', f'fill="{color}"')

            # Convert SVG to PNG bytes
            png_bytes = cairosvg.svg2png(
                bytestring=svg_data.encode('utf-8'),
                output_width=size,
                output_height=size
            )

            # Convert to PIL Image
            pil_image = Image.open(io.BytesIO(png_bytes))

            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(pil_image)

            # Cache it
            self.icon_cache[cache_key] = photo

            return photo

        except Exception as e:
            print(f"Error loading icon {name}: {e}")
            return None

    def get_icon_path(self, name: str) -> str:
        """Get the file path to an icon"""
        return str(self.icons_path / f"{name}.svg")


# Global instance
_icon_manager = None


def get_icon_manager() -> IconManager:
    """Get the global icon manager instance"""
    global _icon_manager
    if _icon_manager is None:
        _icon_manager = IconManager()
    return _icon_manager
