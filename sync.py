import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request

APP_ID = os.environ.get("APP_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
USER_ID = os.environ.get("USER_ID")

# 1. Renovar Access Token
token_url = "https://api.mercadolibre.com/oauth/token"
payload = {
    "grant_type": "refresh_token",
    "client_id": APP_ID,
    "client_secret": CLIENT_SECRET,
    "refresh_token": REFRESH_TOKEN
}

req_token = urllib.request.Request(
    token_url,
    data=urllib.parse.urlencode(payload).encode("utf-8"),
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

with urllib.request.urlopen(req_token) as resp:
    token_data = json.loads(resp.read().decode("utf-8"))
    access_token = token_data["access_token"]

# 2. Consultar publicaciones activas
headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
search_url = f"https://api.mercadolibre.com/users/{USER_ID}/items/search?status=active&limit=50"
req_search = urllib.request.Request(search_url, headers=headers)

with urllib.request.urlopen(req_search) as resp:
    items_ids = json.loads(resp.read().decode("utf-8")).get("results", [])

items_data = []
if items_ids:
    chunks = [items_ids[i:i + 20] for i in range(0, len(items_ids), 20)]
    for chunk in chunks:
        ids_param = ",".join(chunk)
        url_chunk = f"https://api.mercadolibre.com/items?ids={ids_param}"
        req_c = urllib.request.Request(url_chunk, headers=headers)
        with urllib.request.urlopen(req_c) as resp:
            for r in json.loads(resp.read().decode("utf-8")):
                if r.get("code") == 200:
                    items_data.append(r.get("body"))

# 3. Exportar a CSV para Meta
with open("meta_catalog.csv", mode="w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "id", "title", "description", "availability", 
        "condition", "price", "link", "image_link", "brand"
    ])

    for item in items_data:
        title = item.get("title", "")
        price = f"{item.get('price')} {item.get('currency_id')}"
        permalink = item.get("permalink", "")
        stock = "in stock" if item.get("available_quantity", 0) > 0 else "out of stock"
        condition = "new" if item.get("condition") == "new" else "used"
        
        pictures = item.get("pictures", [])
        image_url = pictures[0].get("secure_url", "") if pictures else ""
        
        brand = "ElectroOrg"
        for attr in item.get("attributes", []):
            if attr.get("id") == "BRAND":
                brand = attr.get("value_name") or brand
                break

        writer.writerow([
            item.get("id"), title, title, stock, 
            condition, price, permalink, image_url, brand
        ])

print(f"Catálogo generado con {len(items_data)} productos.")
