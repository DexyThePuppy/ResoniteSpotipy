import asyncio as aio
import websockets as ws
import spotipy as sp
import signal
import curses
import sys
import os
import time
import requests
from datetime import datetime
import threading

from APIClient import APIClient  # The class that handles the Spotify API and custom functions
from resonite_ui import SpotipyUI
# Import the color extraction module
import spotify_color

# Global variables
API: sp.Spotify = None
CLIENT: APIClient = None
PORT: int = 0000
UI = None
DEBUG = False
# Cache for canvas and artist data to avoid redundant checks
TRACK_CACHE = {}
CURRENT_TRACK_ID = None

def get_spotify_canvas(track_id):
    """Fetch Spotify Canvas video for a given track ID"""
    # Check if we already have cached data for this track
    if track_id in TRACK_CACHE and "canvas_checked" in TRACK_CACHE[track_id]:
        return TRACK_CACHE[track_id].get("canvas_data")
        
    try:
        url = f"https://spotifycanvas-indol.vercel.app/api/canvas?trackId={track_id}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data and "canvasesList" in data and len(data["canvasesList"]) > 0:
                canvas_data = data["canvasesList"][0]
                result = {
                    "canvasUrl": canvas_data.get("canvasUrl"),
                    "artistImgUrl": canvas_data.get("artist", {}).get("artistImgUrl")
                }
                
                # Initialize track cache if needed
                if track_id not in TRACK_CACHE:
                    TRACK_CACHE[track_id] = {}
                
                # Store the canvas data and mark as checked
                TRACK_CACHE[track_id]["canvas_data"] = result
                TRACK_CACHE[track_id]["canvas_checked"] = True
                
                return result
    except Exception as e:
        if UI:
            UI.add_log(f"[ERROR] Error fetching canvas: {str(e)}")
    
    # Mark as checked even if no data found
    if track_id not in TRACK_CACHE:
        TRACK_CACHE[track_id] = {}
    TRACK_CACHE[track_id]["canvas_checked"] = True
    TRACK_CACHE[track_id]["canvas_data"] = None
    
    return None

def get_artist_image(artist_id):
    """Get artist image from Spotify API with caching"""
    # Check cache first
    if artist_id in TRACK_CACHE and "artist_image_checked" in TRACK_CACHE[artist_id]:
        return TRACK_CACHE[artist_id].get("artist_image")
        
    try:
        artist_data = API.artist(artist_id)
        if artist_data and artist_data.get("images") and len(artist_data["images"]) > 0:
            artist_img_url = artist_data["images"][0]["url"]
            
            # Initialize artist cache if needed
            if artist_id not in TRACK_CACHE:
                TRACK_CACHE[artist_id] = {}
            
            # Store the artist image and mark as checked
            TRACK_CACHE[artist_id]["artist_image"] = artist_img_url
            TRACK_CACHE[artist_id]["artist_image_checked"] = True
            
            return artist_img_url
    except Exception as e:
        if UI:
            UI.add_log(f"[ERROR] Error fetching artist image: {str(e)}")
    
    # Mark as checked even if no data found
    if artist_id not in TRACK_CACHE:
        TRACK_CACHE[artist_id] = {}
    TRACK_CACHE[artist_id]["artist_image_checked"] = True
    TRACK_CACHE[artist_id]["artist_image"] = None
    
    return None

def current_time():
    return f"[{datetime.now():%H:%M:%S}]"

