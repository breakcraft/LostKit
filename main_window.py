# main_window.py
import gc
import time
import uuid
import re
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QVBoxLayout, QTabWidget, QPushButton, QLabel)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPalette, QBrush, QColor
from game_view import GameViewWidget
from right_panel import RightToolsPanel, InGameBrowser
from chat_panel import ChatPanel
from world_switcher import WorldSwitcherWindow
import config
from styles import get_main_stylesheet, get_icon_path
from font_loader import font_loader
import os


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Generate unique instance ID 
        self.instance_id = uuid.uuid4().hex[:8]
        
        self.setWindowTitle(f"LostKit")
        
        # Set window icon if it exists
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        
        # Load config - ensure proper restoration
        self.config = config.load_config()
        self._header_world_info = self.config.get("current_world_info", "No world")
        self.last_config_save_ts = time.time()
        self.header_widget = None
        self.status_label = None
        self.reload_button = None
        
        # Window state management
        self.is_closing = False
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.save_window_state_debounced)
        
        # Set window geometry from config with better restoration
        self.setup_window_geometry()
        
        # Set black background
        palette = QPalette()
        applied_brush = False
        background_image = "button.jpg"
        if os.path.exists(background_image):
            background_pixmap = QPixmap(background_image)
            if not background_pixmap.isNull():
                scaled_pixmap = background_pixmap.scaled(
                    800,
                    800,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                palette.setBrush(QPalette.ColorRole.Window, QBrush(scaled_pixmap))
                applied_brush = True
        if not applied_brush:
            palette.setBrush(QPalette.ColorRole.Window, QBrush(QColor(0, 0, 0)))
        self.setAutoFillBackground(True)
        self.setPalette(palette)
        
        # Apply updated stylesheet with custom font
        self.setStyleSheet(get_main_stylesheet())
        
        # Set larger minimum size
        self.setMinimumSize(1000, 700)

        # Create central widget and main layout
        central_widget = QWidget()
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)

        # Header bar with status information
        self.create_header_bar()
        self.main_layout.addWidget(self.header_widget)

        # Create main horizontal splitter
        self.main_horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Create sections
        self.create_left_section()
        self.create_right_section()

        self.setCentralWidget(central_widget)
        
        # Track browser tabs for cleanup
        self.browser_tabs = {}
        
        # World switcher window
        self.world_switcher_window = None
        
        # Setup resource management
        self.setup_resource_management()

        # Save config periodically to prevent data loss
        self.config_save_timer = QTimer(self)
        self.config_save_timer.timeout.connect(self.periodic_config_save)
        self.config_save_timer.start(30000)  # Save config every 30 seconds
        
        # Apply readable fonts after UI is created
        QTimer.singleShot(100, self.force_apply_readable_fonts)

    def force_apply_readable_fonts(self):
        """Force apply readable fonts to all UI elements after creation"""
        print("Forcing readable font application...")
        
        # Create readable fonts - 1.7x scaling instead of 5x
        font = QFont()
        if font_loader.is_custom_font_available():
            font.setFamily(font_loader.get_font_family_name())
            print(f"Using custom font: {font_loader.get_font_family_name()}")
        else:
            print("Custom font not available, checking for Runescape-Quill-Caps...")
            # Try to find Runescape-Quill-Caps specifically
            test_font = QFont("Runescape-Quill-Caps", 20)
            if test_font.exactMatch():
                font.setFamily("Runescape-Quill-Caps")
                print("Found Runescape-Quill-Caps font")
            else:
                font.setFamily("Arial")
                print("Using Arial fallback")
        
        font.setPointSize(20)  # Readable size - was 35 before (5x), now ~24 (1.7x)
        font.setWeight(QFont.Weight.Normal)
        
        # Apply to main window and all children recursively
        self.apply_font_to_widget_tree(self, font)
        
        print(f"Applied {font.pointSize()}pt font ({font.family()}) to all UI elements")

    def create_header_bar(self):
        """Create the header bar that shows world info and save status."""
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.status_label = QLabel()
        self.status_label.setObjectName("header_status_label")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #f5e6c0;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self.status_label, 1)

        self.reload_button = QPushButton("Reload Game")
        self.reload_button.setToolTip("Reload the LostCity client if it becomes unresponsive.")
        self.reload_button.clicked.connect(self.reload_game_view)
        self.reload_button.setFixedHeight(32)
        header_layout.addWidget(self.reload_button, 0)

    def reload_game_view(self):
        """Reload the in-game view while providing button feedback."""
        if not hasattr(self, "game_view") or self.game_view is None:
            return
        try:
            self.reload_button.setEnabled(False)
            self.status_label.setText("Reloading game client...")
            self.game_view.reload()
            QTimer.singleShot(2000, lambda: self.reload_button.setEnabled(True))
            QTimer.singleShot(2500, lambda: self.update_header_status())
        except Exception as e:
            print(f"Error reloading game view: {e}")
            self.reload_button.setEnabled(True)
            QTimer.singleShot(500, lambda: self.update_header_status())

    def update_header_status(self, world_info=None, saved_now=False):
        """Refresh the header label with current world info and last save time."""
        if self.status_label is None:
            return

        if world_info is not None:
            self._header_world_info = world_info
        else:
            world_info = self._header_world_info

        if saved_now or not hasattr(self, "last_config_save_ts"):
            self.last_config_save_ts = time.time()

        if self.last_config_save_ts:
            save_display = time.strftime("%I:%M:%S %p", time.localtime(self.last_config_save_ts))
        else:
            save_display = "—"

        display_text = f"World: {world_info} • Last save: {save_display}"
        self.status_label.setText(display_text)
        self.status_label.setToolTip(f"Last configuration save at {save_display}")

    def apply_font_to_widget_tree(self, widget, font):
        """Recursively apply font to widget and all its children"""
        try:
            # Apply font to the current widget
            widget.setFont(font)
            
            # Special handling for specific widget types
            if hasattr(widget, 'setText') and hasattr(widget, 'text'):
                # For buttons, labels, etc - force font update
                current_text = widget.text()
                widget.setFont(font)
                widget.setText(current_text)  # Trigger text refresh
            
            # Apply to all child widgets
            for child in widget.findChildren(QWidget):
                if not isinstance(child, (QTabWidget,)):  # Skip web views to avoid issues
                    child.setFont(font)
                    
                    # Special handling for tab widgets
                    if isinstance(child, QTabWidget):
                        # Apply font to tab bar
                        tab_bar = child.tabBar()
                        if tab_bar:
                            tab_bar.setFont(font)
                            
        except Exception as e:
            print(f"Error applying font to widget: {e}")

    def setup_window_geometry(self):
        """Setup window geometry with proper restoration"""
        try:
            geom = self.config.get("window_geometry")
            if geom and isinstance(geom, list) and len(geom) == 4:
                x, y, w, h = [int(val) for val in geom]
                
                # Validate geometry is on screen
                x = max(0, min(x, 1920 - w))
                y = max(0, min(y, 1080 - h))
                w = max(1000, min(w, 1920))
                h = max(700, min(h, 1080))
                
                self.setGeometry(x, y, w, h)
                print(f"Restored window geometry: {w}x{h} at ({x},{y})")
            else:
                # Default geometry
                self.setGeometry(100, 100, 1440, 900)
                print("Using default window geometry")
        except (ValueError, TypeError) as e:
            print(f"Error setting window geometry: {e}, using defaults")
            self.setGeometry(100, 100, 1440, 900)

    def periodic_config_save(self):
        """Periodically save config to prevent data loss"""
        if not self.is_closing:
            try:
                self.save_current_state_to_config()
                config.force_save_config()
                self.update_header_status(saved_now=True)
                print("Periodic config save completed")
            except Exception as e:
                print(f"Error in periodic config save: {e}")

    def setup_resource_management(self):
        """Setup periodic resource management"""
        if config.get_config_value("resource_optimization", True):
            self.resource_timer = QTimer(self)
            self.resource_timer.timeout.connect(self.perform_resource_cleanup)
            self.resource_timer.start(300000)  # 5 minutes

    def perform_resource_cleanup(self):
        """Perform periodic resource cleanup"""
        try:
            if self.is_closing:
                return
                
            gc.collect()
            
            # Clean up dead browser tab references
            dead_tabs = []
            for tab_index, browser in list(self.browser_tabs.items()):
                try:
                    if not hasattr(browser, 'isVisible') or not browser.parent():
                        dead_tabs.append(tab_index)
                except RuntimeError:
                    dead_tabs.append(tab_index)
            
            for tab_index in dead_tabs:
                if tab_index in self.browser_tabs:
                    del self.browser_tabs[tab_index]
            
            if dead_tabs:
                print(f"Cleaned up {len(dead_tabs)} dead browser tab references")
                
        except Exception as e:
            print(f"Error during resource cleanup: {e}")

    def create_left_section(self):
        """Create the left section with game view and chat panel"""
        self.left_widget = QWidget()
        left_layout = QVBoxLayout(self.left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        # Create vertical splitter for game view and chat
        self.left_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Create game section
        self.create_game_section()
        
        # Create chat panel - NOTE: Chat panel uses its own font system (external IRC)
        self.chat_panel = ChatPanel()
        self.chat_panel.instance_id = self.instance_id
        print("Chat panel created with original font system (external IRC)")
        
        # Add to vertical splitter
        self.left_vertical_splitter.addWidget(self.game_widget)
        self.left_vertical_splitter.addWidget(self.chat_panel)
        
        # Restore vertical splitter sizes
        game_height = 600
        chat_height = self.config.get("chat_panel_height", 200)
        self.left_vertical_splitter.setSizes([game_height, chat_height])
        
        # Restore chat panel visibility
        chat_visible = self.config.get("chat_panel_visible", True)
        if not chat_visible:
            self.chat_panel.hide()
        
        # Connect splitter moved signal
        self.left_vertical_splitter.splitterMoved.connect(self.on_vertical_splitter_moved)
        
        left_layout.addWidget(self.left_vertical_splitter)
        self.main_horizontal_splitter.addWidget(self.left_widget)

    def create_game_section(self):
        """Create the main game section with tabs - starts with detail page loaded"""
        self.game_widget = QWidget()
        game_layout = QVBoxLayout(self.game_widget)
        game_layout.setContentsMargins(0, 0, 0, 0)
        game_layout.setSpacing(5)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_browser_tab)
        
        # Tab styling - will be overridden by force_apply_readable_fonts
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #2a2a2a;
                border-radius: 0px;
            }
            QTabBar::tab {
                background-color: #4a4a4a;
                border: 2px solid #2a2a2a;
                border-radius: 0px;
                padding: 5px 14px;
                margin: 1px;
                min-width: 80px;
                max-height: 30px;
                color: #f5e6c0;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #3a3a3a;
                border-color: #2a2a2a;
                color: #f5e6c0;
            }
            QTabBar::tab:hover:!selected {
                background-color: #505050;
                border-color: #8b4a4a;
            }
        """)
        
        # Game view tab - Start with detail page loaded
        game_url = "https://2004.lostcity.rs/detail"
        print(f"Starting with detail page: {game_url}")
        
        self.game_view = GameViewWidget(game_url)
        self.game_view.instance_id = self.instance_id
        
        # Connect to URL changes to update world info
        self.game_view.page().urlChanged.connect(self.on_game_url_changed)
        
        # Restore zoom factor
        saved_zoom = self.config.get("zoom_factor", 1.0)
        self.game_view.setZoomFactor(saved_zoom)
        self.game_view.zoom_factor = saved_zoom
        
        # Add game tab
        lost_city_icon_path = get_icon_path("Lost City")
        tab_index = self.tab_widget.addTab(self.game_view, "Lost City")
        
        # Set icon if available
        if os.path.exists(lost_city_icon_path) and lost_city_icon_path.endswith('.png'):
            icon = QIcon(lost_city_icon_path)
            self.tab_widget.setTabIcon(tab_index, icon)
        
        # Make game tab unclosable
        self.tab_widget.tabBar().setTabButton(0, self.tab_widget.tabBar().ButtonPosition.RightSide, None)
        
        game_layout.addWidget(self.tab_widget)

    def create_right_section(self):
        """Create the right tools panel"""
        self.tools_panel = RightToolsPanel()
        self.tools_panel.browser_requested.connect(self.open_browser_tab)
        self.tools_panel.chat_toggle_requested.connect(self.toggle_chat_panel)
        self.tools_panel.panel_collapse_requested.connect(self.on_panel_collapse_requested)
        self.tools_panel.world_switch_requested.connect(self.open_world_switcher)
        self.main_horizontal_splitter.addWidget(self.tools_panel)

        # Restore horizontal splitter sizes based on saved collapse state
        collapsed = self.config.get("right_panel_collapsed", False)
        if collapsed:
            total_width = 1440
            left_width = total_width - 25
            self.main_horizontal_splitter.setSizes([left_width, 25])
        else:
            panel_width = self.config.get("right_panel_width", 250)
            total_width = 1440
            left_width = total_width - panel_width
            self.main_horizontal_splitter.setSizes([left_width, panel_width])
        
        # Connect splitter moved signal
        self.main_horizontal_splitter.splitterMoved.connect(self.on_horizontal_splitter_moved)

        # Add to main layout
        self.main_layout.addWidget(self.main_horizontal_splitter)
        self.update_header_status(self._header_world_info)

    def on_panel_collapse_requested(self, expanded):
        """Handle panel expand request"""
        if expanded:
            panel_width = self.config.get("right_panel_width", 250)
            total_width = self.main_horizontal_splitter.width()
            left_width = total_width - panel_width
            self.main_horizontal_splitter.setSizes([left_width, panel_width])

    def toggle_chat_panel(self):
        """Toggle visibility of chat panel"""
        if self.chat_panel.isVisible():
            self.chat_panel.hide()
            self.config["chat_panel_visible"] = False
        else:
            self.chat_panel.show()
            self.config["chat_panel_visible"] = True
        
        # Update the right panel button color
        self.tools_panel.update_chat_button_style(self.config["chat_panel_visible"])
        
        # Save immediately
        config.save_config(self.config)

    def open_browser_tab(self, url, title):
        """Open a tool in a new tab within the main window"""
        print(f"Opening browser tab: {title} - {url}")
        
        icon_path = get_icon_path(title)
        
        if os.path.exists(icon_path) and icon_path.endswith('.png'):
            tab_title = title
        else:
            tab_title = f"{icon_path} {title}"
        
        # Check if tab already exists
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_title or self.tab_widget.tabText(i) == f"{icon_path} {title}":
                self.tab_widget.setCurrentIndex(i)
                return
        
        try:
            if '?' in url:
                unique_url = f"{url}&instance={self.instance_id}"
            else:
                unique_url = f"{url}?instance={self.instance_id}"
                
            browser = InGameBrowser(unique_url, title)
            browser.closed.connect(lambda: self.close_browser_by_widget(browser))
            
            tab_index = self.tab_widget.addTab(browser, tab_title)
            
            if os.path.exists(icon_path) and icon_path.endswith('.png'):
                icon = QIcon(icon_path)
                self.tab_widget.setTabIcon(tab_index, icon)
            
            self.tab_widget.setCurrentIndex(tab_index)
            self.browser_tabs[tab_index] = browser
            
        except Exception as e:
            print(f"Error creating browser tab: {e}")

    def close_browser_tab(self, index):
        """Close a browser tab with proper cleanup"""
        if index == 0:  # Don't close the main game tab
            return
            
        widget = self.tab_widget.widget(index)
        if widget:
            if hasattr(widget, 'cleanup_cache_files'):
                try:
                    widget.cleanup_cache_files()
                except Exception as e:
                    print(f"Error cleaning up browser tab cache: {e}")
            
            if index in self.browser_tabs:
                del self.browser_tabs[index]
            
            self.tab_widget.removeTab(index)
            widget.deleteLater()
            
            if config.get_config_value("resource_optimization", True):
                gc.collect()

    def close_browser_by_widget(self, browser_widget):
        """Close browser tab by widget reference"""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.widget(i) == browser_widget:
                self.close_browser_tab(i)
                break
    
    def open_world_switcher(self):
        """Open or focus the world switcher window"""
        if self.world_switcher_window is None:
            # Get current world URL from game view
            current_url = self.game_view.url().toString()
            
            # Create world switcher window
            self.world_switcher_window = WorldSwitcherWindow(current_url, self)
            self.world_switcher_window.world_selected.connect(self.on_world_selected)
            
            # Give reference to tools panel
            self.tools_panel.set_world_switcher_window(self.world_switcher_window)
        
        # Show and focus the window
        self.world_switcher_window.show()
        self.world_switcher_window.activateWindow()
        self.world_switcher_window.raise_()
    
    def on_world_selected(self, world_url, world_info, is_high_detail):
        """Handle world selection from world switcher"""
        print(f"Switching to: {world_info}")
        print(f"URL: {world_url}")
        print(f"High Detail: {is_high_detail}")
        
        # Load the new world in the game view
        self.game_view.setUrl(QUrl(world_url))
        
        # Update world info display in right panel
        self.tools_panel.update_world_info(world_info)
        self.update_header_status(world_info)
        
        # Save the selected world to config
        config.set_config_value("last_world_url", world_url)
        config.set_config_value("last_world_info", world_info)
    
    def update_world_info_from_url(self, url):
        """Update world info display by parsing the URL - ONLY show world info for recognized worlds"""
        url_string = url if isinstance(url, str) else url.toString()
        
        # Extract world number
        world_match = re.search(r'world[=:](\d+)', url_string, re.IGNORECASE)
        if not world_match:
            self.tools_panel.update_world_info("No world")
            self.update_header_status("No world")
            return
        
        world_num = world_match.group(1)
        
        # Extract detail mode
        is_high_detail = 'detail=high' in url_string.lower()
        is_low_detail = 'detail=low' in url_string.lower()
        
        # Only show world info if we have both a world number and detail mode
        if not is_high_detail and not is_low_detail:
            self.tools_panel.update_world_info("No world")
            self.update_header_status("No world")
            return
        
        detail_text = "HD" if is_high_detail else "LD"
        
        # Map world numbers to locations (from WORLDS_CONFIG)
        location_map = {
            '1': 'US',
            '2': 'US',
            '3': 'Finland',
            '4': 'Finland',
            '9': 'Australia',
            '11': 'Japan',
            '13': 'US',
            '15': 'US',
            '17': 'Singapore',
        }
        
        location = location_map.get(world_num, 'Unknown')
        world_info = f"W{world_num} {location} ({detail_text})"
        
        self.tools_panel.update_world_info(world_info)
        self.update_header_status(world_info)
        
        # Save to config
        config.set_config_value("last_world_url", url_string)
        config.set_config_value("last_world_info", world_info)
    
    def on_game_url_changed(self, url):
        """Handle game view URL changes"""
        url_string = url.toString()
        print(f"Game URL changed: {url_string}")
        
        # Update world info display from URL
        self.update_world_info_from_url(url_string)
        
        # Update world switcher if it's open
        if self.world_switcher_window:
            self.world_switcher_window.update_current_world(url_string)

    def on_vertical_splitter_moved(self, pos, index):
        """Save vertical splitter position to config"""
        if not self.is_closing:
            self.resize_timer.start(1000)  # Save after 1 second of no movement

    def on_horizontal_splitter_moved(self, pos, index):
        """Handle horizontal splitter movement"""
        if not self.is_closing:
            sizes = self.main_horizontal_splitter.sizes()
            if len(sizes) >= 2:
                right_width = sizes[1]
                
                # If panel is dragged to very small width, collapse it
                if right_width < 50:
                    self.tools_panel.set_collapsed_state(True)
                    total_width = self.main_horizontal_splitter.width()
                    self.main_horizontal_splitter.setSizes([total_width - 25, 25])
                elif right_width >= 50 and self.tools_panel.collapsed:
                    # Panel is being expanded
                    self.tools_panel.set_collapsed_state(False)
                    panel_width = self.config.get("right_panel_width", 250)
                    total_width = self.main_horizontal_splitter.width()
                    self.main_horizontal_splitter.setSizes([total_width - panel_width, panel_width])
                else:
                    # Save the panel width when not collapsed
                    if not self.tools_panel.collapsed:
                        self.config["right_panel_width"] = right_width
                
                self.resize_timer.start(1000)

    def save_current_state_to_config(self):
        """Save current window state to config"""
        try:
            # Save window geometry
            geom = self.geometry()
            self.config["window_geometry"] = [geom.x(), geom.y(), geom.width(), geom.height()]
            
            # Save vertical splitter sizes  
            v_sizes = self.left_vertical_splitter.sizes()
            if len(v_sizes) >= 2:
                self.config["chat_panel_height"] = v_sizes[1]
            
            # Save horizontal splitter state
            h_sizes = self.main_horizontal_splitter.sizes()
            if len(h_sizes) >= 2 and not self.tools_panel.collapsed:
                self.config["right_panel_width"] = h_sizes[1]
            
            # Save zoom factors
            if hasattr(self, 'game_view'):
                self.config["zoom_factor"] = self.game_view.zoom_factor
            
            if hasattr(self.chat_panel, 'chat_zoom_factor'):
                self.config["chat_zoom_factor"] = self.chat_panel.chat_zoom_factor
            
            # Save panel states
            self.config["chat_panel_visible"] = self.chat_panel.isVisible()
            self.config["right_panel_collapsed"] = self.tools_panel.collapsed
            
        except Exception as e:
            print(f"Error saving current state: {e}")

    def save_window_state_debounced(self):
        """Save window state after debouncing timer expires"""
        if self.is_closing:
            return
            
        try:
            self.save_current_state_to_config()
            config.save_config(self.config)
            self.update_header_status(saved_now=True)
            print("Window state saved to config")
        except Exception as e:
            print(f"Error saving window state: {e}")

    def moveEvent(self, event):
        """Handle window move with debounced saving"""
        super().moveEvent(event)
        if not self.is_closing:
            self.resize_timer.start(1000)

    def resizeEvent(self, event):
        """Handle window resize with proper panel width maintenance"""
        super().resizeEvent(event)
        if not self.is_closing:
            # Maintain panel widths on window resize
            if hasattr(self, 'tools_panel'):
                if self.tools_panel.collapsed:
                    total_width = self.width()
                    left_width = total_width - 25
                    self.main_horizontal_splitter.setSizes([left_width, 25])
                else:
                    total_width = self.width()
                    panel_width = self.config.get("right_panel_width", 250)
                    left_width = total_width - panel_width
                    self.main_horizontal_splitter.setSizes([left_width, panel_width])
            
            self.resize_timer.start(1000)

    def closeEvent(self, event):
        """Save window state when closing with comprehensive cleanup"""
        self.is_closing = True
        
        try:
            # Stop all timers
            if hasattr(self, 'resource_timer'):
                self.resource_timer.stop()
            if hasattr(self, 'resize_timer'):
                self.resize_timer.stop()
            if hasattr(self, 'config_save_timer'):
                self.config_save_timer.stop()
            
            # Save final state
            self.save_current_state_to_config()
            config.save_config(self.config)
            print("Final config save completed")
            
            # Close all browser tabs
            for i in range(self.tab_widget.count() - 1, 0, -1):
                self.close_browser_tab(i)
            
            # Clean up tools panel
            if hasattr(self.tools_panel, 'close_all_tool_windows'):
                self.tools_panel.close_all_tool_windows()
            
            # Final garbage collection
            gc.collect()
            print("Application cleanup completed - all settings preserved")
            
        except Exception as e:
            print(f"Error during window close cleanup: {e}")
        
        event.accept()
