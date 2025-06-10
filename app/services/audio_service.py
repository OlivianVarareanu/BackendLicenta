from pydub import AudioSegment
from app.services.video_service import get_video_duration
import os
import edge_tts
import whisper
import subprocess
import torch


def transcribe_audio(audio_path, original_lang, model_size="medium"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model(model_size, device=device)
    if(original_lang):
        result = model.transcribe(
            audio_path,
            language=original_lang,
            word_timestamps=True,
            temperature=0.0,
            beam_size=5,
            condition_on_previous_text=False,
            compression_ratio_threshold=1.5,
            logprob_threshold=-1.0,
            no_speech_threshold=0.4
        )
    else:
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            temperature=0.0,
            beam_size=5,
            condition_on_previous_text=False,
            compression_ratio_threshold=1.5,
            logprob_threshold=-1.0,
            no_speech_threshold=0.4
        )

    detected_language = result['language']
    return result["segments"], detected_language

async def generate_audio_segment(text, file_path, voice_name, rate="+0%"):
    print(f"[DEBUG] Generare segment audio pentru textul: {text}")
    try:
        tts = edge_tts.Communicate(text, voice_name, rate=rate)
        await tts.save(file_path)
        print(f"[INFO] Segment generat: {file_path}")
        return file_path
    except Exception as e:
        print(f"[ERROR] Eroare la generarea segmentului audio: {e}")
        raise

async def generate_audio_segments(segments, video_path, target_lang, user_name):
    if not user_name:
        raise ValueError("Numele utilizatorului este obligatoriu.")

    video_duration = get_video_duration(video_path)
    first_segment_start_time = segments[0]["start"]

    segments_dir = f"user_files/{user_name}/segments"
    os.makedirs(segments_dir, exist_ok=True)

    translated_segments = []
    for i, segment in enumerate(segments):
        start_time = segment["start"]
        end_time = segment["end"]
        text = segment["text"]
        translated_segments.append({
            "start": start_time,
            "end": end_time,
            "text": text,
            "index": i
        })

    combined_audio = AudioSegment.silent(duration=0)

    silence_at_start = first_segment_start_time * 1000
    if silence_at_start > 0:
        combined_audio += AudioSegment.silent(duration=silence_at_start)

    current_time_position = silence_at_start

    for i, segment in enumerate(translated_segments):
        segment_start_ms = segment["start"] * 1000

        if segment_start_ms > current_time_position:
            silence_needed = segment_start_ms - current_time_position
            combined_audio += AudioSegment.silent(duration=silence_needed)
            current_time_position = segment_start_ms

        if i < len(translated_segments) - 1:
            next_start = translated_segments[i + 1]["start"]
            available_duration = (next_start - segment["start"]) * 1000
        else:
            available_duration = (video_duration - segment["start"]) * 1000

        segment_audio_path = os.path.join(segments_dir, f"segment_{segment['index']}_base.mp3")
        await generate_audio_segment(segment["text"], segment_audio_path, "de-DE-SeraphinaMultilingualNeural", rate="+0%") #ro-RO-EmilNeural , ro-RO-AlinaNeural, en-US-RogerNeural , de-DE-SeraphinaMultilingualNeural
        segment_audio = AudioSegment.from_mp3(segment_audio_path)
        actual_duration = segment_audio.duration_seconds * 1000

        duration_ratio = actual_duration / available_duration

        if duration_ratio > 1.01:
            adjustment_percent = round((duration_ratio - 1) * 100)
            rate = f"+{min(adjustment_percent, 99)}%"
            print(f"[INFO] Segment {segment['index']} prea lung: {actual_duration:.0f}ms > {available_duration:.0f}ms → {rate}")

            segment_audio_path = os.path.join(segments_dir, f"segment_{segment['index']}_adjusted.mp3")
            await generate_audio_segment(segment["text"], segment_audio_path, "de-DE-SeraphinaMultilingualNeural", rate=rate)
            segment_audio = AudioSegment.from_mp3(segment_audio_path)
        else:
            print(f"[INFO] Segment {segment['index']} OK  {actual_duration:.0f}ms ≤ {available_duration:.0f}ms.")

        combined_audio += segment_audio
        start_debug = current_time_position
        end_debug = start_debug + segment_audio.duration_seconds * 1000
        print(f"[DEBUG] Segment {segment['index']} → start={start_debug:.0f}ms, end={end_debug:.0f}ms")
        current_time_position = end_debug

    total_duration_ms = video_duration * 1000
    if current_time_position < total_duration_ms:
        silence_at_end = total_duration_ms - current_time_position
        combined_audio += AudioSegment.silent(duration=silence_at_end)

    final_audio_path = os.path.join(segments_dir, "audio.wav")
    combined_audio.export(final_audio_path, format="wav")
    print(f"[INFO] Fișier audio final generat: {final_audio_path}")

    return final_audio_path



def overlay_audio_with_reduced_original(original_video_path, generated_audio_path, final_video_path, original_volume_reduction=-14):
    """
    Overlay generated audio on original video while reducing original audio volume
    
    :param original_video_path: Path to the original video file
    :param generated_audio_path: Path to the newly generated audio file
    :param final_video_path: Path where the final video will be saved
    :param original_volume_reduction: Decibel reduction for original audio (negative value)
    """

    original_audio_path = os.path.join(os.path.dirname(original_video_path), "original_audio.wav")
    
    extract_audio_command = [
        "ffmpeg", 
        "-i", original_video_path, 
        "-vn",  
        "-acodec", "pcm_s16le", 
        "-ar", "44100",  
        "-ac", "2",  
        original_audio_path
    ]
    
    try:
        subprocess.run(extract_audio_command, check=True)
        
        original_audio = AudioSegment.from_wav(original_audio_path)
        generated_audio = AudioSegment.from_wav(generated_audio_path)
        
        reduced_original_audio = original_audio + original_volume_reduction
        
        max_length = max(len(reduced_original_audio), len(generated_audio))
        reduced_original_audio = reduced_original_audio.append(
            AudioSegment.silent(duration=max_length - len(reduced_original_audio)), 
            crossfade=0
        )
        generated_audio = generated_audio.append(
            AudioSegment.silent(duration=max_length - len(generated_audio)), 
            crossfade=0
        )
        
        mixed_audio = reduced_original_audio.overlay(generated_audio)
        
        temp_audio_path = os.path.join(os.path.dirname(final_video_path), "mixed_audio.wav")
        mixed_audio.export(temp_audio_path, format="wav")
        
        ffmpeg_command = [
            "ffmpeg", 
            "-i", original_video_path,
            "-i", temp_audio_path,
            "-c:v", "copy", 
            "-c:a", "aac", 
            "-map", "0:v:0", 
            "-map", "1:a:0", 
            "-shortest", 
            final_video_path
        ]
        
        subprocess.run(ffmpeg_command, check=True)
        
        # Clean up temporary files
        os.remove(original_audio_path)
        os.remove(temp_audio_path)
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] FFmpeg command failed: {e}")
        raise
    except Exception as e:
        print(f"[ERROR] Audio mixing failed: {e}")
        raise