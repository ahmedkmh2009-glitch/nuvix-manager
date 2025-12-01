import re
import datetime

import discord
from discord.ext import commands
from discord import app_commands

import config
from db import init_db, get_conn
from sellauth_client import sellauth, SellAuthError

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --------- Helpers for roles/permissions ---------

def is_owner(user: discord.abc.User) -> bool:
    return user.id == config.OWNER_ID

def has_any_role(member: discord.Member | None, role_ids: list[int]) -> bool:
    if not member:
        return False
    return any(r.id in role_ids for r in member.roles)

def classify_user(interaction: discord.Interaction):
    # Return tuple (is_owner, is_admin, is_staff, is_user_role)
    user = interaction.user
    guild = interaction.guild
    if isinstance(user, discord.Member):
        member = user
    elif guild:
        member = guild.get_member(user.id)
    else:
        member = None

    owner = is_owner(user)
    admin = has_any_role(member, config.ADMIN_ROLE_IDS)
    staff = has_any_role(member, config.STAFF_ROLE_IDS)
    user_role = has_any_role(member, config.USER_ROLE_IDS)

    return owner, admin, staff, user_role

# Commands solo owner
OWNER_ONLY_COMMANDS = {
    "shutdown",
    "restart",
    "reloadcmds",
}

# Comandos de anuncios (solo owner)
ANNOUNCE_COMMANDS = {
    "announce",
    "flashsale",
}

# Comandos de admin (owner también puede)
ADMIN_COMMANDS = {
    "bal",
    "refund",
    "payout",
    "invoiceinfo",
    "lastinvoices",
    "stock",
    "productinfo",
    "buy",
    "blacklist",
    "unblacklist",
    "blacklistlist",
}

# Comandos que el staff puede usar (además de /vouch)
STAFF_ALLOWED = {
    "ticket",
    "ticketclose",
    "ticketlogs",
    "transcript",
    "warn",
    "case",
    "vouchlist",
    "myvouches",
}

# Miembros normales solo pueden usar:
MEMBER_ALLOWED = {"vouch"}


@bot.tree.check
async def global_permission_check(interaction: discord.Interaction) -> bool:
    # Deja pasar interacciones raras o DMs
    if not interaction.command:
        return True
    cmd = interaction.command.qualified_name  # nombre del slash
    owner, admin, staff, user_role = classify_user(interaction)

    # Owner siempre puede todo
    if owner:
        return True

    # ---- Usuarios sin owner ----
    # Miembros (rol user o sin roles especiales)
    if not admin and not staff:
        if cmd in MEMBER_ALLOWED:
            return True
        await interaction.response.send_message(
            "❌ No tienes permiso para usar este comando. Solo puedes usar **/vouch**.",
            ephemeral=True,
        )
        return False

    # Admin (pero no owner)
    if admin and not staff:
        # Admin no puede usar comandos solo owner ni anuncios
        if cmd in OWNER_ONLY_COMMANDS or cmd in ANNOUNCE_COMMANDS:
            await interaction.response.send_message(
                "❌ Este comando es solo para el owner del bot.",
                ephemeral=True,
            )
            return False
        # Admin puede usar prácticamente todo lo demás
        return True

    # Staff (no admin, no owner)
    if staff and not admin:
        # Staff no puede anuncios ni owner-only ni comandos admin
        if cmd in OWNER_ONLY_COMMANDS or cmd in ANNOUNCE_COMMANDS or cmd in ADMIN_COMMANDS:
            await interaction.response.send_message(
                "❌ No tienes permiso para usar este comando.",
                ephemeral=True,
            )
            return False
        # Staff solo puede los comandos marcados
        if cmd in STAFF_ALLOWED or cmd in MEMBER_ALLOWED:
            return True
        await interaction.response.send_message(
            "❌ No tienes permiso para usar este comando.",
            ephemeral=True,
        )
        return False

    # fallback
    return True


@bot.event
async def on_ready():
    print(f"Conectado como {bot.user} (ID: {bot.user.id})")
    init_db()
    try:
        await bot.tree.sync()
        print("Slash commands sincronizados.")
    except Exception as e:
        print("Error al sincronizar slash commands:", e)
    await bot.change_presence(activity=discord.Game(name="NuvixMarket | /vouch"))


# ---------- Anti-invite / anti-spam ----------

