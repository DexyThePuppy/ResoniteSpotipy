# Resonite Spotipy
A websocket server for talking with the Spotify API with a Resonite websocket client item to compliment it

![ResoniteSpotipy Terminal UI](https://github.com/user-attachments/assets/c84f2740-fa20-42f3-b742-576ba355cb33)

## Terminal User Interface
The application features a colorful and animated terminal UI that displays real-time information:

![Terminal UI Showcase](Screenshot%202025-05-05%20045601.png)

Here's the Resonite record link for the Resonite Spotipy audio player:
`resrec:///U-JayKub/R-CAF0B1B9598EF23797BE641C09DBBD3905EA75224EBD0F7F08F2AD4B61579001`

## Prerequisites
You'll need these Python packages: *websockets*, *asyncio*, *spotipy*, *pillow*, *numpy*, *scikit-learn*, *joblib*, *requests*.
- To install these, run this command: ```pip install websockets asyncio spotipy pillow numpy scikit-learn joblib requests```
- Or you can use the included requirements.txt: ```pip install -r requirements.txt```

## Features
- Connect to Spotify's API using OAuth authentication
- Control playback (play, pause, skip, volume)
- Browse and play from playlists and albums
- View currently playing tracks with album artwork
- Real-time logging with colorful, animated text
- Track metadata including artist images and dominant colors
- Canvas video support for compatible tracks
- Dynamic UI colors based on album artwork (terminal borders change color to match each album)
- Terminal User Interface (TUI) with album details and playback progress
- Smooth animations for track changes and UI elements

## How to setup your Spotify application
**You'll need Spotify Premium to be able to do this!**
- Go to the Spotify Developer Dashboard: https://developer.spotify.com/dashboard
- Click on "Create app"
- Give it a name, description, and ensure that you have a redirect URL for the application (I recommend putting both of these in: "http://localhost:8000/callback" and "http://localhost:8000")
- Once created, go to the application's Settings panel
    - Here's where you'll find the application's Client ID and, by clicking on the "view client secret" button, the Secret ID

## How to setup the websocket server
- Download the ZIP package in the files and unzip it
- Run the `ResoniteSpotipy.exe` executable in the ZIP file
  - On first run, it will generate an IDs.txt template file if one doesn't exist
  - Edit the IDs.txt file with your Spotify application's Client ID, Secret ID, and Redirect URI
  - Make sure the port ID you choose is not the same as the callback URI port
- Restart the application after editing the IDs.txt file

## How to setup the Resonite websocket client
- Spawn out the item from the folder
- Click on the Spotify tab to link up the player to the websocket server
    - Make sure you supply the same port ID as the one you're using for the websocket server!

## Future additions
| Working On | Progress | Version |
| ---------- | -------- | ------- |
| Displaying album tracks & playing a specific album track | ✔️ Completed | v1.1 |
| Displaying playlist tracks & playing a specific playlist track | ✔️ Completed | v1.1 |
| Player for only displaying currently playing song | ✔️ Completed | v1.1 |
| Dynamic UI colors based on album artwork | ✔️ Completed | v1.2 |
| Canvas video & artist image support | ✔️ Completed | v1.3 |
| Animated terminal UI with colorful logs | ✔️ Completed | v1.3 |
| Searching artists & displaying artist profile | ✔️ Completed | v1.3 |
| UI overhaul for the player | 📝 Planned | v1.4 |
| Song queueing system on the player | �� Planned | v2.0 |
