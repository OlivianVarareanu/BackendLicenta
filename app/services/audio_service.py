from pydub import AudioSegment
from app.services.video_service import get_video_duration
from app.services.translation_service import translate_text
from pydub.effects import speedup
import os
import edge_tts
import asyncio
import whisper
import torch
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

def transcribe_audio(audio_path, model_size="large-v2"):
    
    """
    Transcriere audio folosind librarie Whisper
    
    Args:
        audio_path (str): Calea catre fisierul audio.
        model_size (str): Modelul (default: "large-v2").
    
    Returns:
        list: O lista de segmente.
    """

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model(model_size, device=device)
    result = model.transcribe(audio_path)
    return result["segments"]

def calculate_initial_silence(audio_path, silence_threshold=-50, min_silence_len=500):

    audio = AudioSegment.from_file(audio_path)
    nonsilent_ranges = detect_nonsilent(audio, silence_thresh=silence_threshold, min_silence_len=min_silence_len)
 
    if not nonsilent_ranges:
        return 0

    first_nonsilent_start = nonsilent_ranges[0][0]

    initial_silence = first_nonsilent_start / 1000
    
    return initial_silence

async def generate_audio_segment(text, file_path, voice_name="de-DE-SeraphinaMultilingualNeural"):

    print(f"[DEBUG] Generare segment audio pentru textul: {text}")
    try:
        tts = edge_tts.Communicate(text, voice_name)
        await tts.save(file_path)
        print(f"[INFO] Segment generat: {file_path}")
    except Exception as e:
        print(f"[ERROR] Eroare la generarea segmentului audio: {e}")
        raise

async def generate_audio_segments(segments, video_path, target_lang, user_name):
 
    if not user_name:
        raise ValueError("Numele utilizatorului este obligatoriu.")

    combined_audio = AudioSegment.silent(duration=0)
    tasks = []
    segment_files = []
    
    video_duration = get_video_duration(video_path)
    first_segment_start_time = segments[0]["start"]
    print(f"[INFO] Decalajul de timp până la primul sunet: {first_segment_start_time:.2f} secunde.")

    segments_dir = f"user_files/{user_name}/segments"
    os.makedirs(segments_dir, exist_ok=True)

    for i, segment in enumerate(segments):
        start_time = segment["start"] - first_segment_start_time
        end_time = segment["end"] - first_segment_start_time
        text = segment["text"]
        translated_text = translate_text(text, target_lang)
        print(f"[TRANSLATED {i}] {translated_text} ({start_time}s - {end_time}s)")

        # Salvarea fisierului audio
        segment_audio_path = os.path.join(segments_dir, f"segment_{i}.mp3")
        tasks.append(generate_audio_segment(translated_text, segment_audio_path, "de-DE-FlorianMultilingualNeural"))
        segment_files.append((segment_audio_path, start_time, end_time))

    await asyncio.gather(*tasks)

    silence_at_start = first_segment_start_time * 1000
    if silence_at_start > 0:
        combined_audio += AudioSegment.silent(duration=silence_at_start)

    for i, (segment_path, start_time, end_time) in enumerate(segment_files):
        segment_audio = AudioSegment.from_mp3(segment_path)
        segment_duration = (end_time - start_time) * 1000
        if i < len(segment_files) - 1:
            next_start_time = segment_files[i + 1][1]
            total_available_duration = (next_start_time - start_time) * 1000
        else:
            total_available_duration = (video_duration - start_time) * 1000

        if segment_audio.duration_seconds * 1000 > total_available_duration:
            speed_factor = segment_audio.duration_seconds * 1000 / total_available_duration
            print(f"[INFO] Segmentul {i} este prea lung. Accelerăm cu factorul {speed_factor:.2f}x.")
            segment_audio = speedup(segment_audio, speed_factor)

        combined_audio += segment_audio

        if i < len(segment_files) - 1:
            next_start_time = segment_files[i + 1][1]
            silence_duration = (next_start_time - start_time) * 1000 - segment_audio.duration_seconds * 1000
            if silence_duration > 0:
                combined_audio += AudioSegment.silent(duration=silence_duration)

    last_segment_end_time = segment_files[-1][2]
    silence_at_end = (video_duration - last_segment_end_time) * 1000
    if silence_at_end > 0:
        combined_audio += AudioSegment.silent(duration=silence_at_end)

    # Salvare fisier audio
    final_audio_path = os.path.join(segments_dir, "audio.wav")
    combined_audio.export(final_audio_path, format="wav")
    print(f"[INFO] Fișier audio final generat: {final_audio_path}")