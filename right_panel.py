# right_panel.py
import weakref
import gc
import time
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QGroupBox, 
                             QCheckBox, QScrollArea, QLabel, QMainWindow, QMessageBox, QHBoxLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import QUrl, Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor, QPalette
from config import load_config, save_config, get_config_value, set_config_value
from styles import get_icon_path, get_tool_urls
from font_loader import font_loader
import config


class ToolWindow(QMainWindow):
    closed = pyqtSignal()
    
    def __init__(self, url, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"LostKit - {title}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # CRITICAL: Make window appear as separate task in Windows taskbar
        self.setWindowFlags(Qt.WindowType.Window)
        
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
        self.setPalette(palette)
        
        self.tool_name = title
        self.load_window_geometry()
        self.setMinimumSize(600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        profile_name = f"ToolWindow_{title.replace(' ', '_')}"
        
        try:
            profile = QWebEngineProfile(profile_name, self)
            cache_path = config.get_persistent_cache_path(f"tool_{title.replace(' ', '_')}")
            storage_path = config.get_persistent_profile_path(f"tool_{title.replace(' ', '_')}")
            
            profile.setCachePath(cache_path)
            profile.setPersistentStoragePath(storage_path)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            
            settings = profile.settings()
            if get_config_value("resource_optimization", True):
                settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
                settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, False)
                settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, False)

            page = QWebEnginePage(profile, self)
            self.web_view = QWebEngineView()
            self.web_view.setPage(page)
            
            self.profile_name = profile_name
            self.cache_path = cache_path
            self.storage_path = storage_path
            self._profile = profile
            
        except Exception as e:
            print(f"Error creating web engine profile: {e}")
            self.web_view = QWebEngineView()
            self.profile_name = None
            self.cache_path = None
            self.storage_path = None
            self._profile = None
        
        layout.addWidget(self.web_view)
        self.web_view.setUrl(QUrl(url))
        
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.timeout.connect(self.perform_cleanup)
        cleanup_interval = get_config_value("cache_cleanup_interval", 300) * 1000
        self.cleanup_timer.start(cleanup_interval)
        
        QTimer.singleShot(100, self.force_apply_readable_fonts)

    def force_apply_readable_fonts(self):
        font = QFont()
        if font_loader.is_custom_font_available():
            font.setFamily(font_loader.get_font_family_name())
        else:
            test_font = QFont("Runescape-Quill-Caps", 18)
            if test_font.exactMatch():
                font.setFamily("Runescape-Quill-Caps")
            else:
                font.setFamily("Arial")
        
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Normal)
        self.setFont(font)

    def load_window_geometry(self):
        try:
            config_key = f"tool_window_geometry_{self.tool_name.replace(' ', '_')}"
            geom = get_config_value(config_key, None)
            
            if geom and isinstance(geom, list) and len(geom) == 4:
                x, y, w, h = [int(val) for val in geom]
                x = max(0, min(x, 1920 - w))
                y = max(0, min(y, 1080 - h))
                w = max(600, min(w, 1920))
                h = max(400, min(h, 1080))
                self.setGeometry(x, y, w, h)
            else:
                offset = hash(self.tool_name) % 10 * 25
                self.setGeometry(200 + offset, 200 + offset, 1000, 800)
        except (ValueError, TypeError) as e:
            self.setGeometry(200, 200, 1000, 800)

    def save_window_geometry(self):
        try:
            geom = self.geometry()
            config_key = f"tool_window_geometry_{self.tool_name.replace(' ', '_')}"
            set_config_value(config_key, [geom.x(), geom.y(), geom.width(), geom.height()])
        except Exception as e:
            print(f"Error saving tool window geometry: {e}")

    def perform_cleanup(self):
        try:
            if get_config_value("resource_optimization", True):
                gc.collect()
        except Exception as e:
            print(f"Error during tool window cleanup: {e}")

    def cleanup_cache_files(self):
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, 'save_timer'):
            self.save_timer = QTimer(self)
            self.save_timer.setSingleShot(True)
            self.save_timer.timeout.connect(self.save_window_geometry)
        self.save_timer.start(1000)

    def moveEvent(self, event):
        super().moveEvent(event)
        if not hasattr(self, 'save_timer'):
            self.save_timer = QTimer(self)
            self.save_timer.setSingleShot(True)
            self.save_timer.timeout.connect(self.save_window_geometry)
        self.save_timer.start(1000)

    def closeEvent(self, event):
        self.save_window_geometry()
        if hasattr(self, 'cleanup_timer'):
            self.cleanup_timer.stop()
        if hasattr(self, 'web_view') and self.web_view:
            try:
                self.web_view.setPage(None)
                self.web_view.deleteLater()
            except Exception as e:
                print(f"Error cleaning up web view: {e}")
        self.closed.emit()
        gc.collect()
        event.accept()