INVITE_REGEX = r"(https?://)?(www\.)?(discord\.gg|discord\.com/invite)/[A-Za-z0-9]+"

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # Owner y Admin no se mutean por esto
    member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
    if is_owner(message.author) or has_any_role(member, config.ADMIN_ROLE_IDS):
        return

    if re.search(INVITE_REGEX, message.content):
        try:
            await message.delete()
        except Exception:
            pass

        # timeout 1h para todos menos owner/admin (staff incluido)
        try:
            until = datetime.timedelta(hours=1)
            await member.timeout(until, reason="Invite / spam detectado")
        except Exception:
            pass

        # log
        try:
            log_channel = message.guild.get_channel(config.LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    f"🚫 {member.mention} ha sido **muteado 1h** por enviar invitaciones/spam.\n"
                    f"Mensaje eliminado automáticamente."
                )
        except Exception:
            pass

    # Slash commands no dependen de on_message, pero por si usas prefijos:
    await bot.process_commands(message)


# ---------- Utilidad básica ----------

@bot.tree.command(name="ping", description="Ver ping del bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency*1000)} ms`")

@bot.tree.command(name="about", description="Información del bot")
async def about(interaction: discord.Interaction):
    await interaction.response.send_message("🤖 NuvixMarket x SellAuth • Bot avanzado para tu shop.")

@bot.tree.command(name="status", description="Estado del bot")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message("🟢 Bot online. Si algo falla, revisa la API Key / Shop ID.")


# ---------- VOUCHES PREMIUM ----------

