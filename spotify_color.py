"""
Spotify Color Extraction Module
===============================

This module extracts dominant colors from Spotify album artwork and maps them to
curses terminal colors for use in the ResoniteSpotipy TUI.

It uses HSV color space analysis to identify the most vibrant/saturated colors
in album artwork, then maps them to the closest curses terminal color.

Key features:
- Extracts multiple dominant colors using K-means clustering
- Scores colors based on saturation, brightness, and prevalence
- Maps RGB colors to terminal colors using HSV perceptual distance
- Caches results for performance
- Updates UI borders dynamically when songs change

Functions:
- get_dominant_colors: Extract multiple colors from an image
- get_saturated_color: Find the most vibrant color from a set
- rgb_to_curses_color: Map RGB colors to terminal colors
- process_current_track: Extract colors from current Spotify track

Usage:
    import spotify_color
    
    # Process current playing track (main entry point)
    spotify_color.process_current_track(stdscr, ui_instance, track_data)
    
    # Direct color extraction
    image_data = spotify_color.fetch_album_art(album_url)
    dominant_colors = spotify_color.get_dominant_colors(image_data)
    vibrant_color = spotify_color.get_saturated_color(dominant_colors)
    curses_color = spotify_color.rgb_to_curses_color(vibrant_color)
"""

import os
import sys
import time
import curses
import requests
import threading
import numpy as np
from PIL import Image
from io import BytesIO
from collections import Counter
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import joblib
import colorsys

MODEL_PATH = 'kmeans_model.joblib'
COLOR_CACHE = {}  # Cache colors by album URL to avoid reprocessing
CURRENT_COLOR = None
COLOR_LOCK = threading.Lock()
DEBUG = False  # Debug flag

# RGB to curses color mapping with improved values
CURSES_COLORS = {
    'black': (0, 0, 0),         # Black
    'red': (220, 30, 30),       # More accurate red
    'green': (30, 200, 30),     # More accurate green  
    'yellow': (230, 220, 30),   # More accurate yellow
    'blue': (30, 30, 220),      # More accurate blue
    'magenta': (210, 30, 210),  # More accurate magenta
    'cyan': (30, 210, 210),     # More accurate cyan
    'white': (220, 220, 220)    # Off-white
}

def debug_log(message):
    """Print debug messages to a file (to avoid corrupting curses display)"""
    if DEBUG:
        with open("color_debug.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {message}\n")

def train_kmeans(pixels, max_k=10):
    """Train a KMeans model to find optimal clusters for color extraction.
    
    Args:
        pixels: Numpy array of pixel values
        max_k: Maximum number of clusters to try
        
    Returns:
        Trained KMeans model with optimal number of clusters
    """
    best_k = 1
    best_score = -1
    best_model = None

    for k in range(2, max_k + 1):
        kmeans = KMeans(n_clusters=k, n_init='auto')
        labels = kmeans.fit_predict(pixels)
        
        # Skip single item clusters
        if len(np.unique(labels)) < 2:
            continue
            
        score = silhouette_score(pixels, labels)

        if score > best_score:
            best_k = k
            best_score = score
            best_model = kmeans

    # Fallback if no good model was found
    if best_model is None:
        best_model = KMeans(n_clusters=3, n_init='auto').fit(pixels)
        
    return best_model

def update_kmeans_model(pixels):
    """Update an existing KMeans model with new pixel data.
    
    Args:
        pixels: Numpy array of pixel values
        
    Returns:
        Updated KMeans model
    """
    try:
        if os.path.exists(MODEL_PATH):
            existing_model = joblib.load(MODEL_PATH)
            combined_data = np.vstack([existing_model.cluster_centers_, pixels])
        else:
            combined_data = pixels

        new_model = train_kmeans(combined_data)
        joblib.dump(new_model, MODEL_PATH)
        return new_model
    except Exception as e:
        print(f"Error updating KMeans model: {e}")
        # Fallback to direct KMeans without model persistence
        return KMeans(n_clusters=5, n_init='auto').fit(pixels)

