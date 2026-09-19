import os
import random
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
        f"Sos un copywriter comercial en Argentina para ElectroOrg. "
        f"Escribí una locución para un Reel publicitario de 15 segundos sobre este producto:\n"
        f"Producto: {title}\n"
        f"Precio: {price}\n\n"
        f"Reglas estrictas:\n"
        f"1. Usá español rioplatense sutil, vendedor y fluido.\n"
        f"2. Gancho en los primeros 3 segundos con una necesidad o problema cotidiano.\n"
        f"3. Resaltá 2 beneficios directos.\n"
        f"4. Cierre con llamada a la acción clara: 'Pedilo hoy con link en bio en ElectroOrg'.\n"
        f"5. Devolvé ÚNICAMENTE el texto que debe ser leído en voz alta, sin acotaciones ni emojis."
    )
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        data = response.json()
        if "candidates" in data and len(data["candidates"]) > 0:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Error con Gemini: {e}")
        
    return f"Buscás calidad y rendimiento? Mirá este {title}. Conseguilo hoy mismo con garantía y envío rápido ingresando al link de nuestra bio en ElectroOrg."

async def create_audio(text):
    communicate = edge_tts.Communicate(text, "es-AR-TomasNeural")
    await communicate.save("voice.mp3")

def download_image(url):
    r = requests.get(url, timeout=15)
    with open("product.jpg", "wb") as f:
        f.write(r.content)

def build_video():
    audio = AudioFileClip("voice.mp3")
    duration = audio.duration + 0.5
    
    clip = (
        ImageClip("product.jpg")
        .set_duration(duration)
        .resize(height=1920)
    )
    if clip.w < 1080:
        clip = clip.resize(width=1080)
    clip = clip.crop(x1=clip.w/2 - 540, y1=clip.h/2 - 960, width=1080, height=1920)
    clip = clip.set_audio(audio)
    
    clip.write_videofile("reel.mp4", fps=24, codec="libx264", audio_codec="aac")

def send_telegram(product, script):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    caption = (
        f"🔥 {product['title']}\n\n"
        f"{script}\n\n"
        f"👉 Compralo acá: {product['link']}\n\n"
        f"#ElectroOrg #Tecnologia #Ofertas"
    )
    print(f"Enviando a chat_id: '{TELEGRAM_CHAT_ID}'")
    with open("reel.mp4", "rb") as video:
        res = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"video": video},
            timeout=90
        )
        print("Respuesta de Telegram API:", res.status_code, res.text)
        if not res.ok:
            raise Exception(f"Fallo al enviar a Telegram: {res.text}")

if __name__ == "__main__":
    prod = get_product()
    print(f"Producto elegido: {prod['title']}")
    script = generate_script(prod)
    print(f"Guion listo: {script}")
    asyncio.run(create_audio(script))
    download_image(prod['image_link'])
    build_video()
    send_telegram(prod, script)
    print("¡Video enviado exitosamente a Telegram!")