def check_ids_file():
    """Check if IDs.txt exists and create it from template if missing"""
    if not os.path.exists("IDs.txt"):
        # IDs.txt doesn't exist, create it from template
        template_content = """# You'll find your Client ID and Client Secret in your Spotify application developer panel under Settings.
Client ID: ClientIdHere
Client Secret: SecretHere

# Under the same settings menu you'll find a "Redirect" section, which lets you hook up a link for the API to redirect you to once it's connected
Redirect URI: http://localhost:8000/callback

# The port ID allows you to choose what port this websocket will connect through
# You MUST have the same port ID hooked up in Resonite as you put in here!
Port ID: 6969"""

        try:
            with open("IDs.txt", "w") as f:
                f.write(template_content)
            print("\n" + "="*60)
            print("ATTENTION: IDs.txt was not found and has been created.")
            print("You need to edit this file with your Spotify API credentials.")
            print("The program will now exit. Please edit IDs.txt and restart.")
            print("="*60 + "\n")
            input("Press Enter to exit...")
            sys.exit(0)
        except Exception as e:
            print(f"Error creating IDs.txt: {str(e)}")
            print("Please create this file manually with your Spotify credentials.")
            input("Press Enter to exit...")
            sys.exit(1)
    else:
        # Check if IDs.txt contains default values
        with open("IDs.txt", "r") as f:
            content = f.read()
            if "ClientIdHere" in content or "SecretHere" in content:
                print("\n" + "="*60)
                print("ATTENTION: IDs.txt contains default template values.")
                print("You need to edit this file with your actual Spotify API credentials.")
                print("The program will now exit. Please edit IDs.txt and restart.")
                print("="*60 + "\n")
                input("Press Enter to exit...")
                sys.exit(0)

# Reads data from the IDs.txt file and parses them to be used in the API
def connect_to_spotify():
    global API, CLIENT, PORT
    
    results: list[str | int] = ["", "", "", 0]
    indices: list[int]       = [1, 2, 5, 9]
    
    with open("IDs.txt") as file:
        lines: list[str] = file.readlines()
    
    for i in range(0, 4):
        results[i] = lines[indices[i]].split(" ")[2].removesuffix("\n").replace("<", "").replace(">", "")
        i += 1
    PORT = int(results[3])
    
    if (str(results[3]) in results[2]):
        raise Exception(f"Invalid port! ({PORT = }). Use a different port than the one used by the callback URI.")
    
    _ = """user-library-modify,user-library-read,user-read-currently-playing,user-read-playback-position,
            user-read-playback-state,user-modify-playback-state,app-remote-control,streaming,playlist-read-private,
            playlist-modify-private,playlist-modify-public,playlist-read-collaborative"""
    CLIENT = APIClient(results[0], results[1], results[2], _)
    API = CLIENT._api
    CLIENT._debug = DEBUG
    
    CLIENT.find_device()
    
    return True