# Convert RGB to HSV for better color comparison
def rgb_to_hsv(rgb):
    """Convert RGB color to HSV color space for better perceptual analysis.
    
    Args:
        rgb: Tuple of (r, g, b) values (0-255)
        
    Returns:
        Tuple of (h, s, v) values (h: 0-1, s: 0-1, v: 0-1)
    """
    r, g, b = rgb
    r, g, b = r/255.0, g/255.0, b/255.0  # Normalize to 0-1
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h, s, v)

def get_dominant_colors(image_data, n_colors=5):
    """Extract multiple dominant colors from image data using K-means clustering.
    
    Args:
        image_data: Raw image bytes
        n_colors: Number of colors to extract
        
    Returns:
        List of tuples: [(color, percentage), ...] where color is (r, g, b)
    """
    try:
        debug_log(f"Extracting dominant colors from image ({len(image_data)} bytes)")
        
        # Load image from bytes
        image = Image.open(BytesIO(image_data)).convert('RGB')
        
        # Resize for faster processing, but keep enough detail
        image = image.resize((150, 150))
        
        # Convert to numpy array
        image_array = np.array(image)
        pixels = image_array.reshape((-1, 3))
        
        # Use KMeans to find color clusters
        kmeans = KMeans(n_clusters=n_colors, n_init='auto').fit(pixels)
        colors = kmeans.cluster_centers_
        
        # Count pixel assignments to find dominant colors
        labels = kmeans.labels_
        counts = Counter(labels)
        
        # Get colors sorted by frequency (most common first)
        dominant_colors = []
        for i in counts.most_common(n_colors):
            color = tuple(map(int, colors[i[0]]))
            pct = i[1] / len(labels) * 100
            dominant_colors.append((color, pct))
            
        debug_log(f"Extracted {len(dominant_colors)} dominant colors")
        return dominant_colors
    except Exception as e:
        debug_log(f"Error extracting dominant colors: {e}")
        return [((255, 255, 255), 100)]  # Default white

def get_saturated_color(colors):
    """Find the most saturated (vibrant) color among the dominant colors.
    
    Uses a scoring system that emphasizes saturation while considering color 
    prevalence and brightness. Filters out very dark or near-white colors.
    
    Args:
        colors: List of tuples [(color, percentage), ...] from get_dominant_colors
        
    Returns:
        Tuple (r, g, b) of the most vibrant color
    """
    if not colors:
        return (255, 255, 255)  # Default to white
        
    max_score = 0
    most_saturated = colors[0][0]  # Default to most common color
    
    # Minimum saturation threshold to consider a color "pigmented"
    min_saturation = 0.15
    
    debug_log(f"Finding most pigmented color from {len(colors)} colors")
    
    for color, pct in colors:
        h, s, v = rgb_to_hsv(color)
        
        # Skip very dark colors (low value)
        if v < 0.15:
            debug_log(f"Skipping dark color {color} (v={v:.2f})")
            continue
            
        # Skip very light/white colors
        if s < 0.1 and v > 0.9:
            debug_log(f"Skipping near-white color {color} (s={s:.2f}, v={v:.2f})")
            continue
        
        # Heavy emphasis on saturation (pigmentation), but still consider color prevalence
        # Saturation is now squared to prioritize highly saturated colors
        saturation_weight = 4.0  # Increased from default of 1.0
        prevalence_weight = 0.3  # Reduced from default of 1.0
        value_bonus = 0.7  # Bonus for mid-range brightness (not too dark or light)
        
        # Value bonus peaks at around 0.7 (medium brightness)
        brightness_factor = 1.0 - abs(v - 0.7) * 0.5
        
        # Calculate score with higher weight on saturation (pigmentation)
        score = (s * s * saturation_weight) + (pct * prevalence_weight / 100) + (brightness_factor * value_bonus)
        
        debug_log(f"Color: {color}, HSV: ({h:.2f}, {s:.2f}, {v:.2f}), Score: {score:.2f}")
        
        # Only consider "pigmented" colors above the saturation threshold
        if s >= min_saturation and score > max_score:
            max_score = score
            most_saturated = color
            debug_log(f"New best color: {color} with score {score:.2f}")
            
    debug_log(f"Selected most pigmented color: {most_saturated}")
    return most_saturated

