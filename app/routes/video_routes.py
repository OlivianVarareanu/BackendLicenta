from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.security import HTTPBearer
from app.services.audio_service import transcribe_audio, generate_audio_segments
from app.services.video_service import extract_audio, overlay_audio_with_reduced_original, find_video_file
from app.services.translation_service import translate_text
from pathlib import Path
import os
import json
import jwt
from datetime import datetime, timedelta
import uuid

router = APIRouter()

# Configurare JWT
SECRET_KEY = "secret_random_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

security = HTTPBearer()
router = APIRouter()

@router.post("/upload")
async def upload_video(video: UploadFile = File(...)):
    # Generare ID
    upload_id = str(uuid.uuid4())
    
    # Setare data expirare token
    expiration = datetime.utcnow() + timedelta(days=7)

    payload = {
        "sub": upload_id,
        "exp": expiration
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    original_video_path = f"user_files/{upload_id}/original"
    try:
        os.makedirs(original_video_path, exist_ok=True)
        os.chmod(original_video_path, 0o777)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare la crearea directorului: {str(e)}")
    
    # Salvare fisier
    video_path = os.path.join(original_video_path, video.filename)
    with open(video_path, "wb") as buffer:
        buffer.write(await video.read()) 
    
    return {
        "message": "Video încărcat cu succes",
        "upload_token": token,
        "file_name": video.filename,
        "file_path": video_path
    }

@router.post("/transcribe")
async def transcribe_video(
    token: str = Form(...),
    original_lang: str | None = Form(None)
):
    try:
        # Decodificare token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        upload_id = payload.get("sub")
        
        if upload_id is None:
            raise HTTPException(status_code=401, detail="Token invalid")
            
        user_dir = f"user_files/{upload_id}"
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
        original_segments, detected_language = transcribe_audio(audio_path, original_lang)
        
        # Salvare transcriptie așa cum este generată, fără combinare
        transcription_path = os.path.join(transcriptions_dir, "original_transcription.json")
        with open(transcription_path, "w", encoding="utf-8") as f:
            json.dump(original_segments, f, ensure_ascii=False, indent=4)

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirat")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Token invalid")
    
    return {"message": "Transcriptie generata cu succes.", "transcription_path": transcription_path, "detected_language": detected_language}


@router.post("/translate")
async def translate_transcription(
    token: str = Form(...),
    target_lang: str = Form(...),
    original_lang: str = Form(...)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        upload_id = payload.get("sub")
        
        if upload_id is None:
            raise HTTPException(status_code=401, detail="Token invalid")

        user_dir = f"user_files/{upload_id}"
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
            translated_text = translate_text(segment["text"], target_lang,original_lang)
            translated_segments.append({"start": segment["start"], "end": segment["end"], "text": translated_text})
        
        with open(translated_transcription_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, ensure_ascii=False, indent=4)
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirat")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Token invalid")
    
    return {"message": "Transcriptie tradusa cu succes.", "translated_transcription_path": translated_transcription_path}

@router.post("/generate")
async def generate_video(
    token: str = Form(...),
    target_lang: str = Form(...),
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        upload_id = payload.get("sub")
        
        if upload_id is None:
            raise HTTPException(status_code=401, detail="Token invalid")

        user_dir = Path(f"user_files/{upload_id}")
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

        await generate_audio_segments(translated_segments, video_path, target_lang, upload_id)

        # Combinare segmente audio si suprapunere cu video folosind noua functie
        try:
            overlay_audio_with_reduced_original(
                str(video_path), 
                str(generated_audio), 
                str(final_video_path)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Eroare la suprapunerea audio pe video: {str(e)}")
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirat")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Token invalid")
    
    return {
        "message": "Videoclipul a fost generat cu succes.",
        "final_video_path": str(final_video_path)
    }