import sys
import socket
import json
import subprocess
import yt_dlp
import speech_recognition as sr
import time
import sounddevice as sd
import numpy as np
import math
from PyQt5 import QtWidgets, QtGui, QtCore

assistantName = "cosmo"
process_playing = None
mpv_socket_path = "/tmp/mpvsocket"

#speech recognition
r = sr.Recognizer()
mic = sr.Microphone()

# --- PyQt5 Overlay Window ---
class SiriBallOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.resize(300, 300)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool  # So it doesn't appear in taskbar
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.phase = 0
        self.audio_level = 0

        # Timer to update animation
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(30)  # ~33 FPS

    def update_animation(self):
        self.phase += 0.15
        self.audio_level = self.get_audio_level()
        self.update()

    def get_audio_level(self):
        duration = 0.05  # 50 ms audio snippet
        fs = 44100
        try:
            recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, blocking=True)
            amplitude = np.linalg.norm(recording) / len(recording)
            level = min(amplitude * 50, 1.0)
            return level
        except Exception:
            # If mic error, just return 0
            return 0

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        center = self.rect().center()
        base_radius = 60
        max_scale = 40

        # Radius pulses with sine wave and mic volume
        radius = base_radius + max_scale * math.sin(self.phase) * (0.5 + self.audio_level / 2)

        gradient = QtGui.QRadialGradient(center, radius)
        gradient.setColorAt(0, QtGui.QColor(0, 170, 255, 180))
        gradient.setColorAt(1, QtGui.QColor(0, 170, 255, 0))

        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(center, int(radius), int(radius))


# --- Your original assistant functions ---

def listen(prompt=""):
    with mic as source:
        if prompt:
            print(prompt)
        audio = r.listen(source)
        print("Processing...")
        try:
            said = r.recognize_google(audio)
            print(f"Recognized: {said}")
            return said.lower()
        except sr.UnknownValueError:
            print("Could not understand audio")
            return ""
        except sr.RequestError as e:
            print(f"Speech Recognition error: {e}")
            return ""


def get_from_youtube(query):
    print(f"🎵 Searching YouTube for: {query}")
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'default_search': 'ytsearch1',
        'format': 'bestaudio/best'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info and info['entries']:
            video = info['entries'][0]
        else:
            video = info
        return video['url']


def start_playing(url):
    global process_playing
    if process_playing:
        try:
            process_playing.terminate()
            process_playing.wait(timeout=3)
        except Exception:
            pass
    print(f"Starting playback: {url}")
    process_playing = subprocess.Popen([
        "mpv", url,
        "--no-video",
        "--quiet",
        f"--input-ipc-server={mpv_socket_path}"
    ])


def send_mpv_command(command_dict):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(mpv_socket_path)
        command_json = json.dumps(command_dict).encode('utf-8')
        client.send(command_json + b'\n')
        client.close()
    except Exception as e:
        print("Could not send command to mpv:", e)


def pause_song():
    print("Pausing song")
    send_mpv_command({"command": ["set_property", "pause", True]})


def resume_song():
    print("Resuming song")
    send_mpv_command({"command": ["set_property", "pause", False]})


def stop_song():
    global process_playing
    print("Stopping song")
    if process_playing:
        try:
            process_playing.terminate()
            process_playing.wait(timeout=3)
            process_playing = None
        except Exception:
            pass


def handle_command(command):
    command = command.lower()
    if command.startswith("play "):
        song_name = command.replace("play ", "").strip()
        if song_name:
            url = get_from_youtube(song_name)
            start_playing(url)
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



def commandPhase():
        app = QtWidgets.QApplication(sys.argv)
        overlay = SiriBallOverlay()
        command = listen("Say a command (play, pause, resume, stop):")

        if "play" in command or "pause" in command or "resume" in command or "stop" in command:
                handle_command(command)
                overlay.hide()
        else:
                print("Did not catch any command.")
                commandPhase()

# --- Main logic integrating the PyQt overlay with your assistant ---

def main():
    app = QtWidgets.QApplication(sys.argv)
    overlay = SiriBallOverlay()
    overlay.hide()  # start hidden

    print("Assistant started. Say the wake word to begin.")
    while True:
        said = listen("Say wake word:")
        if assistantName in said:
            print("Wake word detected!")
            # Show overlay and keep it visible while listening for command
            overlay.show()
            # Process Qt events to show window immediately
            app.processEvents()


            commandPhase()

            
        time.sleep(0.5)  # Slight delay to avoid tight loop


if __name__ == "__main__":
    main()
