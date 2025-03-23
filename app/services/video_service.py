import subprocess
import os
from pydub import AudioSegment
from pydub.effects import speedup
from pathlib import Path
import re

def extract_audio(video_path, audio_path):

    video_path_str = os.path.normpath(video_path)
    audio_path_str = os.path.normpath(audio_path)
    command = f"ffmpeg -i \"{video_path_str}\" -ac 1 -ar 16000 -vn \"{audio_path_str}\" -y"
    subprocess.run(command, shell=True, check=True)

def get_video_duration(video_path):
    command = f"ffmpeg -i \"{video_path}\" 2>&1 | findstr Duration"
    result = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    duration_str = result.stdout.split("Duration:")[1].split(",")[0].strip()
    h, m, s = map(float, duration_str.split(":"))
    total_seconds = h * 3600 + m * 60 + s
    return total_seconds


def overlay_audio_on_video(video_path, audio_path, output_path):

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Fișierul video {video_path} nu există.")
    if not audio_path.exists():
        raise FileNotFoundError(f"Fișierul audio {audio_path} nu există.")

    video_path_str = os.path.normpath(video_path)
    audio_path_str = os.path.normpath(audio_path)
    output_path_str = os.path.normpath(output_path)

    command = [
        "ffmpeg",
        "-i", video_path_str,
        "-i", audio_path_str,
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path_str,
        "-y"
    ]

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Eroare la suprapunerea audio pe video: {str(e)}")

def find_video_file(directory):

    directory = Path(directory)
    for file in directory.iterdir():
        if file.is_file() and file.suffix.lower() in (".mp4", ".mkv"):
            return os.path.normpath(file) 
    return None