# Displays current information about the currently playing track and/or the playback states
def display_current_info(received: str) -> str:
    global CURRENT_TRACK_ID
    payload: str = ""
    
    match (received):
        case "current_info": # Used for getting the currently playing track and the playback states
            try:
                track_data = API.current_user_playing_track()
                track_item = track_data['item'] # Throws an error if there's no currently playing track
                track_id = track_item['id']
                
                # Track change detection - only log new info if track changed
                track_changed = CURRENT_TRACK_ID != track_id
                CURRENT_TRACK_ID = track_id
                
                # Get canvas data if available
                canvas_data = get_spotify_canvas(track_id)
                if track_changed:
                    if canvas_data and canvas_data.get("canvasUrl"):
                        if UI:
                            UI.add_log(f"Canvas URL found: {canvas_data['canvasUrl'][:30]}...")
                    else:
                        if UI:
                            UI.add_log("No canvas found for current playing song")
                
                # Get artist image
                artist_id = track_item['artists'][0]['id']
                artist_img_url = get_artist_image(artist_id)
                if track_changed and artist_img_url:
                    if UI:
                        UI.add_log(f"Artist image URL: {artist_img_url[:30]}...")
                
                # Get track color
                if track_changed and track_item.get('album') and track_item['album'].get('images'):
                    album_art_url = track_item['album']['images'][0]['url']
                    color_hex = spotify_color.get_dominant_color(album_art_url)
                    if color_hex:
                        if UI:
                            UI.add_log(f"Track color: {color_hex}")
                
                payload = CLIENT.get_track_data(track_data, ws_call="current") + "\n" + CLIENT.get_playback_states()
                
                # Append canvas and artist data if available
                if canvas_data and canvas_data.get("canvasUrl"):
                    payload += f"\nCANVAS_URL:{canvas_data['canvasUrl']}"
                if artist_img_url:
                    payload += f"\nARTIST_IMG_URL:{artist_img_url}"
                if track_item.get('album') and track_item['album'].get('images'):
                    album_art_url = track_item['album']['images'][0]['url']
                    color_hex = spotify_color.get_dominant_color(album_art_url)
                    if color_hex:
                        payload += f"\nTRACK_COLOR:{color_hex}"
                
            except Exception as e:
                if UI:
                    UI.add_log(f"[ERROR] No current song active: {str(e)}")
                payload = "[ERROR] No current song active"
        
        case "current_track":
            try:
                track_data = API.current_user_playing_track()
                track_item = track_data['item'] # Throws an error if there's no currently playing track
                track_id = track_item['id']
                
                # Track change detection - only log new info if track changed
                track_changed = CURRENT_TRACK_ID != track_id
                CURRENT_TRACK_ID = track_id
                
                # Get canvas data if available
                canvas_data = get_spotify_canvas(track_id)
                if track_changed:
                    if canvas_data and canvas_data.get("canvasUrl"):
                        if UI:
                            UI.add_log(f"Canvas URL found: {canvas_data['canvasUrl']}")
                    else:
                        if UI:
                            UI.add_log("No canvas found for current playing song")
                
                # Get artist image
                artist_id = track_item['artists'][0]['id']
                artist_img_url = get_artist_image(artist_id)
                if track_changed and artist_img_url:
                    if UI:
                        UI.add_log(f"Artist image URL: {artist_img_url}")
                
                # Get track color
                if track_changed and track_item.get('album') and track_item['album'].get('images'):
                    album_art_url = track_item['album']['images'][0]['url']
                    color_hex = spotify_color.get_dominant_color(album_art_url)
                    if color_hex:
                        if UI:
                            UI.add_log(f"Track color: {color_hex}")
                
                payload = CLIENT.get_track_data(track_data, ws_call="current")
                
                # Append canvas and artist data if available
                if canvas_data and canvas_data.get("canvasUrl"):
                    payload += f"\nCANVAS_URL:{canvas_data['canvasUrl']}"
                if artist_img_url:
                    payload += f"\nARTIST_IMG_URL:{artist_img_url}"
                if track_item.get('album') and track_item['album'].get('images'):
                    album_art_url = track_item['album']['images'][0]['url']
                    color_hex = spotify_color.get_dominant_color(album_art_url)
                    if color_hex:
                        payload += f"\nTRACK_COLOR:{color_hex}"
                
            except:
                if UI:
                    UI.add_log("No current song active")
                payload = "[ERROR] No current song active"
        
        case "current_states":
            try:
                payload = CLIENT.get_playback_states()
            except:
                if UI:
                    UI.add_log("Error getting playback states")
                payload = "[ERROR] Error getting playback states"
    
    return payload

# Modifies the currently playing track, like going to the next or previous song, or playing a new song
def modify_current_track(received: str, data: str) -> str:
    payload: str = ""
    
    match (received):
        case "next":
            try:
                CLIENT.run_action(API.next_track)
                if UI:
                    UI.add_log("Next track")
                payload = "[NEXT SONG]"
            except Exception as e:
                if UI:
                    UI.add_log(f"[ERROR] Error going to next song: {str(e)}")
                payload = "[ERROR] Error going to next song"
        
        case "previous":
            try:
                if (API.current_playback()["progress_ms"] > 4000):
                    CLIENT.run_action(API.seek_track, 0)
                else:
                    CLIENT.run_action(API.previous_track)
                
                if UI:
                    UI.add_log("Previous track")
                payload = "[PREVIOUS SONG]"
            except Exception as e:
                if UI:
                    UI.add_log(f"[ERROR] Error going to previous song: {str(e)}")
                payload = "[ERROR] Error going to previous song"
        
        case "play":
            if (data != None):
                # Format for searching: "<track | album | track,album> <uri>"
                # Format for playing from playlist or album: "<uri> <offset uri>"
                # Format for playing from queue: "<offset uri>"
                play_data: list[str] = data.split(" ")
                try:
                    match (DISPLAY):
                        case "search":
                            if (play_data[0] == "track"):
                                API.start_playback(uris=[play_data[1]]) # Plays just the selected song
                                if UI:
                                    UI.add_log(f"Playing selected searched song")
                                payload = "[PLAY] Played selected searched song"
                        
                        case "queue":
                            API.start_playback(context_uri=API.currently_playing()["context"]["uri"], offset={"uri": play_data[1]}) # Plays song in the queue that was clicked on
                            if UI:
                                UI.add_log(f"Playing selected song in queue")
                            payload = "[PLAY] Played selected song in queue"
                        
                        case "playlist" | "album":
                            if (len(play_data) == 3):
                                API.start_playback(context_uri=play_data[1], offset={"uri": play_data[2]}) # Plays song in the playlist/album that was clicked on
                                if UI:
                                    UI.add_log(f"Playing selected song in playlist/album")
                                payload = "[PLAY] Played selected song in playlist/album"
                            else:
                                API.start_playback(context_uri=play_data[1]) # Plays the playlist/album that was clicked on
                                if UI:
                                    UI.add_log(f"Playing selected playlist/album")
                                payload = "[PLAY] Played selected playlist/album"
                        
                except:
                    if UI:
                        UI.add_log("Error playing song")
                    payload = "[ERROR] Error playing song"

    return payload

