import os
import json
import requests

APP_ID = (os.environ.get("APP_ID") or "").strip()
CLIENT_SECRET = (os.environ.get("CLIENT_SECRET") or "").strip()
REFRESH_TOKEN = (os.environ.get("REFRESH_TOKEN") or "").strip()
USER_ID = (os.environ.get("USER_ID") or "").strip()

GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

HISTORY_FILE = "answered_questions.json"

def get_valid_access_token():
    url = "https://api.mercadolibre.com/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": APP_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(url, data=payload, headers=headers, timeout=20)
    data = r.json()
    if "access_token" in data:
        return data["access_token"]
    raise Exception(f"No se pudo renovar el token de Mercado Libre: {data}")

def get_unanswered_questions(token):
    url = f"https://api.mercadolibre.com/my/received_questions/search?seller_id={USER_ID}&status=UNANSWERED"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code == 200:
        return r.json().get("questions", [])
    print(f"Error al obtener preguntas: {r.status_code} - {r.text}")
    return []

def get_item_context(item_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    title = "Producto"
    permalink = f"https://articulo.mercadolibre.com.ar/{item_id}"
    desc = ""

    # Datos básicos
    r_item = requests.get(f"https://api.mercadolibre.com/items/{item_id}", headers=headers, timeout=15)
    if r_item.status_code == 200:
        d = r_item.json()
        title = d.get("title", title)
        permalink = d.get("permalink", permalink)

    # Descripción completa
    r_desc = requests.get(f"https://api.mercadolibre.com/items/{item_id}/description", headers=headers, timeout=15)
    if r_desc.status_code == 200:
        desc = r_desc.json().get("plain_text", "")

    return {"title": title, "link": permalink, "description": desc}

def generate_ai_answer(question_text, item_info):
    prompt = (
        f"Sos el asistente de atención al cliente de la tienda oficial ElectroOrg en Mercado Libre Argentina.\n"
        f"Redactá una respuesta cordial, impecable y profesional para responder la siguiente pregunta de un cliente.\n\n"
        f"CONTEXTO DEL PRODUCTO:\n"
        f"Título: {item_info['title']}\n"
        f"Ficha técnica / Descripción: {item_info['description'][:1500]}\n\n"
        f"PREGUNTA DEL CLIENTE:\n"
        f"\"{question_text}\"\n\n"
        f"PAUTAS ESTRICTAS DE RESPUESTA:\n"
        f"1. Tono: Amable, cálido, seguro y 100% profesional.\n"
        f"2. Hablá en representación del equipo de ElectroOrg (usá plural: 'Hola! Cómo estás? Desde el equipo de ElectroOrg te comentamos...').\n"
        f"3. Si la respuesta está en los datos, respondé con claridad y precisión técnica.\n"
        f"4. Si pregunta por stock o envíos, confirmá que contamos con stock para despacho inmediato.\n"
        f"5. Cierre cálido invitando a la compra: 'Cualquier otra consulta, estamos a tu disposición. Saludos cordiales, equipo de ElectroOrg!'\n"
        f"6. Devolvé ÚNICAMENTE el texto listo para enviar al cliente, sin introducciones ni notas."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        if "candidates" in res and len(res["candidates"]) > 0:
            return res["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Error generando respuesta con Gemini: {e}")

    return "¡Hola! ¿Cómo estás? Desde el equipo de ElectroOrg te comentamos que contamos con stock para despacho inmediato y garantía oficial. Ante cualquier otra duda quedamos a tu completa disposición. ¡Saludos del equipo de ElectroOrg!"

def send_telegram_alert(question_data, item_info, ai_answer):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = (
        f"🔔 *NUEVA PREGUNTA EN MERCADO LIBRE*\n\n"
        f"📦 *Producto:* [{item_info['title']}]({item_info['link']})\n\n"
        f"❓ *Pregunta del cliente:*\n"
        f"\"{question_data.get('text', '')}\"\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 *Respuesta sugerida (ElectroOrg):*\n\n"
        f"`{ai_answer}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 *Tocá el texto de la respuesta para copiarlo y pegarlo directo en Mercado Libre.*"
    )
    requests.post(
        url,
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
        timeout=30
    )

def main():
    token = get_valid_access_token()
    questions = get_unanswered_questions(token)

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    new_history = list(history)
    pending = [q for q in questions if str(q["id"]) not in history]

    if not pending:
        print("No hay preguntas nuevas sin responder.")
        return

    print(f"Preguntas pendientes por procesar: {len(pending)}")
    for q in pending:
        item_id = q["item_id"]
        item_info = get_item_context(item_id, token)
        answer = generate_ai_answer(q.get("text", ""), item_info)
        send_telegram_alert(q, item_info, answer)
        new_history.append(str(q["id"]))

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, indent=2)

    print("Alertas enviadas exitosamente.")

if __name__ == "__main__":
    main()
