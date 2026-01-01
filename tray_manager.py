# System tray icon and context menu

import threading
import logging
from typing import Callable, Dict, Optional
from PIL import Image, ImageDraw
import io
from config import THEME

logger = logging.getLogger(__name__)

# Try to import pystray, but make it optional
try:
    import pystray
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
    logger.warning("pystray not installed. Tray icon will be disabled. Install with: pip install pystray")

class TrayIcon:
    """System tray icon with context menu."""
    
    def __init__(self, app_name: str = "WBT", callbacks: Dict[str, Callable] = None):
        """
        Initialize tray icon.
        
        Args:
            app_name: Application name for tray
            callbacks: Dict of {action_name: callback_function}
        """
        self.app_name = app_name
        self.callbacks = callbacks or {}
        self.icon = None
        self.pystray_icon = None
        self._setup_icon()
    
    def _create_icon_image(self) -> Image.Image:
        """Create a simple WBT icon image."""
        size = 64
        # Create image with theme background
        img = Image.new('RGB', (size, size), THEME["bg"])
        draw = ImageDraw.Draw(img)
        
        # Draw a simple WBT symbol (WBT letters)
        # Draw white rectangle border
        border = 8
        draw.rectangle(
            [(border, border), (size - border, size - border)],
            outline=THEME["accent"],
            width=2
        )
        
        # Draw "WBT" text
        text = "WB"
        text_color = THEME["accent"]
        # Simple text positioning (rough centering)
        draw.text((size // 4, size // 3), text, fill=text_color)
        
        return img
    
    def _build_menu(self):
        """Build context menu from callbacks."""
        if not PYSTRAY_AVAILABLE:
            return None
        
        import pystray
        
        menu_items = []
        
        # Add menu items from callbacks
        for label, callback in self.callbacks.items():
            # Convert snake_case to Title Case for display
            if label == '' and callback == None:
                menu_items.append(pystray.MenuItem('', lambda: None))
                continue
            display_label = label.replace('_', ' ').title()
            if display_label.lower() != 'exit':
                menu_items.append(
                    pystray.MenuItem(display_label, callback)
                )
            else:
            # Add exit option
                menu_items.append(
                    pystray.MenuItem(
                        display_label,
                        lambda: self._exit_callback(),
                        default=False
                    )
                )
        
        return pystray.Menu(*menu_items)
    
    def _exit_callback(self):
        """Handle exit from tray menu."""
        try:
            if hasattr(self, 'pystray_icon') and self.pystray_icon:
                # Schedule the stop to run in the main thread
                self.pystray_icon.stop()
            
            # Call the exit callback if it exists
            if 'exit' in self.callbacks:
                self.callbacks['exit']()
                
        except Exception as e:
            logger.error(f"Error in exit callback: {e}", exc_info=True)
            # Force exit even if there was an error
            os._exit(1)
        
    def _setup_icon(self):
        """Setup the tray icon (called on tray thread)."""
        if not PYSTRAY_AVAILABLE:
            logger.warning("pystray not available, tray icon disabled")
            return False
        
        try:
            import pystray
        except ImportError:
            logger.error("pystray not installed. Install with: pip install pystray")
            return False
        
        try:
            icon_image = self._create_icon_image()
            menu = self._build_menu()
            # def on_clicked(icon, item):
            #     # The item parameter is the menu item that was clicked, if any
            #     # For icon clicks, item will be None
            #     if item is None:  # This means the icon itself was clicked
            #         logger.debug("Tray icon clicked")
            #         if 'toggle_window' in self.callbacks:
            #             self.callbacks['toggle_window']()
            #     return True
            
            def on_clicked(icon, item):
                try:
                    # Print directly to console for debugging
                    print(f"\n=== TRAY ICON CLICKED ===")
                    print(f"Item clicked: {item}")
                    print(f"Available callbacks: {list(self.callbacks.keys())}")
                    print(f"Callback object: {self.callbacks.get('toggle_window')}")
                    
                    if item is None:  # Icon was clicked, not a menu item
                        print("Tray icon main body clicked")
                        if 'toggle_window' in self.callbacks:
                            print("Calling toggle_window callback")
                            try:
                                self.callbacks['toggle_window']()
                                print("toggle_window callback executed successfully")
                            except Exception as e:
                                print(f"Error in toggle_window callback: {e}")
                                import traceback
                                print(f"Stack trace: {traceback.format_exc()}")
                        else:
                            print("WARNING: toggle_window callback not found in callbacks")
                    else:
                        print(f"Menu item clicked: {item}")
                except Exception as e:
                    print(f"CRITICAL ERROR in tray icon click handler: {e}")
                    import traceback
                    print(f"Stack trace: {traceback.format_exc()}")
            
            self.pystray_icon = pystray.Icon(
                self.app_name,
                icon_image,
                self.app_name,
                menu=menu
            )
            self.pystray_icon._on_click = on_clicked
            return True
        except Exception as e:
            logger.error(f"Failed to create tray icon: {e}", exc_info=True)
            return False
    
    def run(self):
        """Run tray icon in thread."""
        try:
            if self.pystray_icon:
                self.pystray_icon.run()
        except Exception as e:
            logger.error(f"Tray icon error: {e}", exc_info=True)
    
    def run_in_thread(self):
        """Run tray icon in background thread."""
        if not self.pystray_icon:
            logger.warning("Tray icon not initialized")
            return False
        
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return True
    
    def stop(self):
        """Stop tray icon."""
        try:
            if self.pystray_icon:
                self.pystray_icon.stop()
        except Exception as e:
            logger.error(f"Error stopping tray icon: {e}")
    
    def update_menu(self, callbacks: Dict[str, Callable]):
        """Update menu items."""
        self.callbacks = callbacks
        if self.pystray_icon:
            try:
                self.pystray_icon.menu = self._build_menu()
            except Exception as e:
                logger.error(f"Error updating menu: {e}")
    
    def set_tooltip(self, text: str):
        """Update tooltip text."""
        if self.pystray_icon:
            try:
                self.pystray_icon.title = text
                logger.debug(f"Tooltip updated: {text}")
            except Exception as e:
                logger.error(f"Error updating tooltip: {e}")