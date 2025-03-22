from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.audio_service import transcribe_audio, generate_audio_segments
from app.services.video_service import extract_audio, overlay_audio_on_video, find_video_file
from app.services.translation_service import translate_text
from pathlib import Path
import os
import json


router = APIRouter()

@router.post("/upload")
async def upload_video(
    user: str = Form(...),
    video: UploadFile = File(...)
):
    if not user:
        raise HTTPException(status_code=400, detail="Numele utilizatorului este obligatoriu.")
    
    original_video_path = f"user_files/{user}/original"
    try:
        os.makedirs(original_video_path, exist_ok=True)
        os.chmod(original_video_path, 0o777)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la crearea directorului: {str(e)}")
    
    video_path = os.path.join(original_video_path, video.filename)
    with open(video_path, "wb") as buffer:
        buffer.write(await video.read()) 
    
    return {
        "message": "Video incarcat cu succes",
        "user_name": user,
        "file_name": video.filename,
        "file_path": video_path
    }

@router.post("/transcribe")
async def transcribe_video(
    user: str = Form(...)
):
    if not user:
        raise HTTPException(status_code=400, detail="Numele utilizatorului este obligatoriu.")
    
    
    user_dir = f"user_files/{user}"
    original_dir = os.path.join(user_dir, "original")
    transcriptions_dir = os.path.join(user_dir, "transcriptions")
    
    if not os.path.exists(original_dir):
        raise HTTPException(status_code=404, detail="Videoclipul original nu exista.")
    
    video_files = [f for f in os.listdir(original_dir) if f.endswith(".mp4") or f.endswith(".mkv")]
    if not video_files:
        raise HTTPException(status_code=404, detail="Nu a fost gasit niciun videoclip.")
    
    video_path = os.path.join(original_dir, video_files[0])
    audio_path = os.path.join(user_dir, "extracted_audio.wav")
    
    try:
        os.makedirs(transcriptions_dir, exist_ok=True)
        os.chmod(transcriptions_dir, 0o777) 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la crearea directorului pentru transcriptii: {str(e)}")
    
    # Extragere audio
    extract_audio(video_path, audio_path)
    
    # Generare transcriptie
    segments = transcribe_audio(audio_path)
    
    # Salvare transcriptie
    transcription_path = os.path.join(transcriptions_dir, "original_transcription.json")
    with open(transcription_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=4)
    
    return {"message": "Transcriptie generata cu succes.", "transcription_path": transcription_path}

@router.post("/translate")
async def translate_transcription(
    user: str = Form(...),
    target_lang: str = Form(...)
):
    if not user:
        raise HTTPException(status_code=400, detail="Numele utilizatorului este obligatoriu.")
    
    user_dir = f"user_files/{user}"
    transcriptions_dir = os.path.join(user_dir, "transcriptions")
    original_transcription_path = os.path.join(transcriptions_dir, "original_transcription.json")
    translated_transcription_path = os.path.join(transcriptions_dir, "translated_transcription.json")
    
    if not os.path.exists(original_transcription_path):
        raise HTTPException(status_code=404, detail="Fisierul de transcriptie original nu exista.")

    try:
        os.makedirs(transcriptions_dir, exist_ok=True)
        os.chmod(transcriptions_dir, 0o777)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la verificarea permisiunilor directorului: {str(e)}")
    
    with open(original_transcription_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
    
    translated_segments = []
    for segment in segments:
        translated_text = translate_text(segment["text"], target_lang)
        translated_segments.append({"start": segment["start"], "end": segment["end"], "text": translated_text})
    
    with open(translated_transcription_path, "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, ensure_ascii=False, indent=4)
    
    return {"message": "Transcriptie tradusa cu succes.", "translated_transcription_path": translated_transcription_path}

@router.post("/generate")
async def generate_video(
    user: str = Form(...),
    target_lang: str = Form(...),
):
    user_dir = Path(f"user_files/{user}")
    original_dir = user_dir / "original"
    translated_transcription_path = user_dir / "transcriptions" / "translated_transcription.json"
    segments_dir = user_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    final_video_path = user_dir / "final_video.mp4"
    generated_audio = segments_dir / "audio.wav"

    if not original_dir.exists():
        raise HTTPException(status_code=404, detail="Directorul original nu exista pentru acest utilizator.")
    
    # Cautare videoclip original
    video_path = find_video_file(original_dir)
    if not video_path:
        raise HTTPException(status_code=404, detail="Videoclipul original a fost sters.")
    
    # Verificare daca exista transcriptia
    if not translated_transcription_path.exists():
        raise HTTPException(status_code=404, detail="Transcriptia tradusa nu exista.")
    
    # Incarcare segmente text
    with open(translated_transcription_path, "r", encoding="utf-8") as f:
        translated_segments = json.load(f)

    await generate_audio_segments(translated_segments, video_path, target_lang, user)

    # Combinare segmente audio si suprapunere cu video
    try:
        overlay_audio_on_video(video_path, generated_audio, final_video_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la suprapunerea audio pe video: {str(e)}")
    
    return {
        "message": "Videoclipul a fost generat cu succes.",
        "final_video_path": str(final_video_path)
    }