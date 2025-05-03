from pydub import AudioSegment
from app.services.video_service import get_video_duration
from app.services.translation_service import translate_text
import os
import edge_tts
import whisper
import subprocess
import torch
from pydub.silence import detect_nonsilent

def transcribe_audio(audio_path, model_size="large-v2"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model(model_size, device=device)
    result = model.transcribe(audio_path,word_timestamps=True,temperature=0.0,beam_size=5,best_of=3,condition_on_previous_text=True)
    return result["segments"]

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
        start_time = segment["start"] - first_segment_start_time
        end_time = segment["end"] - first_segment_start_time
        text = segment["text"]
        translated_text = translate_text(text, target_lang)
        print(f"[TRANSLATED {i}] {translated_text} ({start_time}s - {end_time}s)")
        
        translated_segments.append({
            "start": start_time,
            "end": end_time,
            "text": translated_text,
            "index": i
        })

    max_attempts = 3
    combined_audio = AudioSegment.silent(duration=0)
    
    silence_at_start = first_segment_start_time * 1000
    if silence_at_start > 0:
        combined_audio += AudioSegment.silent(duration=silence_at_start)
    
    for i, segment in enumerate(translated_segments):
        if i < len(translated_segments) - 1:
            next_start = translated_segments[i+1]["start"]
            available_duration = (next_start - segment["start"]) * 1000
        else:
            available_duration = (video_duration - segment["start"]) * 1000
            
        rate = "+0%"
        attempt = 0
        segment_file = None
        
        while attempt < max_attempts:
            segment_audio_path = os.path.join(segments_dir, f"segment_{segment['index']}_{attempt}.mp3")
            await generate_audio_segment(segment["text"], segment_audio_path, "de-DE-SeraphinaMultilingualNeural", rate=rate)  #ro-RO-EmilNeural , en-CA-ClaraNeural, ro-RO-AlinaNeural, de-DE-SeraphinaMultilingualNeural
           
            segment_audio = AudioSegment.from_mp3(segment_audio_path)
            actual_duration = segment_audio.duration_seconds * 1000
            
            duration_ratio = actual_duration / available_duration
            
            if 0.85 <= duration_ratio <= 1.1:
                segment_file = segment_audio_path
                break
            elif duration_ratio < 0.85:

                slow_percent = int((1 / duration_ratio - 1) * 100)

                slow_percent = min(slow_percent, 20)
                rate = f"-{slow_percent}%"
                print(f"[INFO] Segment {segment['index']} prea scurt. Incetinire cu procentajul: {rate}")
            else:

                speed_factor = duration_ratio
                speed_percent = int((speed_factor - 1) * 100) + 15
                rate = f"+{min(speed_percent, 85)}%"
                print(f"[INFO] Segment {segment['index']} prea lung. Accelerare cu rata: {rate}")
            
            print(f"[INFO] Ajustare segment {segment['index']}: durata actuală={actual_duration/1000:.2f}s, " 
                  f"disponibil={available_duration/1000:.2f}s, noua viteza={rate}")
            
            attempt += 1
        
        if segment_file:
            segment_audio = AudioSegment.from_mp3(segment_file)
            combined_audio += segment_audio
            
            if i < len(translated_segments) - 1:
                next_start_time = translated_segments[i+1]["start"] * 1000
                current_position = (segment["start"] * 1000) + segment_audio.duration_seconds * 1000
                silence_needed = next_start_time - current_position
                
                if silence_needed > 0:
                    combined_audio += AudioSegment.silent(duration=silence_needed)
                elif silence_needed < -100:  
                    print(f"[WARNING] Segment {segment['index']} depășește timpul disponibil cu {-silence_needed/1000:.2f}s")
        else:
            print(f"[WARNING] Nu s-a putut genera un segment potrivit pentru {segment['index']} după {max_attempts} încercări")
            last_attempt_path = os.path.join(segments_dir, f"segment_{segment['index']}_{max_attempts-1}.mp3")
            if os.path.exists(last_attempt_path):
                segment_audio = AudioSegment.from_mp3(last_attempt_path)
                combined_audio += segment_audio
                print(f"[INFO] S-a folosit ultima variantă disponibilă pentru segmentul {segment['index']}")
    
    silence_at_end = (video_duration - translated_segments[-1]["end"]) * 1000
    if silence_at_end > 0:
        combined_audio += AudioSegment.silent(duration=silence_at_end)

    final_audio_path = os.path.join(segments_dir, "audio.wav")
    combined_audio.export(final_audio_path, format="wav")
    print(f"[INFO] Fișier audio final generat: {final_audio_path}")
    
    return final_audio_path

def overlay_audio_with_reduced_original(original_video_path, generated_audio_path, final_video_path, original_volume_reduction=-20):
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