class InGameBrowser(QWidget):
    closed = pyqtSignal()
    
    def __init__(self, url, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.url = url
        self.title = title
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        profile_name = f"InGameBrowser_{title.replace(' ', '_')}"
        
        try:
            profile = QWebEngineProfile(profile_name, self)
            cache_path = config.get_persistent_cache_path(f"ingame_{title.replace(' ', '_')}")
            storage_path = config.get_persistent_profile_path(f"ingame_{title.replace(' ', '_')}")
                
            profile.setCachePath(cache_path)
            profile.setPersistentStoragePath(storage_path)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            
            settings = profile.settings()
            if get_config_value("resource_optimization", True):
                settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)

            page = QWebEnginePage(profile, self)
            self.web_view = QWebEngineView()
            self.web_view.setPage(page)
            
            self.profile_name = profile_name
            self.cache_path = cache_path
            self.storage_path = storage_path
            self._profile = profile
            
        except Exception as e:
            print(f"Error creating in-game browser profile: {e}")
            self.web_view = QWebEngineView()
            self.profile_name = None
            self.cache_path = None
            self.storage_path = None
            self._profile = None
        
        layout.addWidget(self.web_view)
        self.web_view.setUrl(QUrl(url))

    def cleanup_cache_files(self):
        pass

    def closeEvent(self, event):
        if hasattr(self, 'web_view') and self.web_view:
            try:
                self.web_view.setPage(None)
                self.web_view.deleteLater()
            except Exception as e:
                print(f"Error cleaning up web view: {e}")
        self.closed.emit()
        event.accept()


