# config.py - Fixed for persistent storage and proper config saving
import json
import os
import threading
import time
from pathlib import Path
from PyQt6.QtCore import QStandardPaths

# Thread-safe config access
_config_lock = threading.RLock()
_config_cache = None
_cache_time = 0
CACHE_DURATION = 2  # Reduced cache duration for more responsive config saving


def get_app_data_dir():
    """Get persistent application data directory using the user's AppData location."""
    try:
        app_data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if app_data_dir:
            app_path = Path(app_data_dir)
            app_path.mkdir(parents=True, exist_ok=True)
            return str(app_path)
    except Exception as e:
        print(f"Warning: Could not create system app data directory: {e}")

    # Fallback to a hidden directory under the user's home if system path is unavailable
    fallback_dir = Path.home() / ".lostkit_app_data"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    return str(fallback_dir)

def get_config_path():
    """Get persistent config file path"""
    return os.path.join(get_app_data_dir(), "config.json")

def get_persistent_cache_dir():
    """Get persistent cache directory that survives restarts"""
    cache_dir = Path(get_app_data_dir()) / "cache"
    cache_dir.mkdir(exist_ok=True)
    return str(cache_dir)

def get_persistent_storage_dir():
    """Get persistent storage directory for web engine data"""
    storage_dir = Path(get_app_data_dir()) / "storage"
    storage_dir.mkdir(exist_ok=True)
    return str(storage_dir)

CONFIG_FILE = get_config_path()

DEFAULT_CONFIG = {
    "window_geometry": [100, 100, 1440, 900],  # Default geometry
    "right_panel_width": 250,
    "right_panel_collapsed": False,
    "zoom_factor": 1.0,
    "open_external": True,
    "tool_window_geometry": [200, 200, 1000, 800],
    "theme": "dark_pastel",
    "chat_panel_visible": True,
    "chat_panel_height": 200,
    "chat_zoom_factor": 0.8,
    "current_world_info": "No world",
    "resource_optimization": True,
    "cache_cleanup_interval": 300,
    "max_tool_windows": 10,
    # Individual tool window geometries
}

def load_config():
    """Load configuration with improved error handling"""
    global _config_cache, _cache_time
    
    with _config_lock:
        current_time = time.time()
        
        # Return cached config if still valid
        if _config_cache and (current_time - _cache_time) < CACHE_DURATION:
            return _config_cache.copy()
        
        config = DEFAULT_CONFIG.copy()
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    
                # Merge loaded config with defaults
                for key, value in loaded_config.items():
                    config[key] = value
                
                # Validate and fix geometry values
                if config.get("window_geometry"):
                    try:
                        geom = [int(x) for x in config["window_geometry"]]
                        if len(geom) == 4:
                            config["window_geometry"] = geom
                        else:
                            config["window_geometry"] = DEFAULT_CONFIG["window_geometry"]
                    except (ValueError, TypeError):
                        config["window_geometry"] = DEFAULT_CONFIG["window_geometry"]
                
                # Validate tool window geometries
                for key, value in list(config.items()):
                    if key.startswith("tool_window_geometry_") and isinstance(value, list):
                        try:
                            config[key] = [int(x) for x in value]
                        except (ValueError, TypeError):
                            del config[key]
                
                # Validate numeric values with proper bounds
                config["zoom_factor"] = max(0.25, min(float(config.get("zoom_factor", 1.0)), 5.0))
                config["chat_zoom_factor"] = max(0.25, min(float(config.get("chat_zoom_factor", 0.8)), 3.0))
                config["right_panel_width"] = max(200, min(int(config.get("right_panel_width", 250)), 800))
                config["chat_panel_height"] = max(100, min(int(config.get("chat_panel_height", 200)), 600))
                config["max_tool_windows"] = max(1, min(int(config.get("max_tool_windows", 10)), 50))
                
                # Validate boolean values
                config["open_external"] = bool(config.get("open_external", True))
                config["chat_panel_visible"] = bool(config.get("chat_panel_visible", True))
                config["resource_optimization"] = bool(config.get("resource_optimization", True))
                config["right_panel_collapsed"] = bool(config.get("right_panel_collapsed", False))
                
            except Exception as e:
                print(f"Error loading config: {e}. Using defaults.")
                config = DEFAULT_CONFIG.copy()
        
        # Cache the config
        _config_cache = config.copy()
        _cache_time = current_time
        return config

def save_config(config):
    """Save configuration with atomic writes and immediate disk flush"""
    global _config_cache, _cache_time
    
    with _config_lock:
        try:
            # Ensure config directory exists
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            
            # Validate config before saving
            validated_config = DEFAULT_CONFIG.copy()
            for key, value in config.items():
                validated_config[key] = value
            
            # Atomic write using temporary file
            temp_file = CONFIG_FILE + ".tmp"
            
            with open(temp_file, "w", encoding='utf-8') as f:
                json.dump(validated_config, f, indent=4, ensure_ascii=False)
                f.flush()  # Force write to disk
                os.fsync(f.fileno())  # Force OS to write to disk
            
            # Atomic move (on most systems)
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            os.rename(temp_file, CONFIG_FILE)
            
            # Update cache
            _config_cache = validated_config.copy()
            _cache_time = time.time()
            
            print(f"Config saved to: {CONFIG_FILE}")
                
        except Exception as e:
            print(f"Error saving config: {e}")
            # Clean up temp file on error
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

def get_config_value(key, default=None):
    """Get a single config value"""
    config = load_config()
    return config.get(key, default)

def set_config_value(key, value):
    """Set a single config value and save immediately"""
    config = load_config()
    config[key] = value
    save_config(config)

def force_save_config():
    """Force save current cached config to disk"""
    global _config_cache
    if _config_cache:
        save_config(_config_cache)

def get_persistent_profile_path(profile_name):
    """Get persistent profile path that survives application restarts"""
    profile_dir = Path(get_persistent_storage_dir()) / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    return str(profile_dir)

def get_persistent_cache_path(cache_name):
    """Get persistent cache path that survives application restarts"""
    cache_path = Path(get_persistent_cache_dir()) / cache_name
    cache_path.mkdir(parents=True, exist_ok=True)
    return str(cache_path)