@bot.tree.command(name="vouch", description="Dejar un vouch (único comando público)")
@app_commands.describe(product="Qué estás reseñando (ej: Netflix 4K)", stars="De 1 a 5 estrellas")
async def vouch(interaction: discord.Interaction, product: str, stars: app_commands.Range[int, 1, 5] = 5):
    """Miembros, staff, admin, owner: todos pueden vouch."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vouches (guild_id, user_id, content, stars) VALUES (?, ?, ?, ?)",
        (interaction.guild_id, interaction.user.id, product, int(stars)),
    )
    vouch_id = cur.lastrowid
    conn.commit()
    conn.close()

    stars_str = "⭐" * int(stars)

    embed = discord.Embed(
        title="New vouch created!",
        description=stars_str,
        color=discord.Color.blue(),
    )
    embed.add_field(name="Vouch:", value=product, inline=False)
    embed.add_field(name="Vouch Nº:", value=f"#{vouch_id}", inline=False)
    embed.add_field(name="Vouched by:", value=interaction.user.mention, inline=False)
    embed.add_field(
        name="Vouched at:",
        value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        inline=False,
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Nuvix Market Vouches System")

    # Enviar al canal de feedback si existe, si no, en el actual
    guild = interaction.guild
    channel = guild.get_channel(config.FEEDBACK_CHANNEL_ID) if guild else None
    if channel:
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Vouch enviado. ¡Gracias por confiar en NuvixMarket!", ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="vouchlist", description="Ver últimos vouches (solo staff/admin/owner)")
async def vouchlist(interaction: discord.Interaction):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, content, stars, created_at FROM vouches WHERE guild_id = ? ORDER BY id DESC LIMIT 20",
        (interaction.guild_id,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("No hay vouches todavía.", ephemeral=True)
        return

    lines = []
    for r in rows:
        s = "⭐" * (r["stars"] or 5)
        lines.append(f"`#{r['id']}` {s} <@{r['user_id']}> — {r['content']} ({r['created_at']})")

    txt = "⭐ **Últimos vouches:**\n" + "\n".join(lines)
    await interaction.response.send_message(txt, ephemeral=True)


@bot.tree.command(name="myvouches", description="Ver tus vouches (staff/admin/owner)")
async def myvouches(interaction: discord.Interaction):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, content, stars, created_at FROM vouches WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
        (interaction.guild_id, interaction.user.id),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("No has dejado ningún vouch aún.", ephemeral=True)
        return

    lines = []
    for r in rows:
        s = "⭐" * (r["stars"] or 5)
        lines.append(f"`#{r['id']}` {s} — {r['content']} ({r['created_at']})")

    txt = "⭐ **Tus vouches:**\n" + "\n".join(lines)
    await interaction.response.send_message(txt, ephemeral=True)


@bot.tree.command(name="vouchdelete", description="Eliminar un vouch por ID (admin/owner)")
async def vouchdelete(interaction: discord.Interaction, vouch_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM vouches WHERE id = ? AND guild_id = ?", (vouch_id, interaction.guild_id))
    changes = cur.rowcount
    conn.commit()
    conn.close()

    if changes:
        await interaction.response.send_message("🗑 Vouch eliminado.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Vouch no encontrado.", ephemeral=True)


# ---------- Blacklist básica ----------

@bot.tree.command(name="blacklist", description="Añadir usuario a la blacklist (admin/owner)")
async def blacklist(interaction: discord.Interaction, user: discord.User, reason: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO blacklist (guild_id, user_id, reason) VALUES (?, ?, ?)",
        (interaction.guild_id, user.id, reason),
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"🚫 {user.mention} añadido a blacklist. Motivo: {reason}", ephemeral=True)


@bot.tree.command(name="unblacklist", description="Quitar usuario de la blacklist (admin/owner)")
async def unblacklist(interaction: discord.Interaction, user: discord.User):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM blacklist WHERE guild_id = ? AND user_id = ?",
        (interaction.guild_id, user.id),
    )
    changes = cur.rowcount
    conn.commit()
    conn.close()
    if changes:
        await interaction.response.send_message(f"✅ {user.mention} eliminado de blacklist.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Ese usuario no estaba en blacklist.", ephemeral=True)


@bot.tree.command(name="blacklistlist", description="Ver usuarios en blacklist (admin/owner)")
async def blacklistlist(interaction: discord.Interaction):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, reason, created_at FROM blacklist WHERE guild_id = ?", (interaction.guild_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("No hay usuarios en blacklist.", ephemeral=True)
        return
    txt = "🚫 **Blacklist:**\n"
    for r in rows:
        txt += f"- <@{r['user_id']}> — {r['reason']} ({r['created_at']})\n"
    await interaction.response.send_message(txt, ephemeral=True)


# ---------- Tickets (simplificado) ----------

@bot.tree.command(name="ticket", description="Abrir ticket (staff/admin/owner gestionan)")
async def ticket(interaction: discord.Interaction, motivo: str):
    await interaction.response.send_message(
        f"🎫 Ticket creado (placeholder). Motivo: `{motivo}`\nAquí puedes enlazar con tu sistema de canales de tickets.",
        ephemeral=True,
    )

@bot.tree.command(name="ticketlogs", description="Ver logs de tickets (staff/admin/owner)")
async def ticketlogs(interaction: discord.Interaction):
    await interaction.response.send_message("📜 /ticketlogs placeholder.", ephemeral=True)

@bot.tree.command(name="transcript", description="Generar transcript de ticket (staff/admin/owner)")
async def transcript(interaction: discord.Interaction):
    await interaction.response.send_message("📝 /transcript placeholder.", ephemeral=True)


# ---------- Warns básicos ----------

@bot.tree.command(name="warn", description="Dar un warn (staff/admin/owner)")
async def warn(interaction: discord.Interaction, user: discord.User, reason: str):
    await interaction.response.send_message(
        f"⚠️ Warn a {user.mention}: {reason}\n(placeholder, aquí puedes guardar en DB)",
        ephemeral=True,
    )

@bot.tree.command(name="case", description="Ver historial de warns (staff/admin/owner)")
async def case(interaction: discord.Interaction, user: discord.User):
    await interaction.response.send_message(
        f"📂 /case placeholder para {user.mention}.",
        ephemeral=True,
    )


# ---------- Comandos de shop básicos (admin/owner) ----------

@bot.tree.command(name="stock", description="Ver stock de productos (admin/owner)")
async def stock(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        data = sellauth.list_products()
        products = data.get("products", data if isinstance(data, list) else [])
        if not products:
            await interaction.followup.send("No hay productos.", ephemeral=True)
            return
        txt = "📦 **Stock disponible:**\n"
        for p in products[:20]:
            txt += f"- **{p.get('name','?')}** — `{p.get('stock','?')}` uds (ID: `{p.get('id')}`)\n"
        await interaction.followup.send(txt, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /stock: `{e}`", ephemeral=True)

@bot.tree.command(name="productinfo", description="Info de un producto (admin/owner)")
async def productinfo(interaction: discord.Interaction, product_id: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        p = sellauth.get_product(product_id)
        e = discord.Embed(
            title=p.get("name", "Producto"),
            description=p.get("description", ""),
            color=discord.Color.blurple(),
        )
        e.add_field(name="ID", value=str(p.get("id")), inline=True)
        e.add_field(name="Precio", value=str(p.get("price", "?")), inline=True)
        e.add_field(name="Stock", value=str(p.get("stock", "?")), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /productinfo: `{e}`", ephemeral=True)

@bot.tree.command(name="buy", description="Crear checkout para un producto (admin/owner)")
async def buy(interaction: discord.Interaction, product_id: str, quantity: int, email: str | None = None):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        data = sellauth.create_checkout(product_id, quantity, email, interaction.user.id)
        url = data.get("url") or data.get("checkout_url") or "URL no devuelta por la API."
        await interaction.followup.send(f"🧾 Checkout creado:\n{url}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /buy: `{e}`", ephemeral=True)

@bot.tree.command(name="invoiceinfo", description="Ver información de una factura (admin/owner)")
async def invoiceinfo(interaction: discord.Interaction, invoice_id: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        inv = sellauth.get_invoice(invoice_id)
        e = discord.Embed(title=f"Invoice {invoice_id}", color=discord.Color.green())
        e.add_field(name="Estado", value=str(inv.get("status", "?")))
        e.add_field(name="Total", value=str(inv.get("total", "?")))
        e.add_field(name="Moneda", value=str(inv.get("currency", "?")))
        await interaction.followup.send(embed=e, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /invoiceinfo: `{e}`", ephemeral=True)

@bot.tree.command(name="lastinvoices", description="Ver últimas facturas del shop (admin/owner)")
async def lastinvoices(interaction: discord.Interaction, limit: int = 10):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        data = sellauth.list_invoices(limit)
        invoices = data.get("invoices", data if isinstance(data, list) else [])
        if not invoices:
            await interaction.followup.send("No hay facturas.", ephemeral=True)
            return
        txt = "📊 **Últimas facturas:**\n"
        for inv in invoices[:limit]:
            txt += f"- `{inv.get('id')}` | {inv.get('status')} | {inv.get('total')} {inv.get('currency')}\n"
        await interaction.followup.send(txt, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /lastinvoices: `{e}`", ephemeral=True)

@bot.tree.command(name="bal", description="Ver balance de un cliente por email (admin/owner)")
async def bal(interaction: discord.Interaction, email: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        customer = sellauth.get_customer_by_email(email)
        if not customer:
            await interaction.followup.send(f"❌ No se encontró cliente con email `{email}`.", ephemeral=True)
            return
        balance = customer.get("balance", 0)
        cid = customer.get("id") or customer.get("customer_id")
        embed = discord.Embed(
            title="💳 Balance del cliente",
            description=f"Email: **{email}**",
            color=discord.Color.blurple(),
        )
        if cid:
            embed.add_field(name="Customer ID", value=str(cid), inline=False)
        embed.add_field(name="Balance", value=f"`{balance}`", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /bal: `{e}`", ephemeral=True)

@bot.tree.command(name="refund", description="Reembolsar una factura (admin/owner)")
async def refund(interaction: discord.Interaction, invoice_id: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        data = sellauth.refund_invoice(invoice_id)
        await interaction.followup.send(f"✅ Factura reembolsada. Respuesta: `{data}`", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error en /refund: `{e}`", ephemeral=True)


# ---------- Anuncios (solo owner) ----------

@bot.tree.command(name="announce", description="Enviar anuncio (solo owner)")
async def announce(interaction: discord.Interaction, title: str, message: str):
    if not is_owner(interaction.user):
        await interaction.response.send_message("❌ Solo el owner puede usar este comando.", ephemeral=True)
        return
    channel = interaction.guild.get_channel(config.ANNOUNCE_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Canal de anuncios no configurado correctamente.", ephemeral=True)
        return
    embed = discord.Embed(title=title, description=message, color=discord.Color.blurple())
    embed.set_footer(text="NuvixMarket • Announce")
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Anuncio enviado.", ephemeral=True)


@bot.tree.command(name="flashsale", description="Anunciar oferta flash (solo owner)")
async def flashsale(interaction: discord.Interaction, product_name: str, discount_percent: int, duration_minutes: int):
    if not is_owner(interaction.user):
        await interaction.response.send_message("❌ Solo el owner puede usar este comando.", ephemeral=True)
        return
    channel = interaction.guild.get_channel(config.ANNOUNCE_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Canal de anuncios no configurado.", ephemeral=True)
        return
    embed = discord.Embed(
        title="🔥 OFERTA FLASH",
        description=f"Producto: **{product_name}**\nDescuento: **{discount_percent}%**\nDuración: **{duration_minutes} min**",
        color=discord.Color.red(),
    )
    embed.set_footer(text="NuvixMarket • Flash Sale")
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Flash sale anunciada.", ephemeral=True)


# ---------- Control del bot (solo owner) ----------

@bot.tree.command(name="reloadcmds", description="Recargar slash commands (owner)")
async def reloadcmds(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message("❌ Solo el owner puede usar este comando.", ephemeral=True)
        return
    await bot.tree.sync()
    await interaction.response.send_message("✅ Slash commands recargados.", ephemeral=True)

@bot.tree.command(name="shutdown", description="Apagar bot (owner)")
async def shutdown(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message("❌ Solo el owner puede usar este comando.", ephemeral=True)
        return
    await interaction.response.send_message("🛑 Apagando bot...", ephemeral=True)
    await bot.close()

@bot.tree.command(name="restart", description="Reiniciar bot (owner)")
async def restart(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message("❌ Solo el owner puede usar este comando.", ephemeral=True)
        return
    await interaction.response.send_message("🔁 Reinicio simulado (en Render se reinicia al reiniciar el servicio).", ephemeral=True)


# ---------- Arranque ----------

def start_bot():
    init_db()
    bot.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    start_bot()
