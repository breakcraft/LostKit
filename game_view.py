# game_view.py - Fixed syntax error on line 199
import gc
import os
import base64
from pathlib import Path
from datetime import datetime
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QToolTip
from PyQt6.QtGui import QCursor
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings, QWebEngineScript
from PyQt6.QtCore import Qt, QUrl, QDir, pyqtSignal, QTimer, QEvent
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
import config


def _is_lostcity_game_client_url(qurl):
    """Return True if the given QUrl points at the LostCity game client (world rs2.cgi or base /client)."""
    try:
        if not qurl or not qurl.isValid():
            return False
        host = (qurl.host() or "").lower()
        path = (qurl.path() or "").lower()
        # Base client page
        if host == "2004.lostcity.rs" and path.startswith("/client"):
            return True
        # World servers like w2-2004.lostcity.rs running the game under /rs2.cgi
        if host.endswith("-2004.lostcity.rs"):
            # Prefix like w2, w3, etc.
            prefix = host.split("-", 1)[0]
            if prefix.startswith("w") and path.startswith("/rs2.cgi"):
                return True
        return False
    except Exception:
        return False


class GamePage(QWebEnginePage):
    """Custom page that blocks back/forward navigation on protected URLs."""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self._blocked_back_patterns = []
        self._screenshot_handler = None
        self._click_log_handler = None

    def set_blocked_back_patterns(self, patterns):
        self._blocked_back_patterns = [pattern.lower() for pattern in patterns or []]

    def set_screenshot_handler(self, handler):
        self._screenshot_handler = handler

    def set_click_log_handler(self, handler):
        self._click_log_handler = handler

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        try:
            if url.scheme().lower() == "lostkit":
                target = url.host() or url.path().lstrip("/")
                if target and target.lower().startswith("take-screenshot"):
                    if callable(self._screenshot_handler):
                        self._screenshot_handler()
                    return False
        except Exception as e:
            print(f"Error handling custom navigation: {e}")

        if (nav_type == QWebEnginePage.NavigationType.NavigationTypeBackForward and
                self._should_block_back_forward()):
            print("Blocked back/forward navigation while on LostCity client.")
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def triggerAction(self, action, checked=False):
        """Block Back action while on the game client, as an extra safeguard."""
        try:
            if action == QWebEnginePage.WebAction.Back and self._should_block_back_forward():
                print("Blocked Back web action while on LostCity client.")
                return
        except Exception:
            pass
        return super().triggerAction(action, checked)

    # Capture console logs from JS and forward special click markers
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        try:
            if isinstance(message, str) and message.startswith('@@CLICK@@ '):
                payload = message[len('@@CLICK@@ '):]
                if callable(self._click_log_handler):
                    self._click_log_handler(payload)
        except Exception as e:
            print(f"Error processing click console message: {e}")
        # Also print all console messages for visibility
        try:
            print(f"JS[{level}] {sourceID}:{lineNumber}: {message}")
        except Exception:
            pass
        try:
            return super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
        except Exception:
            # Some bindings may not require calling super
            return None

    def _should_block_back_forward(self):
        try:
            view = self.view()
            if view is None:
                return False
            current = view.url()
            if not current.isValid():
                return False
            # Block for known game client URLs OR any configured static prefixes
            if _is_lostcity_game_client_url(current):
                return True
            current_str = current.toString().lower()
            return any(current_str.startswith(pattern) for pattern in self._blocked_back_patterns)
        except Exception as e:
            print(f"Error checking back navigation: {e}")
            return False


