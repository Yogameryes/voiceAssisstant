import sys
import socket
import json
import subprocess
import yt_dlp
import speech_recognition as sr
import time
import numpy as np
import math
import queue

from PyQt5 import QtWidgets, QtGui, QtCore
import sounddevice as sd
from yt_dlp.utils import DownloadError

assistantName = "birju"
process_playing = None
mpv_socket_path = "/tmp/mpvsocket"

audio_queue = queue.Queue()

class AudioLevelReader(QtCore.QObject):
    level_updated = QtCore.pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.stream = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self.stream = sd.InputStream(channels=1, callback=self.audio_callback, blocksize=1024, samplerate=44100)
        self.stream.start()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.emit_level)
        self.timer.start(30)

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if hasattr(self, "timer"):
            self.timer.stop()

    def audio_callback(self, indata, frames, time_, status):
        if status:
            print(status)
        amplitude = np.linalg.norm(indata) / frames
        audio_queue.put(amplitude)

    def emit_level(self):
        level = 0
        while not audio_queue.empty():
            level = audio_queue.get()
        scaled = min(level * 30, 1.0)
        self.level_updated.emit(scaled)

class SpeechRecognizer(QtCore.QThread):
    recognized = QtCore.pyqtSignal(str)
    prompt = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.r = sr.Recognizer()
        self.mic = sr.Microphone()
        self._running = True
        self._mode = "wake_word"

    def run(self):
        while self._running:
            try:
                with self.mic as source:
                    self.prompt.emit(f"Listening ({self._mode})...")
                    audio = self.r.listen(source, timeout=5, phrase_time_limit=5)
                text = self.r.recognize_google(audio).lower()
                print(f"Recognized: {text}")
                self.recognized.emit(text)
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                print("Could not understand audio")
                continue
            except sr.RequestError as e:
                print(f"Speech Recognition error: {e}")
                continue

    def stop(self):
        self._running = False
        self.quit()
        self.wait()

    def set_mode(self, mode):
        self._mode = mode

class SiriBallOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.resize(300, 300)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self.phase = 0
        self.audio_level = 0

        self.anim = QtCore.QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setEasingCurve(QtCore.QEasingCurve.OutQuad)
        self.anim.finished.connect(self.on_animation_finished)

        screen_geom = QtWidgets.QApplication.primaryScreen().geometry()
        self.screen_width = screen_geom.width()
        self.screen_height = screen_geom.height()

        self.visible_x = (self.screen_width - self.width()) // 2
        self.visible_y = self.screen_height - self.height() - 100

        self.hidden_y = self.screen_height + 50

        self.move(self.visible_x, self.hidden_y)
        self.hide()

        self.is_visible = False

    def slide_up(self):
        if not self.is_visible:
            self.show()
            self.anim.stop()
            self.anim.setStartValue(QtCore.QPoint(self.visible_x, self.hidden_y))
            self.anim.setEndValue(QtCore.QPoint(self.visible_x, self.visible_y))
            self.anim.start()
            self.is_visible = True

    def slide_down(self):
        if self.is_visible:
            self.anim.stop()
            self.anim.setStartValue(QtCore.QPoint(self.visible_x, self.visible_y))
            self.anim.setEndValue(QtCore.QPoint(self.visible_x, self.hidden_y))
            self.anim.start()
            self.is_visible = False

    def on_animation_finished(self):
        if not self.is_visible:
            self.hide()

    def set_audio_level(self, level):
        self.audio_level = level
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        center = self.rect().center()

        base_radius = 60
        max_scale = 40
        pulse = (0.5 + self.audio_level / 2)
        self.phase += 0.15
        radius = base_radius + max_scale * math.sin(self.phase) * pulse

        gradient = QtGui.QRadialGradient(center, radius)
        gradient.setColorAt(0, QtGui.QColor(0, 170, 255, 220))
        gradient.setColorAt(0.6, QtGui.QColor(0, 170, 255, 80))
        gradient.setColorAt(1, QtGui.QColor(0, 170, 255, 0))

        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(center, int(radius), int(radius))

        core_radius = int(radius * 0.5)
        core_color = QtGui.QColor(0, 170, 255, 255)
        painter.setBrush(core_color)
        painter.drawEllipse(center, core_radius, core_radius)

def get_from_youtube(query):
    print(f"🎵 Searching YouTube for: {query}")
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'default_search': 'ytsearch1',
        'format': 'bestaudio/best[ext=m4a]/bestaudio/best'
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info and info['entries']:
                video = info['entries'][0]
            else:
                video = info
            return video['url']
    except DownloadError as e:
        print(f"❌ Could not fetch audio: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")
        return None

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
    command = command.lower().strip()
    if command.startswith("play"):
        song_name = command[4:].strip()
        if song_name:
            url = get_from_youtube(song_name)
            if url:
                start_playing(url)
                return True
            else:
                print("❌ Could not play that song.")
                return False
        else:
            print("Please say the song name after 'play'.")
            return False
    elif "pause" in command:
        pause_song()
        return True
    elif "resume" in command:
        resume_song()
        return True
    elif "stop" in command:
        stop_song()
        return True
    else:
        print("Command not recognized.")
        return False

class CommandWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(bool)

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        result = handle_command(self.command)
        self.finished.emit(result)

class AssistantApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.overlay = SiriBallOverlay()

        self.audio_reader = AudioLevelReader()
        self.audio_reader.level_updated.connect(self.overlay.set_audio_level)
        self.audio_reader.start()

        self.sr_thread = SpeechRecognizer()
        self.sr_thread.recognized.connect(self.on_recognized)
        self.sr_thread.prompt.connect(self.on_prompt)
        self.mode = "wake_word"
        self.sr_thread.set_mode(self.mode)
        self.sr_thread.start()

        self.command_worker = None

        print("Assistant started. Say the wake word to begin.")

    def on_prompt(self, msg):
        print(msg)

    def on_recognized(self, text):
        print(f"Received text: {text}")
        if self.mode == "wake_word":
            if assistantName in text:
                print("Wake word detected!")
                self.overlay.slide_up()
                self.mode = "command"
                self.sr_thread.set_mode(self.mode)
        elif self.mode == "command":
            if self.command_worker is None:
                self.command_worker = CommandWorker(text)
                self.command_worker.finished.connect(self.on_command_finished)
                self.command_worker.start()

    def on_command_finished(self, handled):
        if handled:
            self.overlay.slide_down()
            self.mode = "wake_word"
            self.sr_thread.set_mode(self.mode)
        else:
            print("Incomplete or unrecognized command, please try again.")
            # Keep overlay visible for retry
        self.command_worker = None

    def closeEvent(self, event):
        self.sr_thread.stop()
        self.audio_reader.stop()
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    assistant = AssistantApp()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
