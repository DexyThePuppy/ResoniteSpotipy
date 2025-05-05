import curses
import time
import threading

# Icons (using ASCII fallbacks instead of Nerd Fonts)
play_icon = "▶"
pause_icon = "⏸ "
shuffle_icon = "🔀"
repeat_track_icon = "🔂"
repeat_icon = "🔁"

# Color pair constants
COLOR_DEFAULT = 1        # White text on default background
COLOR_SUCCESS = 2        # Green text on default background
COLOR_ERROR = 3          # Red text on default background
COLOR_BORDER_INACTIVE = 4  # Border inactive
COLOR_BORDER_ACTIVE = 5  # Border active
COLOR_SELECTED = 6       # Selected item
COLOR_INFO = 8           # Cyan text (info)
COLOR_ALT = 9            # Blue text (alternative)
COLOR_POPUP = 10         # Popup background
COLOR_HIGHLIGHT = 11     # Magenta text (timestamps)
COLOR_WARNING = 12       # Yellow text
COLOR_BORDER = 17        # White border, default background
COLOR_PLAYING = 18       # Green text for playing
COLOR_PAUSED = 19        # Yellow text for paused
COLOR_TIMESTAMP = 20     # Magenta text for timestamp

def ms_to_hms(ms):
    """Convert milliseconds to MM:SS format"""
    if ms is None or ms <= 0:
        return "00:00"
    seconds = int(ms / 1000)
    minutes = int(seconds / 60)
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def truncate(text, max_length):
    """Truncate text to max_length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

class Component:
    """Base component class for UI elements"""
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.component = None
        self.startx = 0
        self.starty = 0
        self.endx = 0
        self.endy = 0
        self.title = None
        self.popup = False
        self.interactive = False

    def activate(self):
        curses.curs_set(0)
        if hasattr(self.component, 'active'):
            self.component.active = True

    def deactivate(self):
        curses.curs_set(1)
        if hasattr(self.component, 'active'):
            self.component.active = False

    def create_border(self, color):
        """Create a border around the component with the specified color"""
        try:
            # Always use COLOR_BORDER for borders to match UI color scheme
            self.stdscr.attron(curses.color_pair(COLOR_BORDER))

            # Draw all borders at once with fewer operations
            # Corners
            self.stdscr.addstr(self.starty, self.startx, "╭")
            self.stdscr.addstr(self.starty, self.endx, "╮")
            self.stdscr.addstr(self.endy, self.startx, "╰")
            self.stdscr.addstr(self.endy, self.endx, "╯")

            # Horizontal borders
            h_border = "─" * (self.endx - self.startx - 1)
            self.stdscr.addstr(self.starty, self.startx + 1, h_border)
            self.stdscr.addstr(self.endy, self.startx + 1, h_border)

            # Vertical borders
            for i in range(self.starty + 1, self.endy):
                self.stdscr.addstr(i, self.startx, "│")
                self.stdscr.addstr(i, self.endx, "│")

            # Title
            if self.title:
                self.stdscr.addstr(self.starty, self.startx + 2, f" {self.title} ")

            self.stdscr.attroff(curses.color_pair(COLOR_BORDER))
        except Exception:
            # Graceful error handling for border rendering
            pass

    def render(self, status=None):
        """Render the component and its content"""
        try:
            if self.popup:
                self.clear_content_area(fill_borders=True)
                self.create_border(COLOR_POPUP)
            elif self.interactive:
                self.create_border(COLOR_BORDER_ACTIVE if self.component.active else COLOR_BORDER_INACTIVE)
            else:
                # All components use the same border style
                self.create_border(COLOR_BORDER)
                
            # Render the component if it exists
            if self.component:
                self.component.render(status)
        except Exception as e:
            # Add fallback rendering for component
            try:
                self.stdscr.attron(curses.A_BOLD)
                self.stdscr.addstr(self.starty + 1, self.startx + 1, f"Component Error: {str(e)[:30]}")
                self.stdscr.attroff(curses.A_BOLD)
            except:
                pass

    def receive_input(self, key):
        """Handle input for interactive components"""
        pass

    def clear_content_area(self, fill_borders=False):
        """Clear the content area of the component"""
        start_y = self.starty if fill_borders else self.starty + 1
        end_y = self.endy if fill_borders else self.endy
        start_x = self.startx if fill_borders else self.startx + 1
        width = self.endx - start_x + 1 if fill_borders else self.endx - self.startx - 1
        
        # Make sure we're not trying to write outside the screen
        max_y, max_x = self.stdscr.getmaxyx()
        if end_y >= max_y:
            end_y = max_y - 1
        
        for y in range(start_y, end_y):
            try:
                self.stdscr.addstr(y, start_x, " " * width)
            except:
                # Gracefully handle any rendering issues
                pass

class BaseComponentContent:
    """Base class for component content"""
    def __init__(self, stdscr, starty, startx, endy, endx):
        self.stdscr = stdscr
        self.starty = starty
        self.startx = startx
        self.endy = endy
        self.endx = endx
        self.active = False
        
    def clear_content_area(self):
        """Clear the component's content area"""
        for y in range(self.starty + 1, self.endy):
            self.stdscr.addstr(y, self.startx + 1, " " * (self.endx - self.startx - 1))
            
    def render(self, status=None):
        """Base render method to be overridden by child classes"""
        self.clear_content_area()