# Modifies the playback states, like pausing, resuming, or changing the shuffle state
def modify_playback_states(received: str) -> str:
    payload: str = ""
    
    if (received == "pause" or received == "resume"):
        try:
            _ = API.current_user_playing_track()['is_playing']
        except:
            _ = False
        
        playing = "False" if _ else "True"
        
        try:
            CLIENT.run_action(API.pause_playback) if _ else CLIENT.run_action(API.start_playback)
            
            if UI:
                UI.add_log(f"Playback {'paused' if _ else 'resumed'}")
            
            payload = CLIENT.get_playback_states(playing=playing)
        except Exception as e:
            if UI:
                UI.add_log(f"[ERROR] Error {'pausing' if _ else 'resuming'} playback: {str(e)}")
            payload = "[ERROR] Error pausing/resuming playback"
             
    match (received):       
        case "shuffle":
            try:
                shuffle: bool = API.current_playback()["shuffle_state"]
                CLIENT.run_action(API.shuffle, not shuffle) # Throws an error if it can't change the shuffle state
                
                if UI:
                    UI.add_log(f"Shuffle {'disabled' if shuffle else 'enabled'}")
                
                payload = CLIENT.get_playback_states(shuffle=str(not shuffle))
            except Exception as e:
                if UI:
                    UI.add_log(f"[ERROR] Error changing shuffle state: {str(e)}")
                payload = "[ERROR] Error changing shuffle state"
        
        case "repeat":
            try:
                states: list[str] = ["track", "context", "off"]
                repeat: str       = API.current_playback()["repeat_state"]
                change: str       = states[(states.index(repeat) + 1) if (repeat != "off") else 0]
                CLIENT.run_action(API.repeat, change) # Throws an error if it can't change the repeat state

                if UI:
                    UI.add_log(f"Repeat mode: {change.capitalize()}")

                payload = CLIENT.get_playback_states(repeat=change.capitalize())
            except:
                if UI:
                    UI.add_log("Error changing repeat state")
                payload = "[ERROR] Error changing repeat state"
    
    return payload

# Lists results stuff, such as playlists, currently playing queue, or search results
def list_stuff(received: str, data: str) -> str:
    global DISPLAY
    payload: str = ""
    
    match (received):
        case "list_playlists":
            DISPLAY = "playlists"
            payload = CLIENT.get_playlists()

        case "search":
            try:
                DISPLAY = "search"
                search_data: list[str] = data.split(" ") # Format: "<type> <search query>"
                
                if (len(search_data) > 1):
                    if UI:
                        UI.add_log(f"Searching for {search_data[0]}: {' '.join(search_data[1:])}")
                    
                    search_results = API.search(" ".join(search_data[1:]), type=search_data[0], market="US") # Valid arguments for type: "track", "album", "track,album"
                    
                    search_split = search_data[0].split(",")
                    if (len(search_split) > 1): # If the search is for more than one type
                        payload = ""
                        for type in search_split:
                            res = search_results[f"{type}s"]
                            payload += CLIENT.get_results(res, ws_call="search") if type != "artist" else CLIENT.get_artists(res)
                    elif (search_data[0] == "artist"):
                        payload = CLIENT.get_artists(search_results["artists"])
                    else:
                        payload = CLIENT.get_results(search_results[f"{search_data[0]}s"], ws_call="search")
            except:
                if UI:
                    UI.add_log("Error searching")
                payload = "[ERROR] Error searching"
            
        case "list_queue":
            try:
                _ = API.queue()["queue"][0] # Throws an error if there's no queue available
                
                DISPLAY = "queue"
                if UI:
                    UI.add_log("Listing queue")
                payload = CLIENT.get_results(API.queue(), ws_call="queue", keyword="queue")
            except:
                if UI:
                    UI.add_log("No queue found")
                payload = "[ERROR] No queue found"
    
    return payload