class RightToolsPanel(QWidget):
    browser_requested = pyqtSignal(str, str)
    chat_toggle_requested = pyqtSignal()
    panel_collapse_requested = pyqtSignal(bool)
    world_switch_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.config = load_config()
        
        self.tool_windows = weakref.WeakValueDictionary()
        self.window_count = 0
        self.world_info_timestamp = time.time()
        self.last_tool_cleanup = time.time()
        
        self.world_switcher_window = None
        self.current_world_info = "No world"  # Default to "No world" on startup
        
        self.collapsed = get_config_value("right_panel_collapsed", False)
        self.saved_width = self.config.get("right_panel_width", 250)
        
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
        self.setPalette(palette)
        
        self.optimal_width = self.calculate_optimal_width()
        
        if self.collapsed:
            self.setFixedWidth(25)
        else:
            self.setFixedWidth(self.optimal_width)
        
        self.setup_ui()
        QTimer.singleShot(100, self.force_apply_readable_fonts)
        
    def force_apply_readable_fonts(self):
        button_font = QFont()
        if font_loader.is_custom_font_available():
            button_font.setFamily(font_loader.get_font_family_name())
        else:
            test_font = QFont("Runescape-Quill-Caps", 18)
            if test_font.exactMatch():
                button_font.setFamily("Runescape-Quill-Caps")
            else:
                button_font.setFamily("Arial")
        
        button_font.setPointSize(20)
        button_font.setWeight(QFont.Weight.Normal)
        
        group_font = QFont()
        group_font.setFamily(button_font.family())
        group_font.setPointSize(22)
        group_font.setWeight(QFont.Weight.Bold)
        
        checkbox_font = QFont()
        checkbox_font.setFamily(button_font.family())
        checkbox_font.setPointSize(18)
        
        self.apply_fonts_to_children(self, button_font, group_font, checkbox_font)
    
    def apply_fonts_to_children(self, widget, button_font, group_font, checkbox_font):
        try:
            if isinstance(widget, QPushButton):
                widget.setFont(button_font)
            elif isinstance(widget, QGroupBox):
                widget.setFont(group_font)
            elif isinstance(widget, QCheckBox):
                widget.setFont(checkbox_font)
            elif isinstance(widget, QLabel):
                widget.setFont(button_font)
            else:
                widget.setFont(button_font)
            
            for child in widget.findChildren(QWidget):
                self.apply_fonts_to_children(child, button_font, group_font, checkbox_font)
                
        except Exception as e:
            print(f"Error applying fonts: {e}")
        
    def calculate_optimal_width(self):
        base_button_width = 160
        total_width = base_button_width + 16 + 23 + 8 + 10 + 16 + 8
        return total_width
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)
        
        if self.collapsed:
            self.setup_collapsed_ui(main_layout)
        else:
            self.setup_expanded_ui(main_layout)

    def setup_collapsed_ui(self, main_layout):
        self.clear_layout(main_layout)
        
        main_layout.addStretch()
        
        expand_container = QWidget()
        expand_container.setFixedHeight(40)
        expand_layout = QHBoxLayout(expand_container)
        expand_layout.setContentsMargins(0, 0, 2, 0)
        
        self.expand_btn = QPushButton("▶")
        self.expand_btn.setFixedSize(18, 35)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b4a4a;
                border: 1px solid #2a2a2a;
                border-radius: 2px;
                color: #f5e6c0;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #a55a5a;
            }
        """)
        self.expand_btn.clicked.connect(self.expand_panel)
        
        expand_layout.addStretch()
        expand_layout.addWidget(self.expand_btn)
        
        main_layout.addWidget(expand_container)
        main_layout.addStretch()

    def setup_expanded_ui(self, main_layout):
        self.clear_layout(main_layout)
        
        # Current world display with button.jpg background
        self.world_info_label = self.create_world_info_display()
        main_layout.addWidget(self.world_info_label)
        
        # Settings panel
        settings_group = QGroupBox("Settings")
        settings_group.setStyleSheet("""
            QGroupBox {
                background: #000000;
                color: #f5e6c0;
                font-weight: bold;
                border: 2px solid #2a2a2a;
                border-radius: 0px;
                margin: 3px 0px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                background-color: #2a2a2a;
            }
        """)
        settings_layout = QVBoxLayout()
        settings_layout.setContentsMargins(8, 8, 8, 8)
        settings_layout.setSpacing(5)
        
        self.external_cb = QCheckBox("Open tools externally")
        # CHANGE: Load saved state from config
        saved_external = get_config_value("open_external", True)
        self.external_cb.setChecked(saved_external)
        self.external_cb.stateChanged.connect(self.toggle_external_mode)
        self.external_cb.setStyleSheet("""
            QCheckBox {
                color: #f5e6c0;
                spacing: 8px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #4a4a4a;
                border: 2px solid #2a2a2a;
                border-radius: 0px;
            }
            QCheckBox::indicator:checked {
                background-color: #8b4a4a;
                border: 2px solid #2a2a2a;
                border-radius: 0px;
            }
        """)
        settings_layout.addWidget(self.external_cb)
        
        settings_group.setLayout(settings_layout)
        settings_group.setMaximumHeight(70)
        main_layout.addWidget(settings_group)
        
        # World Switcher button
        self.world_switcher_btn = QPushButton("World Switcher")
        self.world_switcher_btn.setFixedHeight(35)
        self.world_switcher_btn.clicked.connect(self.open_world_switcher)
        self.world_switcher_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b4a4a;
                border: 2px solid #2a2a2a;
                border-radius: 0px;
                padding: 8px 12px;
                color: #f5e6c0;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #a55a5a;
                border-color: #8b4a4a;
            }
            QPushButton:pressed {
                background-color: #8b4a4a;
                border: 2px inset #2a2a2a;
            }
        """)
        self.apply_world_switcher_icon()
        main_layout.addWidget(self.world_switcher_btn)
        
        # IRC Chat toggle button
        self.chat_toggle_btn = QPushButton("IRC Chat")
        self.chat_toggle_btn.setFixedHeight(35)
        self.chat_toggle_btn.clicked.connect(self.toggle_chat)
        
        is_visible = self.config.get("chat_panel_visible", True)
        self.update_chat_button_style(is_visible)
        
        main_layout.addWidget(self.chat_toggle_btn)
        
        # Tools panel
        tools_group = QGroupBox("Tools")
        tools_group.setStyleSheet("""
            QGroupBox {
                background: #000000;
                color: #f5e6c0;
                font-weight: bold;
                border: 2px solid #2a2a2a;
                border-radius: 0px;
                margin: 3px 0px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                background-color: #2a2a2a;
            }
        """)
        tools_layout = QVBoxLayout()
        tools_layout.setContentsMargins(5, 5, 5, 5)
        tools_layout.setSpacing(4)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: #000000;
                border: 1px solid #2a2a2a;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 14px;
                border: 1px solid #2a2a2a;
            }
            QScrollBar::handle:vertical {
                background: #8b4a4a;
                min-height: 20px;
                border-radius: 0px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a55a5a;
            }
        """)
        
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: #000000;")
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.setContentsMargins(5, 5, 20, 5)
        
        self.tool_buttons = []
        tool_urls = get_tool_urls()
        for tool_name, url in tool_urls.items():
            btn = self.create_tool_button(tool_name, url)
            self.scroll_layout.addWidget(btn)
            self.tool_buttons.append(btn)
        
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_widget)
        tools_layout.addWidget(self.scroll_area)
        
        tools_group.setLayout(tools_layout)
        main_layout.addWidget(tools_group, 1)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def create_world_info_display(self):
        """Create the world info display widget with button.jpg background and larger, readable text"""
        world_label = QLabel(self.current_world_info)
        world_label.setFixedHeight(65)  # Increased height for better text display
        world_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        world_label.setWordWrap(True)
        
        button_image_path = "button.jpg"
        if os.path.exists(button_image_path):
            world_label.setStyleSheet(f"""
                QLabel {{
                    background: url({button_image_path}) center center stretch;
                    border: 2px solid #2a2a2a;
                    border-radius: 0px;
                    padding: 6px 8px;
                    color: #f5e6c0;
                    font-weight: bold;
                    font-size: 26px;  /* Increased font size for readability */
                }}
            """)
        else:
            world_label.setStyleSheet("""
                QLabel {
                    background-color: #3a3a3a;
                    border: 2px solid #2a2a2a;
                    border-radius: 0px;
                    padding: 6px 8px;
                    color: #f5e6c0;
                    font-weight: bold;
                    font-size: 26px;  /* Increased font size for readability */
                }
            """)
        
        if hasattr(self, "world_info_timestamp"):
            try:
                tooltip_time = time.strftime("%I:%M:%S %p", time.localtime(self.world_info_timestamp))
                world_label.setToolTip(f"Updated {tooltip_time}")
            except Exception:
                world_label.setToolTip("World information")
        else:
            world_label.setToolTip("World information")
        
        return world_label
    
    def apply_world_switcher_icon(self):
        """Apply a crisp icon to the world switcher button using QPixmap scaling."""
        try:
            icon_path = get_icon_path("World Map")
            if not isinstance(icon_path, str) or not icon_path.endswith(".png"):
                return
            if not os.path.exists(icon_path):
                return

            pixmap = QPixmap(icon_path)
            if pixmap.isNull():
                return

            icon_size = QSize(26, 26)
            scaled_pixmap = pixmap.scaled(
                icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.world_switcher_btn.setIcon(QIcon(scaled_pixmap))
            self.world_switcher_btn.setIconSize(icon_size)
        except Exception as e:
            print(f"Error applying world switcher icon: {e}")
    
    def update_world_info(self, world_info):
        """Update the world info display"""
        self.current_world_info = world_info
        self.world_info_timestamp = time.time()
        
        if hasattr(self, 'world_info_label') and self.world_info_label:
            self.world_info_label.setText(world_info)
            try:
                tooltip_time = time.strftime("%I:%M:%S %p", time.localtime(self.world_info_timestamp))
                self.world_info_label.setToolTip(f"Updated {tooltip_time}")
            except Exception:
                self.world_info_label.setToolTip("World information")
        self.config["current_world_info"] = world_info
        
        try:
            config_data = load_config()
            config_data["current_world_info"] = world_info
            save_config(config_data)
        except Exception as e:
            print(f"Error persisting world info: {e}")
    
    def open_world_switcher(self):
        """Open or focus the world switcher window"""
        self.world_switch_requested.emit()
    
    def set_world_switcher_window(self, window):
        """Set reference to the world switcher window"""
        self.world_switcher_window = window

    def expand_panel(self):
        self.collapsed = False
        set_config_value("right_panel_collapsed", False)
        self.setFixedWidth(self.optimal_width)
        main_layout = self.layout()
        self.setup_expanded_ui(main_layout)
        self.panel_collapse_requested.emit(False)
        QTimer.singleShot(100, self.force_apply_readable_fonts)

    def set_collapsed_state(self, collapsed):
        if self.collapsed != collapsed:
            self.collapsed = collapsed
            set_config_value("right_panel_collapsed", collapsed)
            
            if collapsed:
                self.setFixedWidth(25)
            else:
                self.setFixedWidth(self.optimal_width)
            
            main_layout = self.layout()
            if collapsed:
                self.setup_collapsed_ui(main_layout)
            else:
                self.setup_expanded_ui(main_layout)
                QTimer.singleShot(100, self.force_apply_readable_fonts)

    def update_chat_button_style(self, is_visible):
        if self.collapsed:
            return
            
        if is_visible:
            self.chat_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a6a4a;
                    border: 2px solid #2a2a2a;
                    border-radius: 0px;
                    padding: 8px 12px;
                    color: #f5e6c0;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #5a7a5a;
                }
            """)
        else:
            self.chat_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #8b4a4a;
                    border: 2px solid #2a2a2a;
                    border-radius: 0px;
                    padding: 8px 12px;
                    color: #f5e6c0;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #a55a5a;
                }
            """)

    def toggle_chat(self):
        self.chat_toggle_requested.emit()

    def create_tool_button(self, name, url):
        icon_path = get_icon_path(name)
        
        display_name = name
        if len(name) > 12:
            if name == "Clue Coordinates":
                display_name = "Coordinates"
            elif name == "Clue Scroll Help":
                display_name = "Clue Help"
            elif name == "Market Prices":
                display_name = "Prices"
        
        if os.path.exists(icon_path) and icon_path.endswith('.png'):
            btn = QPushButton()
            icon = QIcon(icon_path)
            btn.setIcon(icon)
            btn.setIconSize(QSize(26, 26))
            btn.setText(display_name)
        else:
            btn = QPushButton(f"{icon_path} {display_name}")
        
        btn.setStyleSheet(self.get_button_style())
        btn.setFixedHeight(42)
        btn.setMinimumWidth(160)
        btn.setMaximumWidth(200)
        
        btn.clicked.connect(lambda checked, n=name, u=url: self.open_tool(n, u))
        return btn

    def get_button_style(self):
        button_image_path = "button.jpg"
        base_style = """
            QPushButton {
                border: 2px solid #2a2a2a;
                border-radius: 0px;
                padding: 6px 10px;
                color: #f5e6c0;
                font-weight: bold;
                font-size: 20px;
                min-height: 38px;
                max-height: 42px;
                text-align: left;
        """
        
        if os.path.exists(button_image_path):
            base_style += f"background: url({button_image_path}) center center stretch;"
        else:
            base_style += "background-color: #8b4a4a;"
        
        base_style += """
            }
            QPushButton:hover {
                border-color: #8b4a4a;
                background-color: rgba(139, 74, 74, 120);
            }
            QPushButton:pressed {
                border: 2px inset #2a2a2a;
                background-color: rgba(139, 74, 74, 150);
            }
        """
        
        return base_style
        
    def open_tool(self, name, url):
        max_windows = get_config_value("max_tool_windows", 10)
        external_mode = get_config_value("open_external", True)
        
        if external_mode:
            self.cleanup_dead_windows()
            
            # CHANGE: Check if tool window already exists for this tool
            if name in self.tool_windows:
                existing_window = self.tool_windows[name]
                try:
                    # Bring existing window to front instead of creating new one
                    existing_window.show()
                    existing_window.activateWindow()
                    existing_window.raise_()
                    print(f"Bringing existing {name} window to front")
                    return
                except Exception as e:
                    print(f"Error activating existing window: {e}")
                    # Remove dead reference and continue to create new window
                    del self.tool_windows[name]
            
            if len(self.tool_windows) >= max_windows:
                QMessageBox.warning(
                    self, 
                    "Window Limit Reached",
                    f"Maximum number of tool windows ({max_windows}) reached.\nPlease close some windows before opening new ones.",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            try:
                tool_window = ToolWindow(url, name, self)
                # CHANGE: Connect closed signal to remove from tracking
                tool_window.closed.connect(lambda: self.on_tool_window_closed(name))
                tool_window.show()
                self.tool_windows[name] = tool_window
                self.window_count = len(self.tool_windows)
            except Exception as e:
                print(f"Error creating tool window: {e}")
        else:
            self.browser_requested.emit(url, name)

    def on_tool_window_closed(self, tool_name):
        """Handle tool window closed signal - remove from tracking"""
        if tool_name in self.tool_windows:
            del self.tool_windows[tool_name]
            print(f"Removed {tool_name} from tool windows tracking")
        self.window_count = len(self.tool_windows)

    def cleanup_dead_windows(self):
        dead_keys = []
        for key, window_ref in list(self.tool_windows.items()):
            try:
                if not hasattr(window_ref, 'isVisible') or not window_ref.isVisible():
                    dead_keys.append(key)
            except RuntimeError:
                dead_keys.append(key)
        
        for key in dead_keys:
            if key in self.tool_windows:
                del self.tool_windows[key]
        if dead_keys:
            self.last_tool_cleanup = time.time()
            self.window_count = len(self.tool_windows)
            
    def toggle_external_mode(self, state):
        external = state == Qt.CheckState.Checked.value
        set_config_value("open_external", external)
        if not external:
            self.close_all_tool_windows()

    def close_all_tool_windows(self):
        windows_to_close = []
        
        for window_ref in list(self.tool_windows.values()):
            try:
                if hasattr(window_ref, 'isVisible') and window_ref.isVisible():
                    windows_to_close.append(window_ref)
            except RuntimeError:
                pass
        
        for window in windows_to_close:
            try:
                window.close()
            except RuntimeError:
                pass
        
        self.tool_windows.clear()
        self.window_count = 0

    def closeEvent(self, event):
        self.close_all_tool_windows()
        gc.collect()
        event.accept()