class GameViewWidget(QWebEngineView):
    zoom_changed = pyqtSignal(float)
    screenshot_requested = pyqtSignal()
    
    def __init__(self, url, parent=None):
        super().__init__(parent)

        try:
            # Feature toggles from config
            self.click_logging_enabled = bool(config.get_config_value("click_logging_enabled", True))
            self.click_log_to_file = bool(config.get_config_value("click_log_to_file", True))
            self.screenshot_hotkey_enabled = bool(config.get_config_value("screenshot_hotkey_enabled", True))
            self.screenshot_toast_enabled = bool(config.get_config_value("screenshot_toast_enabled", True))
            try:
                self.screenshot_toast_ms = int(config.get_config_value("screenshot_toast_ms", 2000))
            except Exception:
                self.screenshot_toast_ms = 2000
            # Use persistent profile that survives application restarts
            profile_name = "LostCityGame"  # Fixed name, no process ID
            
            profile = QWebEngineProfile(profile_name, self)
            
            # Use persistent directories that survive application restarts
            cache_path = config.get_persistent_cache_path("game_cache")
            storage_path = config.get_persistent_profile_path("game_profile")

            cache_dir = QDir(cache_path)
            if not cache_dir.exists():
                cache_dir.mkpath(".")
            storage_dir = QDir(storage_path)
            if not storage_dir.exists():
                storage_dir.mkpath(".")
            
            print(f"Game using persistent cache: {cache_path}")
            print(f"Game using persistent storage: {storage_path}")
            
            profile.setCachePath(cache_path)
            profile.setPersistentStoragePath(storage_path)
            
            # Force persistent cookies
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            
            # Performance optimizations but keep all login-related features
            settings = profile.settings()
            
            # Enable hardware acceleration and GPU features for game
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            
            # Essential features for game and login functionality
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
            
            # Disable only non-essential features
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
            if config.get_config_value("resource_optimization", True):
                settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)
                settings.setAttribute(QWebEngineSettings.WebAttribute.TouchIconsEnabled, False)

            page = GamePage(profile, self)
            page.set_blocked_back_patterns(
                ["https://2004.lostcity.rs/client"]
            )
            page.set_screenshot_handler(self.handle_screenshot_request)
            if self.click_logging_enabled:
                page.set_click_log_handler(self._handle_click_log)
            # QWebEnginePage has no setView() in PyQt6; binding to the view is done via setPage()
            self.setPage(page)

            # Route all downloads (e.g., game client screenshots) to LCScreenshots
            try:
                profile.downloadRequested.connect(self.on_download_requested)
            except Exception as e:
                print(f"Warning: Could not connect downloadRequested: {e}")
            
            # Store paths for cleanup (but don't delete persistent data)
            self.cache_path = cache_path
            self.storage_path = storage_path

            # Load the game
            self.setUrl(QUrl(url))

            # Load zoom factor from config
            self.zoom_factor = config.get_config_value("zoom_factor", 1.0)
            self.setZoomFactor(self.zoom_factor)

            # Install screenshot hook script to run on all frames
            self.install_screenshot_script()
            # Install click logger across all frames (if enabled)
            if self.click_logging_enabled:
                self.install_click_logger_script()

            # Connect signals
            self.page().loadFinished.connect(self.on_load_finished)
            try:
                self.urlChanged.connect(self._on_url_changed)
            except Exception:
                pass
            
            # Enable focus for keyboard events
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
            # Setup cleanup timer (but preserve persistent data)
            self.cleanup_timer = QTimer(self)
            self.cleanup_timer.timeout.connect(self.perform_cleanup)
            cleanup_interval = config.get_config_value("cache_cleanup_interval", 300) * 1000
            self.cleanup_timer.start(cleanup_interval)
            
        except Exception as e:
            print(f"Error initializing GameViewWidget: {e}")
            self.zoom_factor = 1.0
            self.cache_path = None
            self.storage_path = None

    def perform_cleanup(self):
        """Perform light cleanup without removing persistent data"""
        try:
            if config.get_config_value("resource_optimization", True):
                # Only do memory cleanup, don't touch persistent storage
                gc.collect()
                print("Performed light game view cleanup (preserved login data)")
        except Exception as e:
            print(f"Error during game view cleanup: {e}")

    def on_load_finished(self, ok: bool):
        """Handle page load completion"""
        if ok:
            print("✅ Game page loaded successfully with persistent storage.")
            try:
                self.setZoomFactor(self.zoom_factor)
                QTimer.singleShot(250, self.inject_screenshot_hook)
            except Exception as e:
                print(f"Error setting zoom factor: {e}")
        else:
            print("❌ Failed to load game page.")

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming"""
        try:
            # Hotkey: Ctrl+Shift+S for screenshot
            try:
                if getattr(self, 'screenshot_hotkey_enabled', True):
                    mods = event.modifiers()
                    if (mods & Qt.KeyboardModifier.ControlModifier) and (mods & Qt.KeyboardModifier.ShiftModifier) and event.key() == Qt.Key.Key_S:
                        self.handle_screenshot_request()
                        event.accept()
                        return
            except Exception:
                pass

            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                zoom_step = 0.1
                
                if delta > 0:
                    self.zoom_factor += zoom_step
                else:
                    self.zoom_factor -= zoom_step
                    
                # Clamp zoom factor
                self.zoom_factor = max(0.25, min(self.zoom_factor, 5.0))
                
                # Apply and save zoom
                self.setZoomFactor(self.zoom_factor)
                config.set_config_value("zoom_factor", self.zoom_factor)
                self.zoom_changed.emit(self.zoom_factor)
                
                event.accept()
            else:
                super().wheelEvent(event)
        except Exception as e:
            print(f"Error in wheelEvent: {e}")
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        try:
            # Block navigation keys while on the game client
            try:
                if self._should_block_navigation_buttons():
                    if (event.key() in (getattr(Qt.Key, 'Key_Back', None), getattr(Qt.Key, 'Key_Backspace', None)) or
                        (event.modifiers() & Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_Left)):
                        event.accept()
                        return
            except Exception:
                pass

            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_0:
                    # Ctrl+0: Reset zoom to 100%
                    self.zoom_factor = 1.0
                    self.setZoomFactor(self.zoom_factor)
                    config.set_config_value("zoom_factor", self.zoom_factor)
                    self.zoom_changed.emit(self.zoom_factor)
                    event.accept()
                    return
                elif event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
                    # Ctrl++: Zoom in
                    self.zoom_factor = min(self.zoom_factor + 0.1, 5.0)
                    self.setZoomFactor(self.zoom_factor)
                    config.set_config_value("zoom_factor", self.zoom_factor)
                    self.zoom_changed.emit(self.zoom_factor)
                    event.accept()
                    return
                elif event.key() == Qt.Key.Key_Minus:
                    # Ctrl+-: Zoom out
                    self.zoom_factor = max(self.zoom_factor - 0.1, 0.25)
                    self.setZoomFactor(self.zoom_factor)
                    config.set_config_value("zoom_factor", self.zoom_factor)
                    self.zoom_changed.emit(self.zoom_factor)
                    event.accept()
                    return
            
            super().keyPressEvent(event)
        except Exception as e:
            print(f"Error in keyPressEvent: {e}")
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Also block navigation key releases to avoid fallback handling."""
        try:
            if self._should_block_navigation_buttons():
                if (event.key() in (getattr(Qt.Key, 'Key_Back', None), getattr(Qt.Key, 'Key_Backspace', None)) or
                    (event.modifiers() & Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_Left)):
                    event.accept()
                    return
        except Exception:
            pass
        super().keyReleaseEvent(event)

    # Intercept view-level back/forward programmatic calls
    def back(self):
        try:
            if self._should_block_navigation_buttons():
                print("Blocked view.back() while on LostCity client.")
                return
        except Exception:
            pass
        return super().back()

    def forward(self):
        try:
            if self._should_block_navigation_buttons():
                print("Blocked view.forward() while on LostCity client.")
                return
        except Exception:
            pass
        return super().forward()

    def _apply_game_nav_lock(self):
        """Disable back navigation and clear history when on game client."""
        try:
            if not self._should_block_navigation_buttons():
                # Re-enable back action when not on client
                try:
                    act = self.page().action(QWebEnginePage.WebAction.Back)
                    if act:
                        act.setEnabled(True)
                except Exception:
                    pass
                return
            # On client: clear history and disable back action
            try:
                hist = self.page().history()
                if hist:
                    hist.clear()
            except Exception:
                pass
            try:
                act = self.page().action(QWebEnginePage.WebAction.Back)
                if act:
                    act.setEnabled(False)
            except Exception:
                pass
        except Exception as e:
            print(f"Error applying nav lock: {e}")

    def _on_url_changed(self, qurl):
        # Update nav lock whenever URL changes
        try:
            self._apply_game_nav_lock()
        except Exception as e:
            print(f"Error updating nav lock on URL change: {e}")

    def reset_zoom(self):
        """Reset zoom to 100%"""
        try:
            self.zoom_factor = 1.0
            self.setZoomFactor(self.zoom_factor)
            config.set_config_value("zoom_factor", self.zoom_factor)
            self.zoom_changed.emit(self.zoom_factor)
        except Exception as e:
            print(f"Error resetting zoom: {e}")

    def zoom_in(self):
        """Zoom in by one step"""
        try:
            self.zoom_factor = min(self.zoom_factor + 0.1, 5.0)
            self.setZoomFactor(self.zoom_factor)
            config.set_config_value("zoom_factor", self.zoom_factor)
            self.zoom_changed.emit(self.zoom_factor)
        except Exception as e:
            print(f"Error zooming in: {e}")

    def zoom_out(self):
        """Zoom out by one step"""
        try:
            self.zoom_factor = max(self.zoom_factor - 0.1, 0.25)
            self.setZoomFactor(self.zoom_factor)
            config.set_config_value("zoom_factor", self.zoom_factor)
            self.zoom_changed.emit(self.zoom_factor)
        except Exception as e:  # FIXED: Added 'as e' here
            print(f"Error zooming out: {e}")

    def mousePressEvent(self, event):
        """Block navigation mouse buttons from leaving the game page."""
        try:
            if (self._is_navigation_mouse_button(event.button()) and
                    self._should_block_navigation_buttons()):
                event.accept()
                return
        except Exception as e:
            print(f"Error filtering mousePressEvent: {e}")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Block navigation mouse buttons from leaving the game page."""
        try:
            if (self._is_navigation_mouse_button(event.button()) and
                    self._should_block_navigation_buttons()):
                event.accept()
                return
        except Exception as e:
            print(f"Error filtering mouseReleaseEvent: {e}")
        super().mouseReleaseEvent(event)

    def event(self, event):
        """Swallow navigation side button clicks before default handling."""
        try:
            if event.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseButtonDblClick,
            ):
                # Avoid strict isinstance to be robust across bindings
                btn = None
                try:
                    # QMouseEvent has button(); other events may not
                    btn = event.button() if hasattr(event, 'button') else None
                except Exception:
                    btn = None
                if btn is not None and self._is_navigation_mouse_button(btn) and self._should_block_navigation_buttons():
                    event.accept()
                    return True
        except Exception as e:
            print(f"Error in generic event filter: {e}")
        return super().event(event)

    @staticmethod
    def _is_navigation_mouse_button(button):
        """Return True if the mouse button is a navigation side button."""
        navigation_buttons = [
            getattr(Qt.MouseButton, name, None)
            for name in ("BackButton", "ForwardButton", "XButton1", "XButton2")
        ]
        navigation_buttons = [btn for btn in navigation_buttons if btn is not None]
        return any(button == btn for btn in navigation_buttons)

    def _should_block_navigation_buttons(self):
        """Return True when the current URL matches the LostCity client."""
        try:
            current_url = self.page().url()
            if not current_url.isValid():
                return False
            if _is_lostcity_game_client_url(current_url):
                return True
            return False
        except Exception as e:
            print(f"Error evaluating current game URL: {e}")
            return False

    def _lc_timestamp(self):
        try:
            if ZoneInfo is not None:
                now = datetime.now(ZoneInfo("America/New_York"))
            else:
                now = datetime.now()
            month = now.strftime("%B")
            day = str(now.day)
            year = str(now.year)
            hour_12 = str(now.hour % 12 or 12)
            minute = f"{now.minute:02d}"
            second = f"{now.second:02d}"
            meridiem = now.strftime("%p")
            tz_abbr = now.tzname() or "EDT"
            return f"{month}-{day}-{year}-{hour_12}-{minute}-{second}-{meridiem}-{tz_abbr}"
        except Exception:
            return datetime.now().strftime("%B-%d-%Y-%I-%M-%S-%p-EDT")

    def on_download_requested(self, download):
        """Force any game-initiated downloads (e.g., screenshots) into LCScreenshots with LC_ timestamp name."""
        try:
            # Determine target directory next to this file (repo root)
            target_dir = Path(__file__).resolve().parent / "LCScreenshots"
            target_dir.mkdir(parents=True, exist_ok=True)

            # Best-effort read suggested name and extension across Qt versions
            suggested = None
            try:
                # Qt6: method downloadFileName() may be a function
                suggested = download.downloadFileName() if callable(getattr(download, 'downloadFileName', None)) else getattr(download, 'downloadFileName', None)
            except Exception:
                pass
            if not suggested:
                try:
                    suggested = download.path() if callable(getattr(download, 'path', None)) else getattr(download, 'path', None)
                except Exception:
                    suggested = None
            if not suggested:
                try:
                    suggested = download.url().fileName()  # fallback
                except Exception:
                    suggested = None

            # Normalize extension
            ext = ".png"
            try:
                if suggested:
                    base = os.path.basename(str(suggested))
                    suffix = os.path.splitext(base)[1]
                    if suffix:
                        ext = suffix
            except Exception:
                pass

            filename = f"LC_{self._lc_timestamp()}{ext}"

            # Apply target path according to available API
            applied = False
            try:
                if hasattr(download, 'setDownloadDirectory') and hasattr(download, 'setDownloadFileName'):
                    download.setDownloadDirectory(str(target_dir))
                    download.setDownloadFileName(filename)
                    download.accept()
                    applied = True
            except Exception as e:
                print(f"Download API (Qt6) failed: {e}")

            if not applied:
                try:
                    # PyQt5 style
                    full_path = target_dir / filename
                    if hasattr(download, 'setPath'):
                        download.setPath(str(full_path))
                        download.accept()
                        applied = True
                except Exception as e:
                    print(f"Download API (Qt5) failed: {e}")

            if applied:
                print(f"Redirected download to {target_dir} as {filename}")
                try:
                    self._show_screenshot_toast(str(target_dir / filename))
                except Exception:
                    pass
            else:
                print("Could not apply download redirection; download may go to default location.")
        except Exception as e:
            print(f"Error in on_download_requested: {e}")

    def handle_screenshot_request(self):
        """Capture the canvas directly and save to LCScreenshots."""
        try:
            self.capture_canvas_to_file()
        except Exception as e:
            print(f"Error handling screenshot request: {e}")

    def capture_canvas_to_file(self):
        """Capture the in-page canvas via toDataURL and write a PNG file."""
        try:
            script = """
                (function(){
                    function findCanvas(win) {
                        try {
                            var d = win.document;
                            var c = d && d.getElementById ? d.getElementById('canvas') : null;
                            if (c) return c;
                            if (!win.frames) return null;
                            for (var i=0;i<win.frames.length;i++) {
                                try {
                                    var r = findCanvas(win.frames[i]);
                                    if (r) return r;
                                } catch (e) {}
                            }
                            return null;
                        } catch (e) {
                            return null;
                        }
                    }
                    try {
                        var c = findCanvas(window);
                        if (!c) { return '__ERR__:no-canvas'; }
                        var data = c.toDataURL('image/png');
                        if (!data || typeof data !== 'string' || data.indexOf('data:') !== 0) {
                            return '__ERR__:no-dataurl';
                        }
                        return data;
                    } catch (e) {
                        return '__ERR__:'+ (e && e.toString ? e.toString() : 'unknown');
                    }
                })();
            """
            def _cb(result):
                try:
                    if not isinstance(result, str):
                        print('Screenshot JS result invalid; falling back to view.grab')
                        return self._fallback_grab_to_file()
                    if result.startswith('__ERR__:'):
                        print('Canvas screenshot error:', result)
                        return self._fallback_grab_to_file()
                    # Parse data URL
                    prefix = 'base64,'
                    idx = result.find(prefix)
                    if idx == -1:
                        print('No base64 in data URL; falling back to view.grab')
                        return self._fallback_grab_to_file()
                    b64 = result[idx+len(prefix):]
                    data = base64.b64decode(b64)
                    # Ensure dir
                    target_dir = Path(__file__).resolve().parent / 'LCScreenshots'
                    target_dir.mkdir(parents=True, exist_ok=True)
                    # Name
                    ts = self._lc_timestamp() if hasattr(self, '_lc_timestamp') else 'capture'
                    filename = f'LC_{ts}.png'
                    out_path = target_dir / filename
                    with open(out_path, 'wb') as f:
                        f.write(data)
                    print(f'Canvas screenshot saved to {out_path}')
                    try:
                        self._show_screenshot_toast(str(out_path))
                    except Exception:
                        pass
                except Exception as e:
                    print('Error writing canvas screenshot:', e)
                    self._fallback_grab_to_file()

            self.page().runJavaScript(script, _cb)
        except Exception as e:
            print(f'Error starting canvas capture: {e}')
            self._fallback_grab_to_file()

    def _fallback_grab_to_file(self):
        try:
            pm = self.grab()
            if pm.isNull():
                print('Fallback grab failed: pixmap is null')
                return
            target_dir = Path(__file__).resolve().parent / 'LCScreenshots'
            target_dir.mkdir(parents=True, exist_ok=True)
            ts = self._lc_timestamp() if hasattr(self, '_lc_timestamp') else 'capture'
            out_path = target_dir / f'LC_{ts}.png'
            if pm.save(str(out_path), 'PNG'):
                print(f'Fallback view.grab screenshot saved to {out_path}')
                try:
                    self._show_screenshot_toast(str(out_path))
                except Exception:
                    pass
            else:
                print('Fallback view.grab save failed')
        except Exception as e:
            print('Error in fallback grab:', e)

    def _show_screenshot_toast(self, path_str):
        try:
            if not getattr(self, 'screenshot_toast_enabled', True):
                return
            msg = f"Screenshot saved\n{path_str}"
            pos = QCursor.pos()
            ms = getattr(self, 'screenshot_toast_ms', 2000)
            QToolTip.showText(pos, msg, self, self.rect(), ms)
        except Exception:
            pass

    def inject_screenshot_hook(self):
        """Inject JavaScript that routes the in-game Take screenshot link to LostKit."""
        if not self._should_block_navigation_buttons():
            return
        print("Injecting screenshot hook into game page…")
        script = """
            (function() {
                const CUSTOM_URL = 'lostkit://take-screenshot';

                function triggerLostKit() {
                    try { window.location.href = CUSTOM_URL; } catch (err) {}
                }

                function attachTo(el) {
                    if (!el || el.__lostkitScreenshotAttached) { return false; }
                    function handler(ev) {
                        try { ev.preventDefault(); } catch (e) {}
                        try { ev.stopPropagation(); } catch (e) {}
                        try { ev.stopImmediatePropagation(); } catch (e) {}
                        triggerLostKit();
                        return false;
                    }
                    el.addEventListener('click', handler, true);
                    try { el.onclick = handler; } catch (e) {}
                    try { el.setAttribute('href', CUSTOM_URL); } catch (e) {}
                    el.__lostkitScreenshotAttached = true;
                    return true;
                }

                function attachById() {
                    return attachTo(document.getElementById('screenshot'));
                }

                function attachByText() {
                    const nodes = Array.from(document.querySelectorAll('a,button,span,div'));
                    for (const el of nodes) {
                        try {
                            if (!el || !el.textContent) continue;
                            if (el.textContent.trim().toLowerCase() === 'take screenshot') {
                                if (attachTo(el)) return true;
                            }
                        } catch (e) {}
                    }
                    return false;
                }

                function attachByOnClick() {
                    const nodes = Array.from(document.querySelectorAll('[onclick]'));
                    for (const el of nodes) {
                        try {
                            const val = String(el.getAttribute('onclick')||'').toLowerCase();
                            if (val.indexOf('savescreenshot') !== -1) {
                                if (attachTo(el)) return true;
                            }
                        } catch (e) {}
                    }
                    return false;
                }

                function overrideSaveScreenshot() {
                    try {
                        const original = window.saveScreenshot;
                        window.saveScreenshot = function() { triggerLostKit(); return undefined; };
                        window.saveScreenshot.__lostkitWrapped = true;
                    } catch (e) {}
                }

                function overrideCandidates() {
                    ['takeScreenshot','take_screenshot','TakeScreenshot'].forEach(function(name){
                        try { window[name] = function(){ triggerLostKit(); return undefined; }; } catch (e) {}
                    });
                }

                function install() {
                    overrideSaveScreenshot();
                    overrideCandidates();
                    if (attachById()) return;
                    if (attachByText()) return;
                    attachByOnClick();
                }

                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', install);
                } else {
                    install();
                }

                try {
                    var ELEMENT_NODE = (window.Node && Node.ELEMENT_NODE) || 1;
                    const obs = new MutationObserver(function(muts){
                        let attached = false;
                        for (const m of muts) {
                            for (const n of m.addedNodes) {
                                if ((n.nodeType||ELEMENT_NODE) === ELEMENT_NODE) {
                                    if (attachById() || attachByText() || attachByOnClick()) { attached = true; break; }
                                }
                            }
                            if (attached) break;
                        }
                        overrideSaveScreenshot();
                        overrideCandidates();
                    });
                    obs.observe(document.documentElement||document.body, {childList:true,subtree:true});
                } catch (e) {}
            })();
        """
        try:
            self.page().runJavaScript(script)
        except Exception as e:
            print(f"Error injecting screenshot hook: {e}")

    def install_screenshot_script(self):
        """Register a QWebEngineScript so hooks run on subframes too."""
        try:
            print("Installing persistent screenshot hook script (subframes enabled)…")
            script = QWebEngineScript()
            script.setName("LostKitScreenshotHook")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(True)
            script.setSourceCode(
                """
                (function() {
                    const CUSTOM_URL = 'lostkit://take-screenshot';
                    function triggerLostKit() {
                        try { window.location.href = CUSTOM_URL; } catch (err) {}
                    }
                    function attachTo(el) {
                        if (!el || el.__lostkitScreenshotAttached) { return; }
                        function handler(ev) {
                            try { ev.preventDefault(); } catch (e) {}
                            try { ev.stopPropagation(); } catch (e) {}
                            try { ev.stopImmediatePropagation(); } catch (e) {}
                            triggerLostKit();
                            return false;
                        }
                        el.addEventListener('click', handler, true);
                        try { el.onclick = handler; } catch (e) {}
                        try { el.setAttribute('href', CUSTOM_URL); } catch (e) {}
                        el.__lostkitScreenshotAttached = true;
                    }
                    function install() {
                        try { if (document.getElementById('screenshot')) attachTo(document.getElementById('screenshot')); } catch (e) {}
                        try {
                            const nodes = Array.from(document.querySelectorAll('[onclick]'));
                            for (const el of nodes) {
                                try { const v = String(el.getAttribute('onclick')||'').toLowerCase(); if (v.indexOf('savescreenshot') !== -1) { attachTo(el); break; } } catch (e) {}
                            }
                        } catch (e) {}
                    }
                    if (document.readyState === 'loading') {
                        document.addEventListener('DOMContentLoaded', install);
                    } else {
                        install();
                    }
                    try {
                        var ELEMENT_NODE = (window.Node && Node.ELEMENT_NODE) || 1;
                        const obs = new MutationObserver(function(muts){
                            for (const m of muts) {
                                for (const n of m.addedNodes) {
                                    if ((n.nodeType||ELEMENT_NODE) === ELEMENT_NODE) {
                                        if ((n.id && n.id==='controls') || (n.querySelector && n.querySelector('#screenshot'))) {
                                            install();
                                            return;
                                        }
                                    }
                                }
                            }
                        });
                        obs.observe(document.documentElement||document.body,{childList:true,subtree:true});
                    } catch (e) {}
                })();
                """
            )
            # Insert script (avoid iteration; PyQt6 scripts collection may not be iterable)
            scripts = self.page().scripts()
            try:
                if hasattr(scripts, 'findScript'):
                    existing = scripts.findScript("LostKitScreenshotHook")
                    try:
                        # Remove existing to ensure a single copy
                        if existing and getattr(existing, 'name', None) and existing.name() == "LostKitScreenshotHook":
                            scripts.remove(existing)
                    except Exception:
                        pass
            except Exception:
                pass
            scripts.insert(script)
        except Exception as e:
            print(f"Error installing screenshot script: {e}")

    def get_zoom_percentage(self):
        """Get current zoom as percentage string"""
        try:
            return f"{int(self.zoom_factor * 100)}%"
        except Exception:
            return "100%"

    def cleanup_cache_files(self):
        """Light cleanup - preserve persistent login data"""
        print("Game view cleanup: Preserving login data and cookies")
        # Don't delete persistent storage directories
        # They contain login sessions and should survive restarts

    def closeEvent(self, event):
        """Clean up when widget is closed - preserve login data"""
        if hasattr(self, 'cleanup_timer'):
            self.cleanup_timer.stop()
            
        # Don't clear persistent storage - just clean up memory
        gc.collect()
        print("Game view closed - login data preserved")
        
        super().closeEvent(event)

    def _handle_click_log(self, json_text: str):
        """Append click-log JSON line to logs/clicks.jsonl and echo to console."""
        try:
            if not getattr(self, 'click_log_to_file', True):
                print(f"CLICK {json_text}")
                return
            logs_dir = Path(__file__).resolve().parent / 'logs'
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = logs_dir / 'clicks.jsonl'
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json_text.strip() + '\n')
            print(f"CLICK {json_text}")
        except Exception as e:
            print(f"Error writing click log: {e}")

    def install_click_logger_script(self):
        """Register a script that logs every click with useful element details."""
        try:
            script = QWebEngineScript()
            script.setName("LostKitClickLogger")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(True)
            script.setSourceCode(
                """
                (function(){
                  if (window.__lostkitClickLoggerInstalled) return; 
                  window.__lostkitClickLoggerInstalled = true;

                  function isScreenshotElement(el){
                    try {
                      if (!el) return false;
                      if (el.getAttribute && el.getAttribute('data-lostkit-screenshot') === '1') return true;
                      const id = (el.id||'').toLowerCase();
                      if (id === 'screenshot') return true;
                      const txt = String((el.textContent||'')).trim().toLowerCase();
                      if (txt === 'take screenshot' || txt.indexOf('screenshot') !== -1) return true;
                      const oc = String((el.getAttribute && el.getAttribute('onclick'))||'').toLowerCase();
                      if (oc.indexOf('savescreenshot') !== -1) return true;
                    } catch (e) {}
                    return false;
                  }

                  function nodeLabel(n){
                    try {
                      if (!n || !n.tagName) return 'UNKNOWN';
                      let s = n.tagName.toLowerCase();
                      if (n.id) s += '#' + n.id;
                      if (n.className && typeof n.className === 'string') s += '.' + n.className.trim().split(/\s+/).slice(0,4).join('.');
                      return s;
                    } catch (e) { return 'UNKNOWN'; }
                  }

                  function buildPath(ev){
                    try {
                      const p = (ev.composedPath && ev.composedPath()) || [];
                      if (p && p.length) return p.map(nodeLabel).slice(0,12);
                    } catch (e) {}
                    // Fallback: simple parent chain
                    try {
                      const arr = []; let cur = ev.target; let i=0;
                      while (cur && i++ < 12) { arr.push(nodeLabel(cur)); cur = cur.parentNode; }
                      return arr;
                    } catch (e) { return []; }
                  }

                  function trim(s, n){ try { s = String(s||''); return s.length>n ? s.slice(0,n) : s; } catch(e){ return ''; } }

                  document.addEventListener('click', function(ev){
                    try {
                      const t = ev.target;
                      const href = (t && t.getAttribute && t.getAttribute('href')) || '';
                      const onclick = (t && t.getAttribute && t.getAttribute('onclick')) || '';
                      const payload = {
                        ts: new Date().toISOString(),
                        type: 'click',
                        pageUrl: String(location.href||''),
                        clientX: ev.clientX||0,
                        clientY: ev.clientY||0,
                        target: {
                          tag: (t && t.tagName ? t.tagName.toLowerCase() : 'unknown'),
                          id: (t && t.id) || '',
                          class: (t && typeof t.className==='string' ? t.className : ''),
                          text: trim((t && t.textContent) || '', 120),
                          href: href || '',
                          onclick: trim(onclick, 160)
                        },
                        path: buildPath(ev),
                        isScreenshotIntent: isScreenshotElement(t)
                      };
                      console.log('@@CLICK@@ ' + JSON.stringify(payload));
                    } catch (e) {
                      try { console.log('@@CLICK@@ ' + JSON.stringify({ ts: new Date().toISOString(), err: String(e) })); } catch (ee) {}
                    }
                  }, true);
                })();
                """
            )
            scripts = self.page().scripts()
            try:
                if hasattr(scripts, 'findScript'):
                    existing = scripts.findScript("LostKitClickLogger")
                    try:
                        if existing and getattr(existing, 'name', None) and existing.name() == "LostKitClickLogger":
                            scripts.remove(existing)
                    except Exception:
                        pass
            except Exception:
                pass
            scripts.insert(script)
        except Exception as e:
            print(f"Error installing click logger script: {e}")