class NowPlayingComponent(BaseComponentContent):
    """The inner component that displays track information"""
    def __init__(self, stdscr, starty, startx, endy, endx):
        super().__init__(stdscr, starty, startx, endy, endx)
        self.playing = False
        self.track_name = "-"
        self.artist_name = "-"
        self.track_length = 0
        self.progress = 0
        self.progress_percent = 0
        # Progress bar characters
        self.filled_block = "▰"
        self.empty_block = "▱"
        # Animation state
        self.previous_track_name = None
        self.previous_artist_name = None
        self.animation_active = False
        self.animation_frame = 0
        self.animation_max_frames = 20
        self.animation_complete = False
        # Timer for blank display
        self.no_track_start_time = time.time()
        self.blank_display_seconds = 10

    def start_animation(self):
        """Start animation for track change"""
        self.animation_active = True
        self.animation_frame = 0
        self.animation_complete = False

    def animate_text(self, y, text, max_width):
        """Animate sliding text based on current animation frame with carousel effect"""
        if not self.animation_active or self.animation_complete:
            # Just render the text normally if animation is not active
            truncated_text = truncate(text, max_width)
            
            # Center the text more precisely
            text_length = len(truncated_text)
            padding = (max_width - text_length) // 2
            padding = max(0, padding)  # Ensure padding is non-negative
            
            # Add padding before text for centering
            self.stdscr.addstr(y, self.startx + 1 + padding, truncated_text)
            return
        
        # For carousel animation, we'll keep the entire text together including icons
        content_area_start = self.startx + 1
        content_area_end = content_area_start + max_width
        
        # Calculate center position
        center_pos = content_area_start + (max_width // 2)
        
        if self.previous_track_name and self.animation_frame < self.animation_max_frames:
            # Truncate both texts to fit
            old_text = truncate(self.previous_track_name, max_width)
            new_text = truncate(text, max_width)
            
            # Animation progress factor (0 to 1)
            progress = self.animation_frame / self.animation_max_frames
            
            # Clear the content area first
            for i in range(max_width):
                self.stdscr.addstr(y, content_area_start + i, " ")
            
            # CAROUSEL EFFECT:
            # 1. Old text moves from center to left (exiting)
            # 2. New text moves from right to center (entering)
            
            # Old text: calculate position to move from center to left
            old_text_width = len(old_text)
            # Ensure old text starts perfectly centered
            old_start_x = center_pos - (old_text_width // 2)  # Centered position
            old_end_x = content_area_start - old_text_width    # Fully left (offscreen)
            
            # Linear interpolation between start and end positions
            old_current_x = int(old_start_x + progress * (old_end_x - old_start_x))
            
            # New text: calculate position to move from right to center
            new_text_width = len(new_text)
            new_start_x = content_area_end  # Start from right edge
            # Ensure new text ends perfectly centered
            new_end_x = center_pos - (new_text_width // 2)  # End at center
            
            # Linear interpolation between start and end positions
            new_current_x = int(new_start_x + progress * (new_end_x - new_start_x))
            
            # Only draw old text if it's still visible
            if old_current_x + old_text_width > content_area_start:
                visible_portion = min(old_text_width, content_area_end - old_current_x)
                if visible_portion > 0 and old_current_x < content_area_end:
                    # Simple handling - just clip the text as needed
                    draw_x = old_current_x
                    text_start_idx = 0
                    
                    if old_current_x < content_area_start:
                        text_start_idx = content_area_start - old_current_x
                        draw_x = content_area_start
                    
                    # Draw visible portion of old text
                    visible_text = old_text[text_start_idx:text_start_idx + visible_portion]
                    if visible_text:
                        self.stdscr.addstr(y, draw_x, visible_text)
            
            # Only draw new text if it's starting to be visible
            if new_current_x < content_area_end:
                visible_portion = min(new_text_width, content_area_end - new_current_x)
                if visible_portion > 0 and new_current_x >= content_area_start:
                    # Draw visible portion of new text
                    visible_text = new_text[:visible_portion]
                    self.stdscr.addstr(y, new_current_x, visible_text)
            
            # Update animation frame
            self.animation_frame += 1
            if self.animation_frame >= self.animation_max_frames:
                self.animation_active = False
                self.animation_complete = True
        else:
            # Fall back to normal rendering if no previous track
            truncated_content = truncate(text, max_width)
            # Properly center text with precise calculation
            text_length = len(truncated_content)
            center_padding = (max_width - text_length) // 2
            center_padding = max(0, center_padding)
            
            # Render centered text
            self.stdscr.addstr(y, content_area_start + center_padding, truncated_content)
            self.animation_complete = True

    def render(self, status):
        """Render the currently playing track information"""
        try:
            # Clear the content area
            super().render()
            
            # Update track information if status is available
            if status:
                self.playing = status.get("is_playing", False)
                item = status.get("item", None)
                if item:
                    # Check if track has changed
                    new_track_name = item.get("name", "-")
                    artists = item.get("artists", [])
                    new_artist_name = artists[0].get("name", "-") if artists else "-"
                    
                    # Start animation if track changed
                    if new_track_name != self.track_name:
                        self.previous_track_name = self.track_name
                        self.previous_artist_name = self.artist_name
                        self.start_animation()
                    
                    self.track_name = new_track_name
                    self.artist_name = new_artist_name
                    self.track_length = item.get("duration_ms", 0)
                    self.progress = status.get("progress_ms", 0)
                    self.progress_percent = ((self.progress / self.track_length) * 100 
                                            if self.progress > 0 and self.track_length > 0 else 0)
                    # Reset no-track timer when we have a track
                    self.no_track_start_time = time.time()
                else:
                    # No track in status, check if we need to reset the timer
                    if self.track_name != "-":
                        self.no_track_start_time = time.time()
                        self.track_name = "-"
                        self.artist_name = "-"
            
            # Get playback state icons
            shuffle = status.get("shuffle_state", False) if status else False
            repeat = status.get("repeat_state", "off") if status else "off"
            
            # For animation purposes, always include the playback status in the display text
            # instead of handling it separately
            status_symbol = play_icon if self.playing else pause_icon
            shuffle_symbol = shuffle_icon if shuffle else ""
            repeat_symbol = ""
            
            if repeat == "track":
                repeat_symbol = repeat_track_icon
            elif repeat == "context":
                repeat_symbol = repeat_icon
                
            # Calculate available space for the track info
            # Format times for the progress bar
            current_time = ms_to_hms(self.progress)
            total_time = ms_to_hms(self.track_length)
            
            # Generate the complete track info first - always with the icon at the beginning
            if self.track_name == "-":
                # Check how long we've been in the no-track state
                time_in_no_track = time.time() - self.no_track_start_time
                if time_in_no_track < self.blank_display_seconds:
                    # Display blank for the first 10 seconds
                    full_track_info = ""
                else:
                    # After 10 seconds, show the waiting message
                    full_track_info = f"{status_symbol} Nothing is playing - Waiting for Spotify data..."
            else:
                full_track_info = f"{status_symbol}{shuffle_symbol}{repeat_symbol} {self.track_name} - {self.artist_name}"
            
            # Set the old track info with the appropriate icon too if we're in an animation
            if self.animation_active and self.previous_track_name and not self.animation_complete:
                if self.previous_track_name == "-":
                    # Check how long we've been in the no-track state for previous track
                    time_in_no_track = time.time() - self.no_track_start_time
                    if time_in_no_track < self.blank_display_seconds:
                        self.previous_track_name = ""
                    else:
                        self.previous_track_name = f"{status_symbol} Nothing is playing - Waiting for Spotify data..."
                else:
                    # Make sure the previous track name has the play icon too
                    if not any(icon in self.previous_track_name for icon in [play_icon, pause_icon]):
                        self.previous_track_name = f"{status_symbol}{shuffle_symbol}{repeat_symbol} {self.previous_track_name} - {self.previous_artist_name}"
            
            # Determine total available width in the content area
            content_width = self.endx - self.startx - 1
            
            # Calculate minimum space needed for the progress bar
            min_progress_width = len(current_time) + len(total_time) + 6  # +6 for at least 4 blocks and spaces
            
            # Calculate maximum possible track info length
            max_possible_track_width = content_width - min_progress_width - 2  # -2 for spacing
            
            # If track info is shorter than the max possible, use its actual length
            # Otherwise, truncate it to fit
            if len(full_track_info) <= max_possible_track_width:
                track_info = full_track_info
                # Calculate remaining space for progress bar (all the rest minus spacing)
                progress_bar_width = content_width - len(track_info) - 2
            else:
                # Need to truncate track info
                track_info = truncate(full_track_info, max_possible_track_width)
                progress_bar_width = min_progress_width
            
            # Ensure we have enough space for both components
            if content_width < (min_progress_width + 15):  # Not enough space for both
                # Prioritize track info with minimum length of 15
                track_info = truncate(full_track_info, 15)
                
                # If we still have space for a minimal progress indicator, show it
                if content_width > len(track_info) + min_progress_width:
                    progress_bar_width = content_width - len(track_info) - 2
                else:
                    # Fall back to simple timestamp at the right edge
                    progress_bar_width = len(current_time) + 2
            
            # Use the border color instead of playback state color for matching UI colors
            # COLOR_BORDER = 17 is the border color that changes with keybindings 1-7
            self.stdscr.attron(curses.color_pair(COLOR_BORDER))
            
            # Use the animate_text method instead of direct rendering
            self.animate_text(self.starty + 1, track_info, content_width)
            self.stdscr.attroff(curses.color_pair(COLOR_BORDER))
            
            # Progress bar/time
            if progress_bar_width > min_progress_width:
                # Calculate positions and sizes
                progress_y = self.starty + 2
                if content_width < 80:  # For smaller screens, show simplified progress
                    # Just show the times with minimal progress
                    time_info = f"{current_time} / {total_time}"
                    # Center the time info
                    time_padding = (content_width - len(time_info)) // 2
                    time_padding = max(0, time_padding)
                    self.stdscr.attron(curses.color_pair(COLOR_BORDER))
                    self.stdscr.addstr(progress_y, self.startx + 1 + time_padding, time_info)
                    self.stdscr.attroff(curses.color_pair(COLOR_BORDER))
                else:
                    # Calculate how many blocks to display for progress
                    blocks_width = progress_bar_width - len(current_time) - len(total_time) - 2
                    
                    # Reduce blocks width to make progress bar shorter (approximately half the previous length)
                    max_blocks = min(blocks_width, 50)  # Limit maximum blocks to 50
                    blocks_width = max_blocks
                    
                    filled_blocks = int((self.progress_percent / 100) * blocks_width)
                    empty_blocks = blocks_width - filled_blocks

                    # Calculate padding to center the progress bar
                    total_width = len(current_time) + 1 + blocks_width + 1 + len(total_time)
                    available_width = self.endx - self.startx - 1
                    left_padding = (available_width - total_width) // 2
                    
                    # Ensure we have at least some padding
                    left_padding = max(left_padding, 1)

                    # Render full progress with bar and centered positioning
                    progress_start = self.startx + 1 + left_padding
                    
                    # Current time - use border color to match UI
                    self.stdscr.attron(curses.color_pair(COLOR_BORDER))
                    self.stdscr.addstr(progress_y, progress_start, current_time)
                    self.stdscr.attroff(curses.color_pair(COLOR_BORDER))

                    # Progress bar - use border color to match UI
                    self.stdscr.attron(curses.color_pair(COLOR_BORDER))
                    progress_bar_start = progress_start + len(current_time) + 1
                    progress_bar = self.filled_block * filled_blocks + self.empty_block * empty_blocks
                    self.stdscr.addstr(progress_y, progress_bar_start, progress_bar)
                    self.stdscr.attroff(curses.color_pair(COLOR_BORDER))

                    # Total time - use border color to match UI
                    self.stdscr.attron(curses.color_pair(COLOR_BORDER))
                    self.stdscr.addstr(progress_y, progress_bar_start + blocks_width + 1, total_time)
                    self.stdscr.attroff(curses.color_pair(COLOR_BORDER))
            else:
                # Only show current time if very limited space
                self.stdscr.attron(curses.color_pair(COLOR_BORDER))
                # Center the time
                time_padding = (content_width - len(current_time)) // 2
                time_padding = max(0, time_padding)
                self.stdscr.addstr(self.starty + 2, self.startx + 1 + time_padding, current_time)
                self.stdscr.attroff(curses.color_pair(COLOR_BORDER))
        except Exception as e:
            try:
                # Display a friendly error message
                self.stdscr.attron(curses.color_pair(COLOR_ERROR))
                self.stdscr.addstr(self.starty + 1, self.startx + 1, "Display error")
                self.stdscr.attroff(curses.color_pair(COLOR_ERROR))
            except:
                pass

class StatusBar(Component):
    """Status bar at the top of the screen"""
    def __init__(self, stdscr):
        super().__init__(stdscr)
        self.client_connected = False
        self.client_id = ""
        self.title = "Status"
        self.restart()
        
    def restart(self):
        scry, scrx = self.stdscr.getmaxyx()
        self.startx = 0
        self.endx = scrx - 1
        self.starty = 0
        self.endy = 2
        self.component = StatusBarComponent(
            self.stdscr,
            self.starty,
            self.startx,
            self.endy,
            self.endx,
            self.client_connected,
            self.client_id
        )
    
    def set_client_status(self, connected, client_id=""):
        """Update client connection status"""
        self.client_connected = connected
        self.client_id = client_id
        if hasattr(self, 'component') and self.component:
            self.component.client_connected = connected
            self.component.client_id = client_id

class StatusBarComponent:
    """Inner component for the status bar"""
    def __init__(self, stdscr, starty, startx, endy, endx, client_connected=False, client_id=""):
        self.stdscr = stdscr
        self.starty = starty
        self.startx = startx
        self.endy = endy
        self.endx = endx
        self.client_connected = client_connected
        self.client_id = client_id
        
    def render(self, status=None):
        """Render the status bar content"""
        # Clear status bar area
        for i in range(self.startx + 1, self.endx):
            self.stdscr.addstr(self.starty + 1, i, " ")
        
        # Draw left side status: app name
        status_text = "Resonite Spotipy"
        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.attron(curses.color_pair(COLOR_BORDER))
        self.stdscr.addstr(self.starty + 1, self.startx + 1, status_text)
        self.stdscr.attroff(curses.color_pair(COLOR_BORDER))
        self.stdscr.attroff(curses.A_BOLD)
        
        # Draw center status: connection status
        center_x = (self.endx - self.startx) // 2
        
        # Create status text with appropriate indicator
        if self.client_connected:
            status_indicator = "● CONNECTED"
            center_text = f"Client {self.client_id}: {status_indicator}"
            # Use green for connected
            self.stdscr.attron(curses.color_pair(COLOR_SUCCESS))
            self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(self.starty + 1, center_x - len(center_text) // 2, center_text)
            self.stdscr.attroff(curses.A_BOLD)
            self.stdscr.attroff(curses.color_pair(COLOR_SUCCESS))
        else:
            status_indicator = "○ DISCONNECTED"
            center_text = f"Websocket: {status_indicator}"
            # Use red for disconnected
            self.stdscr.attron(curses.color_pair(COLOR_ERROR))
            self.stdscr.attron(curses.A_DIM)
            self.stdscr.addstr(self.starty + 1, center_x - len(center_text) // 2, center_text)
            self.stdscr.attroff(curses.A_DIM)
            self.stdscr.attroff(curses.color_pair(COLOR_ERROR))
        
        # Draw right side information (current time)
        time_str = time.strftime("%H:%M:%S")
        self.stdscr.attron(curses.color_pair(COLOR_BORDER))
        self.stdscr.addstr(self.starty + 1, self.endx - len(time_str) - 1, time_str)
        self.stdscr.attroff(curses.color_pair(COLOR_BORDER))

class LogWindow(Component):
    """Component for displaying log messages"""
    def __init__(self, stdscr):
        super().__init__(stdscr)
        self.title = "Log"
        self.logs = []
        self.max_logs = 100  # Maximum number of log entries to keep
        self.restart()
        self.new_log_indexes = set()  # Track newly added logs
        
    def restart(self):
        scry, scrx = self.stdscr.getmaxyx()
        self.startx = 0
        self.endx = scrx - 1
        self.starty = 3  # Start below the status bar
        self.endy = scry - 5  # Leave room for now playing component
        self.component = LogWindowComponent(
            self.stdscr,
            self.starty,
            self.startx,
            self.endy,
            self.endx,
            self.logs
        )
    
    def add_log(self, message):
        """Add a new log message"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        # Enhanced log tagging with more specific categories for better coloring
        if "[ERROR]" in message:
            log_entry = f"<error>{log_entry}</error>"
        elif "Canvas URL found" in message:
            log_entry = f"<canvas>{log_entry}</canvas>"
        elif "Artist image URL" in message:
            log_entry = f"<artist>{log_entry}</artist>"
        elif "Track color" in message:
            log_entry = f"<color>{log_entry}</color>"
        elif any(term in message for term in ["Next track", "Previous track"]):
            log_entry = f"<navigation>{log_entry}</navigation>"
        elif any(term in message for term in ["Playback", "Playing", "resumed", "paused"]):
            log_entry = f"<playback>{log_entry}</playback>"
        elif any(term in message for term in ["Shuffle", "Repeat"]):
            log_entry = f"<control>{log_entry}</control>"
        elif "Client" in message and "connected" in message:
            log_entry = f"<connection>{log_entry}</connection>"
        elif any(term in message for term in ["Displaying", "Listing"]):
            log_entry = f"<display>{log_entry}</display>"
        elif any(term in message for term in ["Searching", "Search"]):
            log_entry = f"<search>{log_entry}</search>"
        else:
            log_entry = f"<normal>{log_entry}</normal>"
            
        self.logs.append(log_entry)
        # Remember the index of the new log
        self.new_log_indexes.add(len(self.logs) - 1)
        
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)  # Remove oldest log entry
            # Adjust indexes when removing old logs
            self.new_log_indexes = {idx - 1 for idx in self.new_log_indexes if idx > 0}
            
        if hasattr(self, 'component') and self.component:
            self.component.logs = self.logs
            # Mark new logs for animation
            for idx in self.new_log_indexes:
                self.component.add_log_for_animation(idx)
            # Force the UI to update immediately to show the animation
            self.render(None)
            self.new_log_indexes.clear()

class LogWindowComponent:
    """Inner component for displaying logs"""
    def __init__(self, stdscr, starty, startx, endy, endx, logs):
        self.stdscr = stdscr
        self.starty = starty
        self.startx = startx
        self.endy = endy
        self.endx = endx
        self.active = False
        self.logs = logs
        self.scroll_offset = 0
        # Animation state
        self.animated_logs = {}  # Maps log index to animation frame
        self.animation_frames = 8  # Reduce frames for faster animation
        self.animation_active = False  # Whether any log is currently animating
    
    def add_log_for_animation(self, log_index):
        """Mark a log for animation"""
        self.animated_logs[log_index] = 0
        self.animation_active = True
    
    def render(self, status=None):
        """Render the log messages"""
        # Clear log area
        for y in range(self.starty + 1, self.endy):
            self.stdscr.addstr(y, self.startx + 1, " " * (self.endx - self.startx - 1))
        
        # Calculate available lines
        available_lines = self.endy - self.starty - 1
        
        # Get logs to display
        display_logs = self.logs[-available_lines-self.scroll_offset:] if len(self.logs) > available_lines else self.logs
        
        # Track whether we have any active animations
        has_active_animations = False
        
        # Display logs
        for i, log in enumerate(display_logs):
            if i < available_lines:
                y = self.starty + 1 + i
                max_width = self.endx - self.startx - 2
                
                # Calculate the actual index in the logs list
                log_index = len(self.logs) - len(display_logs) + i
                
                # Calculate animation state for this log
                animation_progress = 0
                is_animating = False
                
                if log_index in self.animated_logs:
                    animation_frame = self.animated_logs[log_index]
                    if animation_frame < self.animation_frames:
                        is_animating = True
                        has_active_animations = True
                        # Use an accelerated animation curve to start fast and slow down
                        animation_progress = (animation_frame / self.animation_frames) ** 0.15
                        self.animated_logs[log_index] += 1.8
                
                # Determine text content and color based on log tag
                log_color = curses.color_pair(COLOR_DEFAULT)
                attr = 0
                
                if "<error>" in log:
                    text = log.replace("<error>", "").replace("</error>", "")
                    log_color = curses.color_pair(COLOR_ERROR)
                    attr = curses.A_BOLD
                elif "<canvas>" in log:
                    text = log.replace("<canvas>", "").replace("</canvas>", "")
                    log_color = curses.color_pair(COLOR_HIGHLIGHT)
                    attr = curses.A_BOLD
                elif "<artist>" in log:
                    text = log.replace("<artist>", "").replace("</artist>", "")
                    log_color = curses.color_pair(COLOR_ALT)
                    attr = curses.A_BOLD
                elif "<color>" in log:
                    text = log.replace("<color>", "").replace("</color>", "")
                    log_color = curses.color_pair(COLOR_WARNING)
                    attr = curses.A_BOLD
                elif "<navigation>" in log:
                    text = log.replace("<navigation>", "").replace("</navigation>", "")
                    log_color = curses.color_pair(COLOR_INFO)
                    attr = curses.A_BOLD
                elif "<playback>" in log:
                    text = log.replace("<playback>", "").replace("</playback>", "")
                    log_color = curses.color_pair(COLOR_SUCCESS)
                    attr = curses.A_BOLD
                elif "<control>" in log:
                    text = log.replace("<control>", "").replace("</control>", "")
                    log_color = curses.color_pair(COLOR_PLAYING)
                    attr = curses.A_BOLD
                elif "<connection>" in log:
                    text = log.replace("<connection>", "").replace("</connection>", "")
                    log_color = curses.color_pair(COLOR_WARNING)
                    attr = curses.A_BOLD | curses.A_UNDERLINE
                elif "<display>" in log:
                    text = log.replace("<display>", "").replace("</display>", "")
                    log_color = curses.color_pair(COLOR_PAUSED)
                    attr = curses.A_BOLD
                elif "<search>" in log:
                    text = log.replace("<search>", "").replace("</search>", "")
                    log_color = curses.color_pair(COLOR_HIGHLIGHT)
                    attr = curses.A_BOLD
                elif "<normal>" in log:
                    text = log.replace("<normal>", "").replace("</normal>", "")
                    log_color = curses.color_pair(COLOR_DEFAULT)
                else:
                    # Fallback for any logs without tags
                    text = log
                    log_color = curses.color_pair(COLOR_DEFAULT)
                
                # Truncate text if needed
                text = truncate(text, max_width)
                
                # Apply animation for sliding in from left
                if is_animating:
                    # For animation: move from far left to normal position
                    start_x = -len(text)  # Start fully off-screen to the left
                    end_x = self.startx + 1  # End at normal position
                    
                    # Calculate current position based on animation progress
                    current_x = int(start_x + (end_x - start_x) * animation_progress)
                    
                    # Adjust for screen boundaries
                    if current_x < self.startx + 1:
                        # When text is partially off-screen, only show visible part
                        offset = (self.startx + 1) - current_x
                        visible_length = len(text) - offset
                        if visible_length > 0:
                            self.stdscr.attron(log_color | attr)
                            visible_text = text[offset:offset+visible_length]
                            self.stdscr.addstr(y, self.startx + 1, visible_text)
                            self.stdscr.attroff(log_color | attr)
                    else:
                        # Text is fully on-screen
                        self.stdscr.attron(log_color | attr)
                        self.stdscr.addstr(y, current_x, text)
                        self.stdscr.attroff(log_color | attr)
                else:
                    # Draw normal log (not animating or animation complete)
                    self.stdscr.attron(log_color | attr)
                    self.stdscr.addstr(y, self.startx + 1, text)
                    self.stdscr.attroff(log_color | attr)
        
        # Update animation active state based on whether we have any active animations
        self.animation_active = has_active_animations

class NowPlaying(Component):
    """Component for displaying currently playing track"""
    def __init__(self, stdscr):
        super().__init__(stdscr)
        self.title = "Now Playing"
        self.restart()
    
    def restart(self):
        scry, scrx = self.stdscr.getmaxyx()
        self.startx = 0
        self.endx = scrx - 1
        # Avoid using the last row which causes border rendering issues
        self.starty = scry - 4  # Start 4 rows from bottom
        self.endy = scry - 2    # End 2 rows from bottom to avoid rendering issues
        self.component = NowPlayingComponent(
            self.stdscr,
            self.starty,
            self.startx,
            self.endy,
            self.endx
        )

class SpotipyUI:
    """Main UI manager class"""
    def __init__(self, stdscr, api_client):
        self.stdscr = stdscr
        self.api_client = api_client
        self.running = True
        self.shutdown_flag = threading.Event()
        self.lock = threading.Lock()
        self.resize_event = threading.Event()
        
        # Store initial terminal size
        self.term_height, self.term_width = stdscr.getmaxyx()
        
        # Initialize curses
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(0)  # Hide cursor
        
        # Initialize color pairs with meaningful names
        curses.init_pair(COLOR_DEFAULT, curses.COLOR_WHITE, -1)  # Default (white on default bg)
        curses.init_pair(COLOR_SUCCESS, curses.COLOR_GREEN, -1)  # Success (green)
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)      # Error (red)
        curses.init_pair(COLOR_BORDER_INACTIVE, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Border inactive
        curses.init_pair(COLOR_BORDER_ACTIVE, curses.COLOR_WHITE, curses.COLOR_CYAN)    # Border active
        curses.init_pair(COLOR_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)         # Selected item
        curses.init_pair(COLOR_INFO, curses.COLOR_CYAN, -1)      # Info (cyan)
        curses.init_pair(COLOR_ALT, curses.COLOR_BLUE, -1)       # Alt (blue)
        curses.init_pair(COLOR_POPUP, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Popup bg
        curses.init_pair(COLOR_HIGHLIGHT, curses.COLOR_MAGENTA, -1)  # Highlight (magenta)
        curses.init_pair(COLOR_WARNING, curses.COLOR_YELLOW, -1)     # Warning (yellow)
        curses.init_pair(COLOR_BORDER, curses.COLOR_WHITE, -1)   # Border (white on default bg)
        curses.init_pair(COLOR_PLAYING, curses.COLOR_GREEN, -1)  # Playing text
        curses.init_pair(COLOR_PAUSED, curses.COLOR_YELLOW, -1)  # Paused text
        curses.init_pair(COLOR_TIMESTAMP, curses.COLOR_MAGENTA, -1)  # Timestamp text
        
        # Try to enable special key handling
        try:
            stdscr.keypad(True)
        except:
            pass
            
        # Initialize UI components
        self.status_bar = StatusBar(stdscr)
        self.log_window = LogWindow(stdscr)
        self.now_playing = NowPlaying(stdscr)
        
        # Add initial log message
        self.log_window.add_log("Starting Resonite Spotipy...")
        
        # Set up resize handler
        self.setup_resize_handler()
        
        # Start UI update thread
        self.update_thread = threading.Thread(target=self.update_ui_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def add_log(self, message):
        """Add a log message to the log window"""
        self.log_window.add_log(message)
        self.log_window.render(None)
        self.stdscr.refresh()
    
    def set_client_status(self, connected, client_id=""):
        """Set the client connection status"""
        self.status_bar.set_client_status(connected, client_id)
        self.status_bar.render(None)
        self.stdscr.refresh()
    
    def shutdown(self):
        """Shutdown the UI"""
        self.running = False
        self.shutdown_flag.set()
        time.sleep(0.2)  # Give update thread time to exit
    
    def setup_resize_handler(self):
        """Set up a signal handler for terminal resize events"""
        try:
            # Only try to use SIGWINCH on Unix-like systems
            import signal
            if hasattr(signal, 'SIGWINCH'):
                signal.signal(signal.SIGWINCH, self.handle_resize)
            else:
                # Windows doesn't have SIGWINCH
                self.add_log("Using polling for resize detection")
        except Exception:
            # Any error means we fall back to polling
            self.add_log("Using polling for resize detection")
    
    def handle_resize(self, signum=None, frame=None):
        """Handle terminal resize event"""
        # Set the resize event flag
        self.resize_event.set()
    
    def check_resize(self):
        """Check if terminal dimensions have changed"""
        try:
            new_height, new_width = self.stdscr.getmaxyx()
            if new_height != self.term_height or new_width != self.term_width:
                self.term_height, self.term_width = new_height, new_width
                return True
        except:
            pass
        return False
    
    def resize_ui(self):
        """Resize and redraw all UI components"""
        with self.lock:
            try:
                # Clear the terminal and reset cursor position
                self.stdscr.clear()
                
                # Store new terminal dimensions
                self.term_height, self.term_width = self.stdscr.getmaxyx()
                
                # Recalculate component dimensions
                self.status_bar.restart()
                self.log_window.restart()
                self.now_playing.restart()
                
                # Redraw all components in proper order
                self.status_bar.render(None)
                self.log_window.render(None)
                self.now_playing.render(None)
                
                # Refresh the screen
                self.stdscr.refresh()
                
                # Log the resize event (but only if it wasn't the initial setup)
                if self.running:
                    self.add_log(f"Terminal resized to {self.term_width}x{self.term_height}")
            except Exception as e:
                # Try to log the error, but don't cause additional issues
                try:
                    self.add_log(f"Error during resize: {str(e)}")
                except:
                    pass
            
            # Clear the resize event flag
            self.resize_event.clear()
    
    def test_border_colors(self):
        """Test cycling through border colors"""
        self.add_log("Testing border colors...")
        colors = [
            ("Red", curses.COLOR_RED),
            ("Green", curses.COLOR_GREEN),
            ("Yellow", curses.COLOR_YELLOW),
            ("Blue", curses.COLOR_BLUE),
            ("Magenta", curses.COLOR_MAGENTA),
            ("Cyan", curses.COLOR_CYAN),
            ("White", curses.COLOR_WHITE)
        ]
        
        for name, color in colors:
            self.add_log(f"Testing border color: {name}")
            curses.init_pair(COLOR_BORDER, color, -1)
            self.redraw_ui()
            time.sleep(1)
            
        # Reset to default
        curses.init_pair(COLOR_BORDER, curses.COLOR_WHITE, -1)
        self.redraw_ui()
        self.add_log("Border color test complete")
    
    def redraw_ui(self):
        """Force redraw of all UI components"""
        try:
            with self.lock:
                self.stdscr.erase()
                self.status_bar.render(None)
                self.log_window.render(None)
                self.now_playing.render(None)
                self.stdscr.refresh()
        except Exception as e:
            self.add_log(f"Error in redraw: {str(e)}")
    
    def update_ui_loop(self):
        """UI update loop running in a separate thread"""
        # Use consistent animation interval of 0.04s for all updates
        animation_interval = 0.04
        resize_check_counter = 0
        
        try:
            while not self.shutdown_flag.is_set():
                try:
                    # Check for a resize event (every 5 frames to avoid constant checking)
                    resize_check_counter += 1
                    if resize_check_counter >= 5:
                        resize_check_counter = 0
                        if self.resize_event.is_set() or self.check_resize():
                            self.resize_ui()
                    
                    # Always use the animation interval for smooth animations
                    interval = animation_interval
                    
                    # Check if there's an active animation
                    now_playing_animating = hasattr(self.now_playing.component, 'animation_active') and self.now_playing.component.animation_active
                    log_animating = hasattr(self.log_window.component, 'animation_active') and self.log_window.component.animation_active
                    is_animating = now_playing_animating or log_animating
                    
                    # Update the now playing component with current track info
                    if self.api_client:
                        try:
                            status = self.api_client.get_current_playback_full()
                            with self.lock:
                                # Update log window first to ensure animations are processed
                                if log_animating:
                                    self.log_window.render(None)
                                self.now_playing.render(status)
                                self.stdscr.refresh()
                        except Exception as e:
                            self.add_log(f"Error updating playback info: {str(e)[:50]}")
                    
                    # Apply border coloring from album art
                    if self.api_client and not is_animating:
                        try:
                            track_data = self.api_client.get_current_playback_full()
                            
                            # Only process colors if we have track data
                            if track_data and 'item' in track_data and track_data['item']:
                                # Conditionally import to avoid circular imports
                                try:
                                    import spotify_color
                                    spotify_color.process_current_track(self.stdscr, self, track_data)
                                except ImportError:
                                    pass  # Silently ignore if color module not available
                        except:
                            pass  # Silently ignore API errors for color processing
                    
                    # Sleep for the animation interval
                    time.sleep(interval)
                    
                except Exception as e:
                    # Catch any exceptions in the loop to prevent crashing
                    self.add_log(f"UI update error: {str(e)}")
                    time.sleep(animation_interval)
        except Exception as e:
            # Log if the whole loop crashes
            try:
                self.add_log(f"UI loop crashed: {str(e)}")
            except:
                pass

def curses_main(stdscr):
    global UI, API, CLIENT
    
    # Enable special key detection in curses
    stdscr.keypad(True)
    
    # Initialize UI
    UI = SpotipyUI(stdscr, CLIENT)
    
    # Wait for user to quit
    while True:
        try:
            key = stdscr.getch()
            if key == ord('q'):  # Quit on 'q'
                break
            elif key == ord('r'):  # Refresh on 'r'
                UI.resize_ui()  # Use same function for manual refresh
            elif key == ord('c'):  # Test cycling colors with 'c'
                UI.test_border_colors()
            elif key == curses.KEY_RESIZE:  # Handle terminal resize
                UI.handle_resize()
            elif key == ord('1'):  # Red
                curses.init_pair(17, curses.COLOR_RED, -1)
                UI.redraw_ui()
            elif key == ord('2'):  # Green
                curses.init_pair(17, curses.COLOR_GREEN, -1)
                UI.redraw_ui()
            elif key == ord('3'):  # Yellow
                curses.init_pair(17, curses.COLOR_YELLOW, -1)
                UI.redraw_ui()
            elif key == ord('4'):  # Blue
                curses.init_pair(17, curses.COLOR_BLUE, -1)
                UI.redraw_ui()
            elif key == ord('5'):  # Magenta
                curses.init_pair(17, curses.COLOR_MAGENTA, -1)
                UI.redraw_ui()
            elif key == ord('6'):  # Cyan
                curses.init_pair(17, curses.COLOR_CYAN, -1)
                UI.redraw_ui()
            elif key == ord('7'):  # White (default)
                curses.init_pair(17, curses.COLOR_WHITE, -1)
                UI.redraw_ui()
            elif key == ord('u'):  # Test URL color update with 'u'
                # Test with a known album art URL
                UI.add_log("Testing manual URL color update...")
                import spotify_color
                test_url = "https://i.scdn.co/image/ab67616d0000b273b83fe3578a60a300b1a42953"
                spotify_color.force_update_from_url(stdscr, UI, test_url)
            elif key == ord('f'):  # Force update with current track
                UI.add_log("Testing color update with current track...")
                # Get current playback
                if hasattr(UI.api_client, '_api'):
                    try:
                        current_playback = UI.api_client._api.current_playback()
                        if current_playback and 'item' in current_playback and current_playback['item']:
                            import spotify_color
                            spotify_color.process_current_track(stdscr, UI, current_playback)
                            UI.add_log("Forced color update from current track")
                        else:
                            UI.add_log("No track currently playing")
                    except Exception as e:
                        UI.add_log(f"Error: {str(e)}")
                else:
                    UI.add_log("API client not available")
        except KeyboardInterrupt:
            break
    
    # Shutdown UI
    if UI:
        UI.shutdown() 