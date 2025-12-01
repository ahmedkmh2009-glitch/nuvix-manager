import os
import json
import asyncio
from pathlib import Path
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import aiohttp
import discord
from discord import Embed, Intents

# =============================
# Cargar variables de entorno
# =============================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
SELLAUTH_API_KEY = os.getenv("SELLAUTH_API_KEY")
SELLAUTH_SHOP_ID = os.getenv("SELLAUTH_SHOP_ID")
SHOP_NAME = os.getenv("SHOP_NAME", "Mi Tienda")
PORT = int(os.getenv("PORT", 10000))

if not (DISCORD_TOKEN and DISCORD_CHANNEL_ID and SELLAUTH_API_KEY and SELLAUTH_SHOP_ID):
    raise Exception("Faltan variables en Render")


# =============================
# Rangos Premium
# =============================
RANGOS = [
    (0.50,   "Agradecido",  "🤍"),
    (1.00,   "Amado",       "❤️"),
    (1.50,   "Especial",    "💛"),
    (2.00,   "Premium",     "💚"),
    (2.50,   "Elite",       "💜"),
    (3.00,   "Rey",         "👑"),
    (3.50,   "Maestro",     "🔥"),
    (4.00,   "Empresario",  "💼"),
    (4.50,   "Diamante",    "💎"),
    (5.00,   "Leyenda",     "🦅"),
    (7.00,   "Titan",       "⭐"),
    (9.00,   "Supremo",     "⚡"),
    (11.00,  "Dominante",   "🦂"),
    (13.00,  "Inmortal",    "🌙"),
    (15.00,  "Magnate",     "💰"),
    (17.00,  "Ultra",       "💠"),
    (19.00,  "Colosal",     "🗿"),
    (21.00,  "Divino",      "🪽"),
    (23.00,  "Apex",        "🐺"),
    (25.00,  "Legendario",  "🐉"),
    (27.00,  "Mítico",      "🔱"),
    (29.00,  "Omnisciente", "🌀"),
    (30.00,  "Dios del Mercado", "👑🔥"),
]


def obtener_rango(total):
    rango, emoji = "Nuevo", "🆕"
    for minimo, nombre, em in RANGOS:
        if total >= minimo:
            rango, emoji = nombre, em
    return rango, emoji


# =============================
# DB JSON para totales
# =============================
BUYERS_FILE = Path("buyers_totals.json")

if BUYERS_FILE.exists():
    buyers_totals = json.load(open(BUYERS_FILE, "r", encoding="utf-8"))
else:
    buyers_totals = {}


def guardar_totales():
    json.dump(buyers_totals, open(BUYERS_FILE, "w", encoding="utf-8"), indent=2)


# =============================
# Discord BOT
# =============================
intents = Intents.default()
bot = discord.Client(intents=intents)

discord_channel = None


@bot.event
async def on_ready():
    global discord_channel
    print(f"Bot conectado como {bot.user}")
    discord_channel = await bot.fetch_channel(DISCORD_CHANNEL_ID)


async def enviar_mensaje(order, total_cliente):
    nombre_rango, emoji_rango = obtener_rango(total_cliente)

    cantidad = order.get("quantity", 1)
    total = float(order.get("total", 0))
    moneda = order.get("currency", "EUR")
    product = order.get("product", {}).get("name", "Producto")
    metodo = order.get("gateway", "Método")
    buyer = order.get("buyer_email", "cliente")

    descripcion = (
        f"» Un **{nombre_rango} {emoji_rango}** acaba de comprar "
        f"**{cantidad}x {product}** usando **{metodo}**.\n"
        f"Compra actual: **{total:.2f} {moneda}**\n"
        f"Gasto total del cliente: **{total_cliente:.2f} {moneda}**\n"
        f"Gracias por confiar en **{SHOP_NAME}** 💕"
    )

    embed = Embed(description=descripcion, color=0x2ECC71)
    embed.set_footer(text=SHOP_NAME)

    await discord_channel.send(embed=embed)


# =============================
# Obtener factura desde API
# =============================
async def obtener_invoice(invoice_id):
    url = f"https://dev.sell.app/api/v1/invoices/{invoice_id}"
    headers = {
        "Authorization": f"Bearer {SELLAUTH_API_KEY}",
        "Accept": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()


# =============================
# Flask server (webhook)
# =============================
app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return "Bot SellAuth está vivo."


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("Webhook recibido:", data)

    invoice_id = data.get("json", {}).get("data", {}).get("invoice_id")

    if not invoice_id:
        return jsonify({"error": "invoice_id no encontrado"}), 400

    asyncio.run(handle_invoice(invoice_id))

    return jsonify({"ok": True})


async def handle_invoice(invoice_id):
    order = await obtener_invoice(invoice_id)

    buyer = order.get("buyer_email", "cliente").lower()
    total = float(order.get("total", 0))

    anterior = buyers_totals.get(buyer, 0)
    nuevo_total = anterior + total
    buyers_totals[buyer] = nuevo_total
    guardar_totales()

    await enviar_mensaje(order, nuevo_total)


# =============================
# INICIAR TODO
# =============================
def start_flask():
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    import threading

    threading.Thread(target=start_flask).start()
    bot.run(DISCORD_TOKEN)