# Displays tracks in an album or playlist
def display_info(received: str, data: str) -> str:
    global DISPLAY
    payload: str = ""
    
    match (received):
        case "display_album":
            # Data format: <album uri>
            try:
                DISPLAY = "album"
                _ = API.album_tracks(data)["items"][0] # Throws an error if there are no tracks in the album
            
                album_info = API.album(data)
                if UI:
                    UI.add_log(f"Displaying album: {album_info['name']}")
                
                payload = CLIENT.display_album(album_info)
            except:
                if UI:
                    UI.add_log("Error loading album tracks")
                payload = "[ERROR] Error loading album tracks"

        case "display_playlist":
            # Data format: <playlist uri> <offset>
            DISPLAY = "playlist"
            spl = data.split(" ")
            try:
                if ("collection" in spl[0]):
                    _ = API.current_user_saved_tracks()["items"][0] # Throws an error if there are no tracks in their Liked Songs
                    
                    if UI:
                        UI.add_log("Displaying Liked Songs")
                    
                    payload = CLIENT.display_playlist(API.current_user_saved_tracks(), offset=int(spl[1]), uri=spl[0])
                else:
                    playlist_info = API.playlist(playlist_id=spl[0])
                    _ = playlist_info["tracks"]["items"] # Throws an error if there are no tracks in the playlist
                    
                    if UI:
                        UI.add_log(f"Displaying playlist: {playlist_info['name']}")
                
                    payload = CLIENT.display_playlist(playlist_info, offset=int(spl[1]))
            except:
                if UI:
                    UI.add_log("Error loading playlist tracks")
                payload = "[ERROR] Error loading playlist tracks"
        
        case "display_artist":
            # Data format: <artist uri>
            DISPLAY = "artist"
            try:
                artist_info = API.artist(data)
                _ = API.artist_top_tracks(data)["tracks"][0] # Throws an error if the artist has no tracks
                
                if UI:
                    UI.add_log(f"Displaying artist: {artist_info['name']}")
                
                payload = CLIENT.display_artist(artist_info, API.artist_top_tracks(data), API.artist_albums(data))
            except:
                if UI:
                    UI.add_log("Error loading artist")
                payload = "[ERROR] Error loading artist"
    
    return payload