def color_distance_hsv(color1, color2):
    """Calculate perceptual color distance in HSV space.
    
    Args:
        color1: First RGB color tuple (r, g, b)
        color2: Second RGB color tuple (r, g, b)
        
    Returns:
        Distance value (lower means more similar)
    """
    # Convert to HSV
    hsv1 = rgb_to_hsv(color1)
    hsv2 = rgb_to_hsv(color2)
    
    # Hue is circular (0=360), so handle accordingly
    h1, s1, v1 = hsv1
    h2, s2, v2 = hsv2
    
    # Calculate hue distance on a circle (0-1)
    h_dist = min(abs(h1 - h2), 1 - abs(h1 - h2))
    
    # Weight the components (hue is most important for color identity)
    h_weight, s_weight, v_weight = 0.6, 0.3, 0.1
    distance = h_weight * h_dist + s_weight * abs(s1 - s2) + v_weight * abs(v1 - v2)
    
    return distance

def rgb_to_curses_color(rgb):
    """Map an RGB color to the closest curses color using HSV distance.
    
    Args:
        rgb: RGB color tuple (r, g, b)
        
    Returns:
        Curses color constant (e.g., curses.COLOR_RED)
    """
    min_distance = float('inf')
    closest_color = curses.COLOR_WHITE  # Default to white
    
    debug_log(f"Finding closest curses color for RGB: {rgb}")
    
    # Find closest basic color using HSV perceptual distance
    for color_name, color_rgb in CURSES_COLORS.items():
        distance = color_distance_hsv(rgb, color_rgb)
        debug_log(f"Distance to {color_name}: {distance:.3f}")
        
        if distance < min_distance:
            min_distance = distance
            
            # Map color name to curses constant
            if color_name == 'black':
                # Avoid black (invisible on black bg)
                closest_color = curses.COLOR_WHITE
            elif color_name == 'red':
                closest_color = curses.COLOR_RED
            elif color_name == 'green':
                closest_color = curses.COLOR_GREEN
            elif color_name == 'yellow':
                closest_color = curses.COLOR_YELLOW
            elif color_name == 'blue':
                closest_color = curses.COLOR_BLUE
            elif color_name == 'magenta':
                closest_color = curses.COLOR_MAGENTA
            elif color_name == 'cyan':
                closest_color = curses.COLOR_CYAN
            elif color_name == 'white':
                closest_color = curses.COLOR_WHITE
    
    debug_log(f"Selected curses color: {closest_color}")
    return closest_color

def get_brightness(rgb):
    """Calculate perceived brightness of a color (0-255).
    
    Uses the standard formula that weights channels according to human perception.
    
    Args:
        rgb: RGB color tuple (r, g, b)
        
    Returns:
        Brightness value (0-255)
    """
    # Using the formula: 0.299*R + 0.587*G + 0.114*B
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

def get_color_for_album(album_url):
    """Get dominant color for album artwork, with caching.
    
    Main function to extract color from album art URL. Caches results for
    performance.
    
    Args:
        album_url: URL to album artwork image
        
    Returns:
        Curses color constant (e.g., curses.COLOR_RED)
    """
    global COLOR_CACHE
    
    debug_log(f"Getting color for album: {album_url}")
    
    if not album_url:
        debug_log("No album URL provided, using default white")
        return curses.COLOR_WHITE  # Default color
        
    # Check the cache first
    if album_url in COLOR_CACHE:
        debug_log(f"Using cached color for album: {COLOR_CACHE[album_url]}")
        return COLOR_CACHE[album_url]
    
    # Fetch and process the image
    image_data = fetch_album_art(album_url)
    if not image_data:
        debug_log("No image data returned, using default white")
        return curses.COLOR_WHITE
    
    # Extract dominant colors
    dominant_colors = get_dominant_colors(image_data, n_colors=8)
    
    # Find the most vibrant color
    vibrant_color = get_saturated_color(dominant_colors)
    
    # Map to nearest curses color with enhanced algorithm
    curses_color = rgb_to_curses_color(vibrant_color)
    
    # Cache the result
    COLOR_CACHE[album_url] = curses_color
    
    return curses_color

