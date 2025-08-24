import socket
import json
import time


import subprocess
import yt_dlp

import speech_recognition as sr

r = sr.Recognizer()
mic = sr.Microphone()

assistantName = "hey cosmo"







def send_mpv_command(command_dict):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect("/tmp/mpvsocket")
        command_json = json.dumps(command_dict).encode('utf-8')
        client.send(command_json + b'\n')
        client.close()
    except Exception as e:
        print("Could not send command to mpv:", e)

def pause_song():
    send_mpv_command({"command": ["set_property", "pause", True]})

def resume_song():
    send_mpv_command({"command": ["set_property", "pause", False]})

def stop_song():
    global process_playing
    if process_playing:
        process_playing.terminate()
        process_playing = None







def listen(say):
    with mic as source:
        print(say)
        audio = r.listen(source)
        print("Processing...")
        try:
          said = r.recognize_google(audio)
          return said

        except sr.UnknownValueError:
            print("Google Speech Recognition could not understand audio")
            return ""


def get_from_youtube(query):
    print(f"🎵 Searching and playing: {query}")
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'default_search': 'ytsearch1',
        'format': 'bestaudio/best'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)

        # If it's a search, results are inside entries
        if 'entries' in info and info['entries']:
            video = info['entries'][0]
        else:
            video = info

        return video['url']
    




def play_song(url):
    global process_playing

    if process_playing:
        process_playing.terminate()
    process_playing = subprocess.Popen([
    "mpv", url,
    "--no-video", "--quiet",
    "--input-ipc-server=/tmp/mpvsocket"
])


def handle_command(command):
    command = command.lower()
    if command.startswith("play "):
        song_name = command.replace("play ", "").strip()
        if song_name:
            url = get_from_youtube(song_name)
            play_song(url)
        else:
            print("No song name given.")
    elif "pause" in command:
        pause_song()
    elif "resume" in command:
        resume_song()
    elif "stop" in command:
        stop_song()
    else:
        print("Command not recognized.")





def requestSong():
    request = listen("Search For a song")
    if request:
        play_song(request)
    else:
        print("Say something to Search for a song")
        requestSong()



while True:
    if assistantName.strip().lower() in listen("call its name").strip().lower():
        is_name_called = True
    else:
        is_name_called = False
    print(is_name_called)
    if is_name_called:
        requestSong()
            
        

    





