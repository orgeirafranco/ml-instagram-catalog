import os
import random
import re
import requests
import pandas as pd
import asyncio
import edge_tts
import webvtt
from moviepy.editor import (
    ImageClip, 
    AudioFileClip, 
    TextClip, 
    CompositeVideoClip
)

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
        f"Reglas estrictas de duración y estilo:\n"
        f"1. LONGITUD: Máximo entre 24 y 28 palabras en total (para que la locución dure exactamente 10 segundos).\n"
        f"2. TONO: Español rioplatense vendedor, directo, sin relleno.\n"
        f"3. ESTRUCTURA: 3 segundos de gancho con necesidad + 4 segundos de beneficio + 3 segundos cierre: 'Pedilo en link de bio en ElectroOrg'.\n"
        f"4. Salida: Devolvé ÚNICAMENTE el texto para ser leído, sin comillas, sin emojis ni notas."
    )
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        data = response.json()
        if "candidates" in data and len(data["candidates"]) > 0:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Limpiamos saltos de línea molestos
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
                submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])

    with open("subtitles.vtt", "w", encoding="utf-8") as file:
        file.write(submaker.generate_subs())

def download_image(url):
    r = requests.get(url, timeout=15)
    with open("product.jpg", "wb") as f:
        f.write(r.content)

def time_to_seconds(time_str):
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])

def build_video():
    audio = AudioFileClip("voice.mp3")
    total_duration = audio.duration + 0.3
    
    # 1. Base del Video (Fondo 9:16 vertical 1080x1920)
    base_img = (
        ImageClip("product.jpg")
        .set_duration(total_duration)
        .resize(height=1920)
    )
    if base_img.w < 1080:
        base_img = base_img.resize(width=1080)
    base_img = base_img.crop(x1=base_img.w/2 - 540, y1=base_img.h/2 - 960, width=1080, height=1920)

    clips = [base_img]

    # 2. Generación de Subtítulos sincronizados palabra/frase
    vtt_file = "subtitles.vtt"
    if os.path.exists(vtt_file):
        subs = webvtt.read(vtt_file)
        for sub in subs:
            start = time_to_seconds(sub.start)
            end = time_to_seconds(sub.end)
            duration = max(end - start, 0.2)
            
            # Limpiar texto del subtítulo
            clean_text = sub.text.strip().upper()
            if not clean_text:
                continue

            # Subtítulo estilo TikTok: Letra grande, borde negro de alto contraste, centrada abajo
            txt_clip = (
                TextClip(
                    clean_text,
                    fontsize=68,
                    font="Liberation-Sans-Bold",
                    color="#FFE500",      # Amarillo llamativo de alto engagement
                    stroke_color="black", # Borde negro para que se lea perfecto sobre cualquier fondo
                    stroke_width=4,
                    method="caption",
                    size=(920, None)
                )
                .set_start(start)
                .set_duration(duration)
                .set_position(('center', 1420)) # Posición ergonómica para Reels/TikTok (sobre la interfaz)
            )
            clips.append(txt_clip)

    video = CompositeVideoClip(clips, size=(1080, 1920)).set_audio(audio)
    video.write_videofile("reel.mp4", fps=24, codec="libx264", audio_codec="aac")

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
    print("¡Reel con subtítulos dinámicos enviado a Telegram!")
