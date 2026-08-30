"""System Tray Manager - Handles system tray integration"""

import pystray
from PIL import Image, ImageDraw
import threading
from typing import Callable

from core.branding import APP_NAME, APP_TAGLINE


class SystemTrayManager:
    """Manages system tray icon and menu"""

    def __init__(self, root, restore_callback: Callable):
        self.root = root
        self.restore_callback = restore_callback
        self.icon = None
        self.is_visible = False

    def _create_icon_image(self):
        """Create a simple icon image"""
        # Create a simple icon (you can replace this with a better icon file)
        width = 64
        height = 64
        color1 = (30, 106, 165)  # Blue
        color2 = (255, 255, 255)  # White

        image = Image.new('RGB', (width, height), color1)
        draw = ImageDraw.Draw(image)

        # Draw a simple folder icon
        draw.rectangle([10, 20, 54, 50], fill=color2, outline=color1)
        draw.rectangle([15, 15, 35, 20], fill=color2, outline=color1)

        return image

    def _create_menu(self):
        """Create tray menu"""
        return pystray.Menu(
            pystray.MenuItem(APP_NAME, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show", self._on_restore),
            pystray.MenuItem("Quit", self._on_quit)
        )

    def _on_restore(self, icon, item):
        """Restore window from tray"""
        self.hide_tray()
        self.restore_callback()

    def _on_quit(self, icon, item):
        """Quit application from tray"""
        self.hide_tray()
        self.root.quit()

    def show_tray(self):
        """Show system tray icon"""
        if self.is_visible:
            return

        def run_tray():
            self.icon = pystray.Icon(
                APP_NAME,
                self._create_icon_image(),
                f"{APP_NAME} - {APP_TAGLINE.title()}",
                self._create_menu()
            )
            self.is_visible = True
            self.icon.run()

        # Run tray in separate thread
        tray_thread = threading.Thread(target=run_tray, daemon=True)
        tray_thread.start()

    def hide_tray(self):
        """Hide system tray icon"""
        if self.icon and self.is_visible:
            self.icon.stop()
            self.is_visible = False