def fetch_album_art(album_url):
    """Fetch the album art from Spotify.
    
    Args:
        album_url: URL to the album art
        
    Returns:
        Raw image data bytes
    """
    try:
        response = requests.get(album_url, timeout=5)
        if response.status_code == 200:
            return response.content
        else:
            debug_log(f"Error fetching album art: HTTP {response.status_code}")
            return None
    except Exception as e:
        debug_log(f"Exception fetching album art: {e}")
        return None

def get_dominant_color(album_url):
    """Get the dominant color in hex format from an album art URL.
    
    Args:
        album_url: URL to the album art
        
    Returns:
        Hex color code (e.g. "#FF5733") or None if error
    """
    try:
        # Check if we have this color cached
        if album_url in COLOR_CACHE:
            rgb_color = COLOR_CACHE[album_url]
        else:
            # Fetch and process the album art
            image_data = fetch_album_art(album_url)
            if not image_data:
                return None
                
            # Get dominant colors
            dominant_colors = get_dominant_colors(image_data)
            
            # Get the most vibrant color
            rgb_color = get_saturated_color(dominant_colors)
            
            # Cache the result
            COLOR_CACHE[album_url] = rgb_color
        
        # Convert RGB to hex
        hex_color = "#{:02x}{:02x}{:02x}".format(rgb_color[0], rgb_color[1], rgb_color[2])
        return hex_color
        
    except Exception as e:
        debug_log(f"Error getting dominant color: {e}")
        return None

def update_border_color(stdscr, ui_instance, album_url):
    """Update the border color based on album artwork.
    
    Uses threading to avoid blocking the main UI during processing.
    
    Args:
        stdscr: Curses screen object
        ui_instance: ResoniteUI instance
        album_url: URL to album artwork image
    """
    global CURRENT_COLOR, COLOR_LOCK
    
    debug_log(f"Updating border color for album: {album_url}")
    
    # Skip if no album URL or UI
    if not album_url or not ui_instance:
        debug_log("Missing album URL or UI instance, skipping color update")
        return
    
    # Process in a separate thread to avoid blocking
    def process_color():
        global CURRENT_COLOR, COLOR_LOCK
        
        debug_log("Starting color processing thread")
        
        # Get color for this album
        curses_color = get_color_for_album(album_url)
        
        with COLOR_LOCK:
            debug_log(f"Current color: {CURRENT_COLOR}, New color: {curses_color}")
            
            # Always update the color pair (don't check if it's the same)
            CURRENT_COLOR = curses_color
            
            # Define a custom color pair for the border
            try:
                # Get the actual COLOR_BORDER value from the UI module
                from resonite_ui import COLOR_BORDER
                debug_log(f"Updating color pair {COLOR_BORDER} to color: {curses_color}")
                
                # Force update the color pair
                curses.init_pair(COLOR_BORDER, curses_color, -1)
                
                # Force refresh of UI components
                debug_log("Triggering UI refresh")
                ui_instance.redraw_ui()  # Use the new redraw_ui method
                debug_log("UI refresh completed")
            except Exception as e:
                debug_log(f"Error updating color: {e}")
                # Fallback to hardcoded color pair number
                try:
                    debug_log("Trying fallback with hardcoded color pair 17")
                    curses.init_pair(17, curses_color, -1)
                    ui_instance.redraw_ui()
                except Exception as e2:
                    debug_log(f"Fallback also failed: {e2}")
    
    # Start color processing in background
    thread = threading.Thread(target=process_color)
    thread.daemon = True
    thread.start()
    debug_log("Color processing thread started")

