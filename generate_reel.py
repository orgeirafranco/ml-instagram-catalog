import os
import random
import subprocess
import requests
import pandas as pd
import asyncio
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip

GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

def get_product():
    df = pd.read_csv("meta_catalog.csv")
    valid_products = df.dropna(subset=['title', 'image_link', 'link']).to_dict('records')
    return random.choice(valid_products)

def generate_script(product):
    title = product['title']
    price = product.get('price', '')
    
    prompt = (
        f"Sos un copywriter experto en anuncios de TikTok y Reels para ElectroOrg (Argentina). "
        f"Escribí un guion comercial EXACTO de 10 segundos para este producto:\n"
        f"Producto: {title}\n"
        f"Precio: {price}\n\n"
        f"Reglas estrictas:\n"
        f"1. LONGITUD: Entre 22 y 26 palabras (locución de 10 segundos exactos).\n"
        f"2. TONO: Rioplatense vendedor, directo, atrapante.\n"
        f"3. ESTRUCTURA: Gancho inicial + beneficio clave + llamado: 'Pedilo hoy con link en bio en ElectroOrg'.\n"
        f"4. Salida: Devolvé ÚNICAMENTE el texto que debe ser leído en voz alta, sin comillas ni emojis."
    )
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        data = response.json()
        if "candidates" in data and len(data["candidates"]) > 0:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return " ".join(text.split())
    except Exception as e:
        print(f"Error con Gemini: {e}")
        
    return f"Buscás calidad al mejor precio? Conocé este {title}. Conseguilo hoy con garantía en el link de nuestra bio en ElectroOrg."

async def create_audio_and_subtitles(text):
    communicate = edge_tts.Communicate(text, "es-AR-TomasNeural")
    submaker = edge_tts.SubMaker()
    
    with open("voice.mp3", "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    # Exportamos el archivo SRT corregido
    srt_content = submaker.get_srt()
    with open("subtitles.srt", "w", encoding="utf-8") as file:
        file.write(srt_content)

def download_image(url):
    r = requests.get(url, timeout=15)
    with open("product.jpg", "wb") as f:
        f.write(r.content)

def build_video():
    audio = AudioFileClip("voice.mp3")
    duration = audio.duration + 0.3
    
    # 1. Base vertical 1080x1920 en MoviePy
    clip = (
        ImageClip("product.jpg")
        .set_duration(duration)
        .resize(height=1920)
    )
    if clip.w < 1080:
        clip = clip.resize(width=1080)
    clip = clip.crop(x1=clip.w/2 - 540, y1=clip.h/2 - 960, width=1080, height=1920)
    clip = clip.set_audio(audio)
    clip.write_videofile("temp_raw.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 2. Incrustar subtítulos con estilo profesional mediante FFmpeg (amarillo llamativo, borde negro, centrado)
    # Alignment=2 (abajo centrado), MarginV=280 (sobre la interfaz de TikTok/Reels), PrimaryColour=&H0000FFFF (Amarillo)
    sub_style = (
        "subtitles=subtitles.srt:force_style='"
        "FontName=Liberation Sans,"
        "FontSize=22,"
        "Bold=1,"
        "PrimaryColour=&H0000FFFF,"
        "OutlineColour=&H00000000,"
        "Outline=3,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=260'"
    )
    
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", "temp_raw.mp4",
        "-vf", sub_style,
        "-c:a", "copy",
        "reel.mp4"
    ]
    
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("Aviso FFmpeg subtítulos:", res.stderr)
        # Respaldo: si FFmpeg no pudo agregar subtítulos, usa el video base
        if not os.path.exists("reel.mp4"):
            os.rename("temp_raw.mp4", "reel.mp4")

def send_telegram(product, script):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    caption = (
        f"🔥 {product['title']}\n\n"
        f"{script}\n\n"
        f"👉 Compralo acá: {product['link']}\n\n"
        f"#ElectroOrg #Tecnologia #Ofertas"
    )
    with open("reel.mp4", "rb") as video:
        res = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"video": video},
            timeout=120
        )
        if not res.ok:
            raise Exception(f"Fallo al enviar a Telegram: {res.text}")

if __name__ == "__main__":
    prod = get_product()
    print(f"Producto elegido: {prod['title']}")
    script = generate_script(prod)
    print(f"Guion (10s): {script}")
    asyncio.run(create_audio_and_subtitles(script))
    download_image(prod['image_link'])
    build_video()
    send_telegram(prod, script)
    print("¡Reel de 10s con subtítulos profesionales enviado a Telegram!")
