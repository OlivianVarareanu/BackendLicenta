from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from app.services.audio_service import transcribe_audio, generate_audio_segments
from app.services.video_service import extract_audio, overlay_audio_with_reduced_original, find_video_file
from app.services.translation_service import translate_text
from pathlib import Path
import os
import json
import uuid

router = APIRouter()

@router.post("/upload")
async def upload_video(video: UploadFile = File(...)):
    upload_id = str(uuid.uuid4())

    original_video_path = f"user_files/{upload_id}/original"
    try:
        os.makedirs(original_video_path, exist_ok=True)
        os.chmod(original_video_path, 0o777)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la crearea directorului: {str(e)}")
    
    video_path = os.path.join(original_video_path, video.filename)
    with open(video_path, "wb") as buffer:
        buffer.write(await video.read()) 
    
    return {
        "message": "succes",
        "upload_id": upload_id,
        "file_name": video.filename,
        "file_path": video_path
    }

@router.post("/transcribe/{upload_id}")
async def transcribe_video(upload_id: str, original_lang: str | None = Form(None)):
    user_dir = f"user_files/{upload_id}"
    original_dir = os.path.join(user_dir, "original")
    transcriptions_dir = os.path.join(user_dir, "transcriptions")
    
    if not os.path.exists(original_dir):
        raise HTTPException(status_code=404, detail="Videoclipul original nu exista.")
    
    video_files = [f for f in os.listdir(original_dir) if f.endswith((".mp4", ".mkv",".mov"))]
    if not video_files:
        raise HTTPException(status_code=404, detail="Nu a fost gasit niciun videoclip.")
    
    video_path = os.path.join(original_dir, video_files[0])
    audio_path = os.path.join(user_dir, "extracted_audio.wav")
    
    os.makedirs(transcriptions_dir, exist_ok=True)
    os.chmod(transcriptions_dir, 0o777)

    extract_audio(video_path, audio_path)
    original_segments, detected_language = transcribe_audio(audio_path, original_lang)
    
    transcription_path = os.path.join(transcriptions_dir, "original_transcription.json")
    with open(transcription_path, "w", encoding="utf-8") as f:
        json.dump(original_segments, f, ensure_ascii=False, indent=4)
    
    return {"message": "succes.", "transcription_path": transcription_path, "detected_language": detected_language}


@router.post("/translate/{upload_id}")
async def translate_transcription(upload_id: str, target_lang: str = Form(...), original_lang: str = Form(...)):
    user_dir = f"user_files/{upload_id}"
    transcriptions_dir = os.path.join(user_dir, "transcriptions")
    original_transcription_path = os.path.join(transcriptions_dir, "original_transcription.json")
    translated_transcription_path = os.path.join(transcriptions_dir, "translated_transcription.json")
    
    if not os.path.exists(original_transcription_path):
        raise HTTPException(status_code=404, detail="Fisierul de transcriptie original nu exista.")

    os.makedirs(transcriptions_dir, exist_ok=True)
    os.chmod(transcriptions_dir, 0o777)

    with open(original_transcription_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    translated_segments = [
        {
            "start": segment["start"],
            "end": segment["end"],
            "text": translate_text(segment["text"], target_lang, original_lang)
        }
        for segment in segments
    ]

    with open(translated_transcription_path, "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, ensure_ascii=False, indent=4)

    return {"message": "succes", "translated_transcription_path": translated_transcription_path}


@router.post("/generate/{upload_id}")
async def generate_video(upload_id: str, target_lang: str = Form(...), voice_id: str = Form(...)):
    user_dir = Path(f"user_files/{upload_id}")
    original_dir = user_dir / "original"
    translated_transcription_path = user_dir / "transcriptions" / "translated_transcription.json"
    segments_dir = user_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    final_video_path = user_dir / "final_video.mp4"
    generated_audio = segments_dir / "audio.wav"

    if not original_dir.exists():
        raise HTTPException(status_code=404, detail="Directorul original nu exista pentru acest utilizator.")
    
    video_path = find_video_file(original_dir)
    if not video_path:
        raise HTTPException(status_code=404, detail="Videoclipul original a fost sters.")

    if not translated_transcription_path.exists():
        raise HTTPException(status_code=404, detail="Transcriptia tradusa nu exista.")
    
    with open(translated_transcription_path, "r", encoding="utf-8") as f:
        translated_segments = json.load(f)

    await generate_audio_segments(translated_segments, video_path, target_lang, upload_id, voice_id)

    try:
        overlay_audio_with_reduced_original(
            str(video_path), 
            str(generated_audio), 
            str(final_video_path)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la suprapunerea audio pe video: {str(e)}")

    return {
        "message": "succes",
        "final_video_path": str(final_video_path)
    }

@router.get("/download/{upload_id}")
async def download_final_video(upload_id: str):
    final_video_path = Path(f"user_files/{upload_id}/final_video.mp4")
    if not final_video_path.exists():
        raise HTTPException(status_code=404, detail="Fișierul video final nu a fost găsit.")
    
    return FileResponse(
        path=str(final_video_path),
        media_type="video/mp4",
        filename="final_video.mp4"
    )