# Function to be called from the main app when track changes
def process_current_track(stdscr, ui_instance, track_data):
    """Process the current track to update UI colors.
    
    Main entry point for color extraction from Spotify track data.
    
    Args:
        stdscr: Curses screen object
        ui_instance: ResoniteUI instance
        track_data: Spotify track data dictionary
    """
    debug_log("Processing current track for color extraction")
    
    if not track_data:
        debug_log("No track data provided")
        return
    
    if not ui_instance:
        debug_log("No UI instance provided")
        return
        
    # Extract album art URL from track data
    album_url = None
    try:
        debug_log("Extracting album art URL from track data")
        if "item" in track_data and track_data["item"]:
            debug_log(f"Track item found: {track_data['item'].get('name', 'Unknown')}")
            if "album" in track_data["item"] and track_data["item"]["album"]:
                debug_log(f"Album found: {track_data['item']['album'].get('name', 'Unknown')}")
                if "images" in track_data["item"]["album"] and track_data["item"]["album"]["images"]:
                    # Get the medium size image (index 1) or the first available
                    if len(track_data["item"]["album"]["images"]) > 1:
                        album_url = track_data["item"]["album"]["images"][1]["url"]
                    else:
                        album_url = track_data["item"]["album"]["images"][0]["url"]
                    debug_log(f"Album art URL extracted: {album_url}")
                else:
                    debug_log("No images found in album data")
            else:
                debug_log("No album found in track data")
        else:
            debug_log("No item found in track data")
    except Exception as e:
        debug_log(f"Error extracting album art URL: {e}")
        return
    
    if album_url:
        debug_log(f"Calling update_border_color with URL: {album_url}")
        update_border_color(stdscr, ui_instance, album_url)
    else:
        debug_log("No album URL found, skipping color update")

def enable_debug():
    """Enable debug logging"""
    global DEBUG
    DEBUG = True
    # Clear previous log
    with open("color_debug.log", "w") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] Debug logging started\n")

def force_update_from_url(stdscr, ui_instance, album_url, force_color=None):
    """Manually force color update from a URL - for debugging.
    
    Args:
        stdscr: Curses screen object
        ui_instance: ResoniteUI instance
        album_url: URL to album artwork image
        force_color: Optional color to force instead of extracting
    """
    global CURRENT_COLOR, COLOR_LOCK, DEBUG
    
    # Enable debugging
    DEBUG = True
    with open("color_debug.log", "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Forcing color update from URL: {album_url}\n")
    
    if force_color is not None:
        # Use the specified color directly
        with COLOR_LOCK:
            CURRENT_COLOR = force_color
            try:
                from resonite_ui import COLOR_BORDER
                curses.init_pair(COLOR_BORDER, force_color, -1)
                ui_instance.redraw_ui()
                with open("color_debug.log", "a") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Forced color {force_color} applied\n")
            except Exception as e:
                with open("color_debug.log", "a") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Error applying color: {e}\n")
        return
    
    # Otherwise extract from URL
    try:
        image_data = fetch_album_art(album_url)
        if not image_data:
            with open("color_debug.log", "a") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Failed to fetch image\n")
            return
            
        # Extract dominant colors
        dominant_colors = get_dominant_colors(image_data)
        vibrant_color = get_saturated_color(dominant_colors)
        curses_color = rgb_to_curses_color(vibrant_color)
        
        with COLOR_LOCK:
            CURRENT_COLOR = curses_color
            try:
                from resonite_ui import COLOR_BORDER
                curses.init_pair(COLOR_BORDER, curses_color, -1)
                ui_instance.redraw_ui()
                with open("color_debug.log", "a") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Color {curses_color} applied from RGB {vibrant_color}\n")
            except Exception as e:
                with open("color_debug.log", "a") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Error applying color: {e}\n")
    except Exception as e:
        with open("color_debug.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] MANUAL COLOR TEST: Error: {e}\n")

if __name__ == "__main__":
    # Stand-alone test functionality
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # Extract dominant colors
            dominant_colors = get_dominant_colors(image_data)
            vibrant_color = get_saturated_color(dominant_colors)
            print(f"Dominant Color (RGB): {vibrant_color}")
            
            brightness = get_brightness(vibrant_color)
            print(f"Brightness: {brightness}")
            
            # Approximate curses color
            curses_color_name = "unknown"
            curses_color = rgb_to_curses_color(vibrant_color)
            for name, rgb in CURSES_COLORS.items():
                if curses_color == getattr(curses, f"COLOR_{name.upper()}"):
                    curses_color_name = name
                    break
                    
            print(f"Closest curses color: {curses_color_name}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: python spotify_color.py <image_path>") 