async def socket(websocket: ws.WebSocketClientProtocol):
    global DISPLAY, UI
    
    # Initializing the websocket
    ID = str(websocket.id)
    if UI:
        UI.add_log(f"Client {ID[:8]} connected!")
        UI.set_client_status(True, ID[:8])
    
    await websocket.send(CLIENT.get_playback_states())
    
    try:
        async for message in websocket:
            # Message format: "command" "extra data"
            parsed: list[str] = message.removesuffix(" ").split(" ")
            received: str     = ""
            data: str | None  = None
            
            if (len(parsed) < 2):
                received = message
                if UI:
                    UI.add_log(f"Client {ID[:8]} command: {received}")
            else:
                received = parsed[0]
                data     = " ".join(parsed[1:])
                if UI:
                    UI.add_log(f"Client {ID[:8]} command: {received} {data[:20] + '...' if len(data) > 20 else data}")

            payload: str = ""
            
            if (received in ["current_info", "current_song", "current_states"]):
                payload = display_current_info(received)
                
            elif (received in ["next", "previous", "play"]):
                payload = modify_current_track(received, data)

            elif (received in ["pause", "resume", "shuffle", "repeat"]):
                payload = modify_playback_states(received)
                
            elif (received in ["list_playlists", "search", "list_queue"]):
                payload = list_stuff(received, data)
            
            elif (received in ["display_album", "display_playlist", "display_artist"]):
                payload = display_info(received, data)
            
            elif (received in ["get_canvas_video", "get_artist_image", "get_track_color"]):
                try:
                    track_data = API.current_user_playing_track()
                    track_id = track_data['item']['id']
                    
                    if received == "get_canvas_video":
                        canvas_data = get_spotify_canvas(track_id)
                        if canvas_data and canvas_data.get("canvasUrl"):
                            payload = f"CANVAS_URL:{canvas_data['canvasUrl']}"
                        else:
                            payload = "NO_CANVAS_AVAILABLE"
                    
                    elif received == "get_artist_image":
                        artist_id = track_data['item']['artists'][0]['id']
                        artist_img_url = get_artist_image(artist_id)
                        if artist_img_url:
                            payload = f"ARTIST_IMG_URL:{artist_img_url}"
                        else:
                            payload = "NO_ARTIST_IMAGE_AVAILABLE"
                    
                    elif received == "get_track_color":
                        # Get album art URL from current track
                        if track_data['item']['album']['images']:
                            album_art_url = track_data['item']['album']['images'][0]['url']
                            # Get dominant color in hex format
                            color_hex = spotify_color.get_dominant_color(album_art_url)
                            if color_hex:
                                payload = f"TRACK_COLOR:{color_hex}"
                            else:
                                payload = "NO_COLOR_AVAILABLE"
                        else:
                            payload = "NO_ALBUM_ART_AVAILABLE"
                
                except Exception as e:
                    if UI:
                        UI.add_log(f"Error processing media request: {str(e)}")
                    payload = f"[ERROR] {str(e)}"
            
            else:
                if UI:
                    UI.add_log(f"Unknown command: {received}")
                payload = "[ERROR] Unknown command"
        
            if DEBUG and payload != "":
                if UI:
                    UI.add_log(f"Response sent: {payload}")
                    
            await websocket.send(payload)
            
    except Exception as e:
        if UI:
            UI.add_log(f"[ERROR] Connection error with client {ID[:8]}: {str(e)}")
            UI.set_client_status(False)

# Variable to store the current screen mode we're displaying
DISPLAY: str = ""

def curses_main(stdscr):
    global UI, API, CLIENT
    
    # Initialize UI
    UI = SpotipyUI(stdscr, CLIENT)
    
    # Wait for user to quit
    while True:
        try:
            key = stdscr.getch()
            if key == ord('q'):  # Quit on 'q'
                break
            elif key == ord('r'):  # Refresh on 'r'
                stdscr.clear()
                stdscr.refresh()
        except KeyboardInterrupt:
            break
    
    # Shutdown UI
    if UI:
        UI.shutdown()

async def main():
    global API, CLIENT, UI
    
    # Check for IDs.txt at startup
    check_ids_file()
    
    # Create a shutdown event
    shutdown_event = aio.Event()
    
    # Define a shutdown handler
    def shutdown_signal(signal, frame):
        if UI:
            UI.add_log("Shutting down...")
        shutdown_event.set()
    
    # Register the signal handlers
    signal.signal(signal.SIGINT, shutdown_signal)
    signal.signal(signal.SIGTERM, shutdown_signal)
    
    # Connect to Spotify
    if not connect_to_spotify():
        print("Failed to connect to Spotify")
        return
        
    # Start the UI in a separate thread
    ui_thread = threading.Thread(target=lambda: curses.wrapper(curses_main))
    ui_thread.daemon = True
    ui_thread.start()
    
    # Start the server
    server = await ws.serve(socket, 'localhost', PORT)
    
    # Wait for the shutdown event
    try:
        await shutdown_event.wait()
    finally:
        # Clean shutdown
        server.close()
        await server.wait_closed()
        
        if UI:
            UI.add_log("Server has been shut down.")
            time.sleep(0.5)  # Give UI time to display the message
            UI.shutdown()

if __name__ == '__main__':
    import argparse as arg
    parser = arg.ArgumentParser(description="The websocket server for the Resonite Spotipy project")
    parser.add_argument("-d", "--debug", dest="debug", action="store_true", help="Prints debug messages", default=False)
    args = parser.parse_args()
    
    DEBUG = args.debug
    
    try:
        aio.run(main())
    except KeyboardInterrupt:
        # Already handled
        pass
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)