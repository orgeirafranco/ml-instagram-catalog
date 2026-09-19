import os
import json
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
HISTORY_FILE = "price_history.json"

def clean_price(val):
    try:
        s = str(val).replace("$", "").replace(".", "").replace(",", ".").strip()
        parts = s.split()
        return float(parts[0])
    except Exception:
        return 0.0

def check_for_discounts():
    if not os.path.exists("meta_catalog.csv"):
        print("No existe meta_catalog.csv")
        return []

    df = pd.read_csv("meta_catalog.csv")
    valid = df.dropna(subset=['id', 'title', 'price', 'image_link', 'link']).to_dict('records')

    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    discounted = []
    updated_history = dict(history)

    for item in valid:
        pid = str(item['id'])
        current_p = clean_price(item['price'])
        if current_p <= 0:
            continue

        if pid in history:
            old_p = float(history[pid])
            if current_p < old_p:
                diff_pct = round(((old_p - current_p) / old_p) * 100)
                discounted.append({
                    "product": item,
                    "old_price": old_p,
                    "new_price": current_p,
                    "diff_pct": diff_pct
                })
        # Guardamos el precio actual para la próxima comparación
        updated_history[pid] = current_p

    # Si es la primera vez que corre y no hay historial previo, armamos un demo con un producto random
    if not history and valid:
        sample = random.choice(valid)
        curr = clean_price(sample['price'])
        discounted.append({
            "product": sample,
            "old_price": curr * 1.15,
            "new_price": curr,
            "diff_pct": 15
        })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_history, f, indent=2)

    return discounted

def generate_deal_script(item_data):
    prod = item_data["product"]
    pct = item_data["diff_pct"]
    price = prod.get("price", "")

    prompt = (
        f"Sos un copywriter experto en ofertas relámpago de ElectroOrg en Argentina. "
        f"Escribí un guion comercial EXACTO de 10 segundos para anunciar una baja de precio:\n"
        f"Producto: {prod['title']}\n"
        f"Descuento: {pct}% OFF\n"
        f"Precio actual: {price}\n\n"
        f"Reglas estrictas:\n"
        f"1. LONGITUD: Entre 22 y 26 palabras (locución de 10 segundos clavados).\n"
        f"2. TONO: Urgencia, entusiasmo vendedor rioplatense ('Mirá esta locura', 'Atención').\n"
        f"3. ESTRUCTURA: Alerta de oferta + beneficio clave del producto + cierre 'Link en bio antes de que vuele'.\n"
        f"4. Devolvé ÚNICAMENTE el texto que debe ser leído en voz alta, sin comillas ni emojis."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        if "candidates" in res and len(res["candidates"]) > 0:
            text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
            return " ".join(text.split())
    except Exception as e:
        print(f"Error con Gemini: {e}")

    return f"Atención! Bajó de precio este {prod['title']} con un descuento imperdible. Aprovechalo hoy mismo ingresando al link de nuestra bio en ElectroOrg."

async def create_audio_and_subtitles(text):
    communicate = edge_tts.Communicate(text, "es-AR-TomasNeural")
    submaker = edge_tts.SubMaker()

    with open("voice.mp3", "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    with open("subtitles.srt", "w", encoding="utf-8") as file:
        file.write(submaker.get_srt())

def download_image(url):
    r = requests.get(url, timeout=15)
    with open("product.jpg", "wb") as f:
        f.write(r.content)

def build_video():
    audio = AudioFileClip("voice.mp3")
    duration = audio.duration + 0.3

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

    # Subtítulos en rojo/naranja llamativo (&H0000A5FF) de oferta con borde negro
    sub_style = (
        "subtitles=subtitles.srt:force_style='"
        "FontName=Liberation Sans,"
        "FontSize=22,"
        "Bold=1,"
        "PrimaryColour=&H0000A5FF,"
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
        "deal_reel.mp4"
    ]

    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists("deal_reel.mp4"):
        os.rename("temp_raw.mp4", "deal_reel.mp4")

def send_telegram(item_data, script):
    prod = item_data["product"]
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    caption = (
        f"⚡ *¡OFERTA RELÁMPAGO DETECTADA!* ⚡\n\n"
        f"🔥 *{prod['title']}*\n"
        f"💰 *Precio con {item_data['diff_pct']}% OFF:* {prod.get('price', '')}\n\n"
        f"{script}\n\n"
        f"👉 Link directo de compra: {prod['link']}\n\n"
        f"#ElectroOrg #OfertaRelampago #Descuentos #Tecnologia"
    )
    with open("deal_reel.mp4", "rb") as video:
        res = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"video": video},
            timeout=120
        )
        if not res.ok:
            raise Exception(f"Error Telegram: {res.text}")

if __name__ == "__main__":
    deals = check_for_discounts()
    if not deals:
        print("No se registraron bajas de precio en esta corrida.")
    else:
        deal = deals[0]
        prod = deal["product"]
        print(f"Oferta encontrada: {prod['title']} (-{deal['diff_pct']}%)")
        script = generate_deal_script(deal)
        print(f"Guion de oferta: {script}")
        asyncio.run(create_audio_and_subtitles(script))
        download_image(prod['image_link'])
        build_video()
        send_telegram(deal, script)
        print("¡Reel de oferta relámpago enviado exitosamente a Telegram!")
