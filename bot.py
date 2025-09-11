import os
import time
import asyncio
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
except ImportError:
    # Alternatív import ha a fenti nem működik
    import telegram
    from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    Update = telegram.Update
    InlineKeyboardButton = telegram.InlineKeyboardButton
    InlineKeyboardMarkup = telegram.InlineKeyboardMarkup

# Beállítások
ADMIN_ID = 5437277473
ARUSITO_IDK = [8055559906, 5803982074, 7471563285]  # Új árusító hozzáadva
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("HIBA: BOT_TOKEN környezeti változó nincs beállítva!")
    print("Kérlek állítsd be a BOT_TOKEN-t a környezeti változókban.")
    exit(1)

# Globális adatok
keszlet = {"VapSolo": {}, "Elf Bar": {}}
akciok = "Jelenleg nincsenek akciók."
vip = "Jelenleg nincsenek V.I.P. ajánlatok."
user_sessions = {}
# Eladási számláló minden árusító számára: {seller_id: {"total_sold": total, "remainder": current_count}}
sales_counters = {}

# Termék leírások
termek_leirasok = {
    "VapSolo": (
        "💨 60.000 slukk\n"
        "🎯 3 íz egyben\n"
        "💪 5% nikotin\n"
        "📱 kisebb kijelző a folyadék és akkumulátor állapotáról\n"
        "🔋 650 mAh akkumulátor\n"
        "⚡ USB Type-C töltő\n\n"
        "💰 **Ár: 10.000 Ft**"
    ),
    "Elf Bar": (
        "⚙️ 3 fokozat\n"
        "🌱 Eco mode: 40.000 slukk\n"
        "🔥 Normal mode: 30.000 slukk\n"
        "🚀 Boost mode: 25.000 slukk\n"
        "💪 5% nikotin\n"
        "📱 nagyobb kijelző a folyadék és akkumulátor állapotáról valamint az aktuális fokozatról\n"
        "🔋 1000 mAh akkumulátor\n"
        "⚡ USB Type-C töltő\n\n"
        "💰 **Ár: 10.000 Ft**"
    )
}

def get_user_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "visited": False,
            "state": {},
            "order_state": {},
            "pending_data": {},
            "chat_id": None,
            "last_activity": time.time(),
            "last_menu_message_id": None,
            "reserved_stock": {}  # Ideiglenes készlet lefoglalás kosárhoz
        }
    else:
        user_sessions[user_id]["last_activity"] = time.time()
    return user_sessions[user_id]

def get_seller_sales_count(seller_id):
    """Árusító eladási számának lekérése (jelenlegi számláló érték 0-9)"""
    if seller_id not in sales_counters:
        return 0
    return sales_counters[seller_id].get("remainder", 0)

def get_seller_total_sales(seller_id):
    """Árusító összes eladásának lekérése"""
    if seller_id not in sales_counters:
        return 0
    return sales_counters[seller_id].get("total_sold", 0)

def release_reserved_stock(user_id):
    """Lefoglalt készlet felszabadítása"""
    session = get_user_session(user_id)
    if "reserved_stock" not in session:
        return
    
    for (termek, iz), qty in session["reserved_stock"].items():
        if termek in keszlet:
            if iz in keszlet[termek]:
                keszlet[termek][iz] += qty
            else:
                keszlet[termek][iz] = qty
    
    session["reserved_stock"] = {}
    print(f"Lefoglalt készlet felszabadítva user {user_id} számára")

def build_order_summary(items):
    """Rendelési összesítő készítése"""
    if not items:
        return "A kosár üres.", 0
    
    # Csoportosítás termék és íz szerint
    grouped = {}
    for item in items:
        termek = item["termek"]
        iz = item["iz"]
        db = item["db"]
        
        key = (termek, iz)
        if key not in grouped:
            grouped[key] = 0
        grouped[key] += db
    
    # Összesítő szöveg készítése
    summary = "🛒 **Rendelési összesítő:**\n\n"
    total_qty = 0
    
    # Termékek szerint csoportosítva
    termekek = {}
    for (termek, iz), db in grouped.items():
        if termek not in termekek:
            termekek[termek] = []
        termekek[termek].append((iz, db))
        total_qty += db
    
    for termek, izek in termekek.items():
        # Teljes termék név
        if termek == "VapSolo":
            display_name = "VapSolo Triple 60K"
        elif termek == "Elf Bar":
            display_name = "Elf Bar MoonNight 40K" 
        else:
            display_name = termek
        
        summary += f"**{display_name}:**\n"
        for iz, db in izek:
            summary += f"• {iz}: {db} db\n"
        summary += "\n"
    
    summary += f"📦 **Összesen:** {total_qty} db"
    return summary, total_qty

def increment_seller_sales(seller_id, quantity=1):
    """Árusító eladási számának növelése (darabszám szerint)"""
    if seller_id not in sales_counters:
        sales_counters[seller_id] = {"total_sold": 0, "remainder": 0}
    
    old_total = sales_counters[seller_id]["total_sold"]
    old_remainder = sales_counters[seller_id]["remainder"]
    
    new_total = old_total + quantity
    new_remainder = new_total % 10
    
    # Delta awards: hány 10-es küszöböt lépett át EBBEN a rendelésben
    delta_awards = (old_total + quantity) // 10 - old_total // 10
    
    # Frissítés
    sales_counters[seller_id]["total_sold"] = new_total
    sales_counters[seller_id]["remainder"] = new_remainder
    
    return new_remainder, delta_awards, new_total  # (jelenlegi számláló, új awards, összes eladás)

async def notify_admin_and_seller(context, seller_id, current_count, delta_awards=0, total_sold=0):
    """Admin és árusító értesítése eladásokról"""
    seller_name = f"Árusító (ID: {seller_id})"
    
    # Admin értesítése
    admin_msg = f"📊 **Eladási jelentés**\n\n{seller_name} jelenlegi ciklus: **{current_count}/10 db**"
    admin_msg += f"\n📊 **Összes eladás:** {total_sold} db"
    
    if delta_awards > 0:
        if delta_awards == 1:
            admin_msg += f"\n\n🎉 **{seller_name} elérte a 10 db-os limitet!**\n✅ Jogosult 1 db ingyen termékre!"
        else:
            admin_msg += f"\n\n🎉 **{seller_name} {delta_awards} alkalommal érte el a 10 db-os limitet!**\n✅ Jogosult {delta_awards} db ingyen termékre!"
    
    await send_private_message(context, ADMIN_ID, admin_msg)
    
    # Árusító értesítése
    seller_msg = f"📈 **Eladás rögzítve!**\n\n📊 **Összes eladás:** {total_sold} db"
    seller_msg += f"\n📊 **Jelenlegi ciklus:** {current_count}/10 db"
    
    if delta_awards > 0:
        if delta_awards == 1:
            seller_msg += f"\n\n🎉 **Gratulálunk!**\nElérted a 10 db-os limitet!\n✅ Jogosult vagy 1 db ingyen termékre!"
            seller_msg += f"\nVedd fel a kapcsolatot az adminnal!"
        else:
            seller_msg += f"\n\n🎉 **SZUPER GRATULÁLUNK!**\n{delta_awards} alkalommal érted el a 10 db-os limitet!\n✅ Jogosult vagy {delta_awards} db ingyen termékre!"
            seller_msg += f"\nVedd fel a kapcsolatot az adminnal!"
    else:
        remaining = 10 - current_count if current_count > 0 else 10
        seller_msg += f"\nMég {remaining} db az ingyen termékig! 💪"
    
    await send_private_message(context, seller_id, seller_msg)

def get_product_description(termek):
    """Visszaadja a termék leírását"""
    if termek == "VapSolo" or termek == "VapSolo Triple 60K":
        return (
            "60.000 slukk\n"
            "3 íz egyben\n"
            "5% nikotin\n"
            "kisebb kijelző a folyadék és akkumulátor állapotáról\n"
            "650 mAh akkumulátor\n"
            "USB Type-C töltő\n\n"
        )
    elif termek == "Elf Bar" or termek == "Elf Bar MoonNight 40K":
        return (
            "3 fokozat\n"
            "Eco mode: 40.000 slukk\n"
            "Normal mode: 30.000 slukk\n"
            "Boost mode: 25.000 slukk\n"
            "5% nikotin\n"
            "nagyobb kijelző a folyadék és akkumulátor állapotáról valamint az aktuális fokozatról\n"
            "1000 mAh akkumulátor\n"
            "USB Type-C töltő\n\n"
        )
    else:
        return ""

def cleanup_inactive_sessions():
    current_time = time.time()
    timeout = 3600

    for user_id in list(user_sessions.keys()):
        if current_time - user_sessions[user_id].get("last_activity", 0) > timeout:
            # Lefoglalt készlet felszabadítása mielőtt töröljük a sessiont
            release_reserved_stock(user_id)
            del user_sessions[user_id]
            print(f"Inaktív session törölve: {user_id}")

async def send_private_message(context, admin_id, message):
    try:
        await context.bot.send_message(chat_id=admin_id, text=message, parse_mode='Markdown')
    except Exception:
        pass

async def delete_message_after_delay(context, chat_id, message_id, delay=10):
    """Üzenet törlése megadott idő után"""
    try:
        await asyncio.sleep(delay)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Nem sikerült törölni az üzenetet: {e}")

async def start_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Csatorna kezelése - csak átirányítás privát chatbe"""
    try:
        chat_id = update.effective_chat.id if update.effective_chat else 0

        # Bot neve lekérése
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        welcome_text = (
            "🔸 Üdvözlünk az e-cigaretta boltban! 🔸\n\n"
            "📱 A termékek böngészéséhez és rendeléshez kattints az alábbi gombra, "
            "ami átirányít a privát chatbe:\n\n"
            "⬇️ PRIVÁT CHAT INDÍTÁSA ⬇️"
        )

        keyboard = [[InlineKeyboardButton("💬 Privát chat megnyitása", url=f"https://t.me/{bot_username}?start=channel_{abs(int(chat_id))}")]]

        message_obj = update.message or update.channel_post
        if message_obj:
            sent_message = await message_obj.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

            # Üzenet törlése 30 másodperc után
            asyncio.create_task(delete_message_after_delay(context, chat_id, sent_message.message_id, 30))

            # Eredeti üzenet törlése is (ha /start parancs volt)
            if update.message:
                asyncio.create_task(delete_message_after_delay(context, chat_id, update.message.message_id, 30))

    except Exception as e:
        print(f"Error in start_channel: {e}")

async def clear_chat_history(context, chat_id, user_id, keep_message_id=None):
    """Chat előzmények törlése - agresszívebb megközelítés"""
    try:
        session = get_user_session(user_id)
        deleted_count = 0
        
        # 1. Töröljük a sessionban tárolt message ID-kat
        for key in list(session.keys()):
            if "message_id" in key and session[key] and session[key] != keep_message_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=session[key])
                    deleted_count += 1
                    del session[key]
                except Exception:
                    pass
        
        # 2. Próbáljuk meg törölni a legutóbbi üzeneteket
        # Egy üzenet küldése hogy megkapjuk az aktuális message_id-t
        try:
            temp_msg = await context.bot.send_message(chat_id=chat_id, text="🧹")
            current_id = temp_msg.message_id
            await context.bot.delete_message(chat_id=chat_id, message_id=current_id)
            
            # Visszafelé töröljük az üzeneteket az aktuális ID-tól
            for i in range(1, 20):  # Utolsó 20 üzenet
                try:
                    msg_id = current_id - i
                    if msg_id != keep_message_id:
                        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                        deleted_count += 1
                except Exception:
                    continue
        except Exception:
            pass
            
        print(f"Chat takarítás: {deleted_count} üzenet törölve")
        
    except Exception as e:
        print(f"Hiba a chat takarításban: {e}")
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Privát chat és csoport kezelése"""
    try:
        # Ha csatorna, akkor csatorna kezelőt hívjuk
        if update.channel_post or (update.effective_chat and update.effective_chat.type == "channel"):
            await start_channel(update, context)
            return

        # Ha csoport vagy szupergroup, szintén csatorna kezelőt hívjuk
        chat_type = update.effective_chat.type if update.effective_chat else "private"
        if chat_type in ["group", "supergroup"]:
            await start_channel(update, context)
            return

        if not update.effective_user:
            return

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "Felhasználó"
        chat_id = update.effective_chat.id

        # Session törlése és újra létrehozása
        old_session = None
        if user_id in user_sessions:
            old_session = user_sessions[user_id]
            del user_sessions[user_id]

        session = get_user_session(user_id)
        session["chat_id"] = chat_id

        # Ellenőrizzük, hogy csatornából jön-e (start paraméter alapján)
        channel_info = ""
        if context.args and len(context.args) > 0 and context.args[0].startswith("channel_"):
            channel_info = "\n🔗 Sikeresen csatlakoztál a csatornából!"

        # Főmenü azonnali megjelenítése (nem üdvözlő szöveg)
        main_menu = []
        main_menu.append([InlineKeyboardButton("📦 Aktuális", callback_data="aktualis")])
        main_menu.append([InlineKeyboardButton("🎯 Akció", callback_data="akcio")])
        main_menu.append([InlineKeyboardButton("📋 Termékek", callback_data="termekek")])

        if user_id in ARUSITO_IDK or user_id == ADMIN_ID:
            main_menu.append([InlineKeyboardButton("⭐ V.I.P.", callback_data="vip")])
            main_menu.append([InlineKeyboardButton("🛒 Rendelés", callback_data="rendeles")])

        if user_id == ADMIN_ID:
            main_menu.append([InlineKeyboardButton("📥 Feltöltés", callback_data="feltoltes")])

        # Tiszta üdvözlő szöveg a főmenüvel
        welcome_text = f"Szia {user_name}! 👋{channel_info}\n\nVálassz a menüből:"

        # ELŐSZÖR: Új üzenet küldése
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            reply_markup=InlineKeyboardMarkup(main_menu)
        )
        session["last_menu_message_id"] = sent_message.message_id

        # AZUTÁN: Teljes chat takarítás a háttérben
        async def cleanup_chat():
            await asyncio.sleep(0.5)  # Kis késleltetés a menü megjelenítése után
            
            # /start parancs törlése
            message_obj = update.message
            if message_obj:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_obj.message_id)
                except Exception:
                    pass
            
            # Teljes chat takarítás (kivéve az új menü üzenetet)
            await clear_chat_history(context, chat_id, user_id, keep_message_id=sent_message.message_id)

        # Takarítás indítása a háttérben
        asyncio.create_task(cleanup_chat())

    except Exception as e:
        print(f"Hiba a start kezelésben: {e}")

async def show_main_menu(query, user_id):
    """Főmenü megjelenítése"""
    main_menu = []
    main_menu.append([InlineKeyboardButton("📦 Aktuális", callback_data="aktualis")])
    main_menu.append([InlineKeyboardButton("🎯 Akció", callback_data="akcio")])
    main_menu.append([InlineKeyboardButton("📋 Termékek", callback_data="termekek")])

    if user_id in ARUSITO_IDK or user_id == ADMIN_ID:
        main_menu.append([InlineKeyboardButton("⭐ V.I.P.", callback_data="vip")])
        main_menu.append([InlineKeyboardButton("🛒 Rendelés", callback_data="rendeles")])

    if user_id == ADMIN_ID:
        main_menu.append([InlineKeyboardButton("📥 Feltöltés", callback_data="feltoltes")])

    await safe_edit_message(query, "Válassz a menüből:", reply_markup=InlineKeyboardMarkup(main_menu))

async def safe_edit_message(query, text, reply_markup=None, parse_mode=None):
    """Biztonságos üzenet szerkesztés - kezeli a 'Message is not modified' hibát"""
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        if "Message is not modified" in str(e):
            # Ha ugyanaz a tartalom, rövid visszajelzés
            await query.answer("Nincs változás", show_alert=False)
        else:
            # Egyéb hiba esetén újradobjuk
            raise e

async def send_error_and_keep_menu(context, chat_id, session, error_text, return_callback="back_to_main"):
    """Hibaüzenet küldése úgy, hogy a menü megmaradjon"""
    # Hibaüzenet küldése
    error_keyboard = [[InlineKeyboardButton("✅ Értettem", callback_data=return_callback)]]
    error_message = await context.bot.send_message(
        chat_id=chat_id,
        text=error_text,
        reply_markup=InlineKeyboardMarkup(error_keyboard)
    )

    # Hibaüzenet automatikus törlése 10 másodperc után
    asyncio.create_task(delete_message_after_delay(context, chat_id, error_message.message_id, 10))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gomb kezelés - CSAK privát chatben"""
    global akciok, vip, keszlet, termek_leirasok
    try:
        query = update.callback_query
        if not query:
            return

        # FONTOS: Csak privát chatben engedélyezzük a gombokat
        if update.effective_chat.type != "private":
            await query.answer("❌ A menük csak privát chatben működnek! Írj privátban a botnak: /start", show_alert=True)
            return

        await query.answer()

        user_id = query.from_user.id
        actual_user_id = query.from_user.id
        user_name = query.from_user.first_name or "Felhasználó"
        data = query.data
        session = get_user_session(user_id)

        if data == "welcome_ok":
            await show_main_menu(query, actual_user_id)

        elif data == "termekek":
            # Chat takarítás a menü megjelenítése előtt
            chat_id = query.message.chat.id
            
            keyboard = [
                [InlineKeyboardButton("🔸 VapSolo Triple 60K", callback_data="termek_VapSolo")],
                [InlineKeyboardButton("🔸 Elf Bar MoonNight 40K", callback_data="termek_Elf Bar")],
                [InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")]
            ]
            
            # Új üzenet küldése
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text="Válassz terméket a részletes leírásért:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            session["last_menu_message_id"] = sent_message.message_id
            
            # Korábbi üzenetek törlése a háttérben
            asyncio.create_task(clear_chat_history(context, chat_id, actual_user_id, keep_message_id=sent_message.message_id))

        elif data.startswith("termek_"):
            termek = data.split("_", 1)[1]
            if termek == "VapSolo":
                display_name = "VapSolo Triple 60K"
            elif termek == "Elf Bar":
                display_name = "Elf Bar MoonNight 40K"
            else:
                display_name = termek

            leiras = termek_leirasok.get(termek, "Nincs elérhető leírás.")

            keyboard = [[InlineKeyboardButton("✅ Rendben", callback_data="termekek")]]
            if actual_user_id == ADMIN_ID:
                keyboard.append([InlineKeyboardButton("✏️ Módosítás", callback_data=f"termek_modositas_{termek}")])

            await query.edit_message_text(f"**{display_name}**\n\n{leiras}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data.startswith("termek_modositas_") and actual_user_id == ADMIN_ID:
            termek = data.split("_", 2)[2]
            session["state"] = {"mode": "termek_edit", "termek": termek}
            if termek == "VapSolo":
                display_name = "VapSolo Triple 60K"
            elif termek == "Elf Bar":
                display_name = "Elf Bar MoonNight 40K"
            else:
                display_name = termek

            current_leiras = termek_leirasok.get(termek, "")
            keyboard = [[InlineKeyboardButton("❌ Mégsem", callback_data=f"termek_{termek}")]]
            await query.edit_message_text(f"Jelenlegi {display_name} leírás:\n\n{current_leiras}\n\nÍrd be az új leírást:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif data == "aktualis":
            # Chat takarítás a menü megjelenítése előtt
            chat_id = query.message.chat.id
            session = get_user_session(actual_user_id)
            
            # Új menü üzenet küldése
            msg = "📦 **Aktuális készlet:**\n\n"
            for termek, lista in keszlet.items():
                # Teljes termék név megjelenítése
                if termek == "VapSolo":
                    display_name = "VapSolo Triple 60K"
                elif termek == "Elf Bar":
                    display_name = "Elf Bar MoonNight 40K"
                else:
                    display_name = termek
                
                msg += f"**{display_name}**\n"
                msg += f"💰 **Ár:** 10.000 Ft\n\n"
                
                if not lista:
                    msg += "❌ Nincs készleten\n\n"
                else:
                    msg += "📋 **Készleten lévő ízek:**\n"
                    for iz, db in lista.items():
                        msg += f"• {iz}: {db} db\n"
                    msg += "\n"

            keyboard = [[InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")]]
            
            # Új üzenet küldése
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            session["last_menu_message_id"] = sent_message.message_id
            
            # Korábbi üzenetek törlése a háttérben
            asyncio.create_task(clear_chat_history(context, chat_id, actual_user_id, keep_message_id=sent_message.message_id))

        elif data == "akcio":
            # Chat takarítás a menü megjelenítése előtt
            chat_id = query.message.chat.id
            
            keyboard = []
            if actual_user_id == ADMIN_ID:
                keyboard.append([InlineKeyboardButton("✏️ Módosítás", callback_data="akcio_modositas")])
            keyboard.append([InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")])
            
            # Új üzenet küldése
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 **Akciók:**\n\n{akciok}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            session["last_menu_message_id"] = sent_message.message_id
            
            # Korábbi üzenetek törlése a háttérben
            asyncio.create_task(clear_chat_history(context, chat_id, actual_user_id, keep_message_id=sent_message.message_id))

        elif data == "akcio_modositas" and actual_user_id == ADMIN_ID:
            session["state"] = {"mode": "akcio_edit"}
            keyboard = [[InlineKeyboardButton("❌ Mégsem", callback_data="akcio")]]
            await query.edit_message_text(f"Jelenlegi akció:\n\n{akciok}\n\nÍrd be az új akció szövegét:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif data == "vip":
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return

            keyboard = []
            if actual_user_id == ADMIN_ID:
                keyboard.append([InlineKeyboardButton("✏️ Módosítás", callback_data="vip_modositas")])
            keyboard.append([InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")])
            await query.edit_message_text(f"⭐ **V.I.P. ajánlatok:**\n\n{vip}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data == "vip_modositas" and actual_user_id == ADMIN_ID:
            session["state"] = {"mode": "vip_edit"}
            keyboard = [[InlineKeyboardButton("❌ Mégsem", callback_data="vip")]]
            await query.edit_message_text(f"Jelenlegi V.I.P. ajánlat:\n\n{vip}\n\nÍrd be az új V.I.P. ajánlat szövegét:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif data == "rendeles":
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
            
            # Eladási számláló megjelenítése
            current_remainder = get_seller_sales_count(actual_user_id)
            total_sales = get_seller_total_sales(actual_user_id)
            remaining = 10 - current_remainder if current_remainder > 0 else 10
            
            msg = f"🛒 **Rendelési rendszer**\n\n"
            msg += f"📊 **Összes eladás:** {total_sales} db\n"
            msg += f"📊 **Jelenlegi ciklus:** {current_remainder}/10 db\n"
            
            if current_remainder == 0 and total_sales > 0:
                msg += f"🎉 **Gratulálunk! Elérted a 10 db-os limitet!**\n"
                msg += f"✅ Jogosult vagy 1 db ingyen termékre!\n\n"
            else:
                msg += f"💪 Még {remaining} db az ingyen termékig!\n\n"
            
            msg += f"Válassz terméket a rendeléshez:"
            
            keyboard = []
            if keszlet["VapSolo"]:
                keyboard.append([InlineKeyboardButton("🔹 VapSolo Triple 60K", callback_data="rendeles_VapSolo")])
            if keszlet["Elf Bar"]:
                keyboard.append([InlineKeyboardButton("🔹 Elf Bar MoonNight 40K", callback_data="rendeles_Elf Bar")])
            keyboard.append([InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")])
            
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data.startswith("rendeles_") and not data.startswith("rendeles_iz_") and not data.startswith("rendeles_db_") and data not in ["rendeles_meg", "rendeles_confirm", "rendeles_ossz", "rendeles_megsem"]:
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
                
            termek = data.split("_", 1)[1]
            # Többszörös rendelési session struktúra
            if "order_state" not in session:
                session["order_state"] = {"items": [], "current_termek": None}
            session["order_state"]["current_termek"] = termek
            
            # Ízek listázása
            izek = list(keszlet[termek].keys())
            if not izek:
                await query.answer("❌ Ez a termék jelenleg nincs készleten!", show_alert=True)
                return
            
            keyboard = []
            for iz in izek:
                if keszlet[termek][iz] > 0:
                    keyboard.append([InlineKeyboardButton(f"{iz} ({keszlet[termek][iz]} db)", callback_data=f"rendeles_iz_{iz}")])
            keyboard.append([InlineKeyboardButton("❌ Mégsem", callback_data="rendeles")])
            
            display_name = "VapSolo Triple 60K" if termek == "VapSolo" else "Elf Bar MoonNight 40K"
            await safe_edit_message(query, f"🔹 **{display_name}**\n\nVálassz ízt:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data.startswith("rendeles_iz_"):
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
                
            iz = data.split("_", 2)[2]
            if "order_state" not in session or not session["order_state"] or not session["order_state"].get("current_termek"):
                await query.answer("❌ Hiba történt! Kezdd újra a rendelést.", show_alert=True)
                return
                
            termek = session["order_state"]["current_termek"]
            session["order_state"]["current_iz"] = iz
            max_db = keszlet[termek].get(iz, 0)
            
            if max_db <= 0:
                await query.answer("❌ Ez az íz jelenleg nincs készleten!", show_alert=True)
                return
            
            keyboard = []
            # Csak annyi darabszám opció, amennyi készleten van
            for i in range(1, max_db + 1):
                keyboard.append([InlineKeyboardButton(f"{i} db", callback_data=f"rendeles_db_{i}")])
            keyboard.append([InlineKeyboardButton("❌ Mégsem", callback_data="rendeles")])
            
            await safe_edit_message(query, f"🔹 **{iz}**\n\nMennyi darabot szeretnél rendelni?\n(Készleten: {max_db} db)", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data.startswith("rendeles_db_"):
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
                
            db = int(data.split("_", 2)[2])
            if "order_state" not in session or not session["order_state"] or not session["order_state"].get("current_termek") or not session["order_state"].get("current_iz"):
                await query.answer("❌ Hiba történt! Kezdd újra a rendelést.", show_alert=True)
                return
                
            termek = session["order_state"]["current_termek"]
            iz = session["order_state"]["current_iz"]
            
            # Készlet ellenőrzése (de még NEM csökkentjük!)
            if keszlet[termek].get(iz, 0) < db:
                await query.answer("❌ Nincs elegendő készlet!", show_alert=True)
                return
            
            # Order state inicializálása ha szükséges
            if "order_state" not in session:
                session["order_state"] = {"items": [], "current_termek": None}
            if "items" not in session["order_state"]:
                session["order_state"]["items"] = []
            
            # Készlet lefoglalása időlegesen a kosárban
            if "reserved_stock" not in session:
                session["reserved_stock"] = {}
            
            key = (termek, iz)
            if key in session["reserved_stock"]:
                session["reserved_stock"][key] += db
            else:
                session["reserved_stock"][key] = db
                
            # Készletből ideiglenes kivonás
            keszlet[termek][iz] -= db
            if keszlet[termek][iz] <= 0:
                del keszlet[termek][iz]
            
            print(f"Lefoglalva: {termek} {iz} {db} db user {actual_user_id} számára")
            
            # Hozzáadás a kosárhoz
            new_item = {"termek": termek, "iz": iz, "db": db}
            session["order_state"]["items"].append(new_item)
            session["order_state"]["current_iz"] = None  # Töröljük az átmeneti állapotot
            
            # Teljes rendelési összesítő megjelenítése
            display_name = "VapSolo Triple 60K" if termek == "VapSolo" else "Elf Bar MoonNight 40K"
            
            # Aktuális rendelés összesítése
            summary_text, total_qty = build_order_summary(session["order_state"]["items"])
            
            msg = f"✅ **Kosárhoz adva: {iz} - {db} db**\n\n"
            msg += summary_text + "\n\n"
            msg += f"Mit szeretnél csinálni?"
            
            keyboard = [
                [InlineKeyboardButton("➕ Rendelek még", callback_data="rendeles_meg")],
                [InlineKeyboardButton("✅ Véglegesítés", callback_data="rendeles_confirm")],
                [InlineKeyboardButton("❌ Kosár ürítése", callback_data="rendeles_megsem")]
            ]
            await safe_edit_message(query, msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data == "rendeles_meg":
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
            
            # Vissza a termék választáshoz (kosár megtartása)
            current_remainder = get_seller_sales_count(actual_user_id)
            total_sales = get_seller_total_sales(actual_user_id)
            remaining = 10 - current_remainder if current_remainder > 0 else 10
            
            items_count = len(session.get("order_state", {}).get("items", []))
            
            msg = f"🛒 **Rendelési rendszer** (Kosárban: {items_count} tétel)\n\n"
            msg += f"📊 **Összes eladás:** {total_sales} db\n"
            msg += f"📊 **Jelenlegi ciklus:** {current_remainder}/10 db\n"
            
            if current_remainder == 0 and total_sales > 0:
                msg += f"🎉 **Gratulálunk! Elérted a 10 db-os limitet!**\n"
                msg += f"✅ Jogosult vagy 1 db ingyen termékre!\n\n"
            else:
                msg += f"💪 Még {remaining} db az ingyen termékig!\n\n"
            
            msg += f"Válassz terméket a rendeléshez:"
            
            keyboard = []
            if keszlet["VapSolo"]:
                keyboard.append([InlineKeyboardButton("🔹 VapSolo Triple 60K", callback_data="rendeles_VapSolo")])
            if keszlet["Elf Bar"]:
                keyboard.append([InlineKeyboardButton("🔹 Elf Bar MoonNight 40K", callback_data="rendeles_Elf Bar")])
            keyboard.append([InlineKeyboardButton("🧾 Kosár", callback_data="rendeles_ossz")])
            keyboard.append([InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")])
            
            await safe_edit_message(query, msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data == "rendeles_ossz":
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
            
            items = session.get("order_state", {}).get("items", [])
            if not items:
                await query.answer("❌ A kosár üres!", show_alert=True)
                return
            
            summary_text, total_qty = build_order_summary(items)
            
            keyboard = [
                [InlineKeyboardButton("✅ Véglegesítés", callback_data="rendeles_confirm")],
                [InlineKeyboardButton("➕ Rendelek még", callback_data="rendeles_meg")],
                [InlineKeyboardButton("❌ Kosár ürítése", callback_data="rendeles_megsem")]
            ]
            await safe_edit_message(query, summary_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data == "rendeles_megsem":
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
            
            # Lefoglalt készlet felszabadítása
            release_reserved_stock(actual_user_id)
            
            # Kosár ürítése
            session["order_state"] = {"items": [], "current_termek": None}
            
            msg = "🗑️ **Kosár ürítve!**\n\nMit szeretnél csinálni?"
            keyboard = [
                [InlineKeyboardButton("🛒 Új rendelés", callback_data="rendeles")],
                [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
            ]
            await safe_edit_message(query, msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data == "rendeles_confirm":
            if actual_user_id not in ARUSITO_IDK and actual_user_id != ADMIN_ID:
                await query.answer("❌ Nincs jogosultságod ehhez!", show_alert=True)
                return
                
            items = session.get("order_state", {}).get("items", [])
            if not items:
                await query.answer("❌ A kosár üres!", show_alert=True)
                return
            
            # Csoportosítás és készlet ellenőrzés
            grouped = {}
            for item in items:
                key = (item["termek"], item["iz"])
                if key not in grouped:
                    grouped[key] = 0
                grouped[key] += item["db"]
            
            # Készlet ellenőrzése minden tételre (reserved stock figyelembevételével)
            shortages = []
            reserved = session.get("reserved_stock", {})
            for (termek, iz), needed_qty in grouped.items():
                # A jelenlegi készlet + ez a felhasználó lefoglalt készlete 
                available = keszlet[termek].get(iz, 0) + reserved.get((termek, iz), 0)
                if available < needed_qty:
                    shortages.append(f"• {iz}: {needed_qty} db kell, {available} db van")
            
            if shortages:
                error_msg = "❌ **Nincs elegendő készlet!**\n\n" + "\n".join(shortages)
                error_msg += "\n\nKérlek módosítsd a rendelést."
                keyboard = [[InlineKeyboardButton("🧾 Vissza az összesítőhöz", callback_data="rendeles_ossz")]]
                await safe_edit_message(query, error_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                return
            
            # Összesített mennyiség számítása (a készlet már le van csökkentve a kosárba rakáskor)
            total_qty = 0
            for (termek, iz), qty in grouped.items():
                total_qty += qty
            
            # Eladási számláló növelése
            current_count, delta_awards, total_sold = increment_seller_sales(actual_user_id, total_qty)
            
            # Értesítések
            seller_name = query.from_user.first_name or "Ismeretlen"
            summary_text, _ = build_order_summary(items)
            
            # Admin értesítés
            admin_msg = f"📦 **ÚJ ÖSSZEVONT RENDELÉS**\n\n"
            admin_msg += f"👤 **Árusító:** {seller_name} (ID: {actual_user_id})\n\n"
            admin_msg += summary_text.replace("🛒 **Rendelési összesítő:**", "**Rendelt termékek:**")
            admin_msg += f"\n\n📊 **Árusító jelenlegi:** {current_count}/10 db"
            admin_msg += f"\n📊 **Összes eladás:** {total_sold} db"
            
            if delta_awards > 0:
                if delta_awards == 1:
                    admin_msg += f"\n\n🎉 **FIGYELEM:** {seller_name} elérte a 10 db-os limitet!"
                    admin_msg += f"\n✅ Jogosult 1 db ingyen termékre!"
                else:
                    admin_msg += f"\n\n🎉 **FIGYELEM:** {seller_name} {delta_awards} alkalommal érte el a 10 db-os limitet!"
                    admin_msg += f"\n✅ Jogosult {delta_awards} db ingyen termékre!"
            
            await send_private_message(context, ADMIN_ID, admin_msg)
            
            # Árusító értesítés
            if delta_awards > 0:
                if delta_awards == 1:
                    seller_msg = f"📈 **Rendelés véglegesítve!**\n\n🎉 **Gratulálunk!**\nElérted a 10 db-os limitet!\n✅ Jogosult vagy 1 db ingyen termékre!"
                    seller_msg += f"\n\n🔄 **Új ciklus:** {current_count}/10 db\n📊 **Összes eladás:** {total_sold} db\nVedd fel a kapcsolatot az adminnal!"
                else:
                    seller_msg = f"📈 **Rendelés véglegesítve!**\n\n🎉 **SZUPER GRATULÁLUNK!**\n{delta_awards} alkalommal érted el a 10 db-os limitet!\n✅ Jogosult vagy {delta_awards} db ingyen termékre!"
                    seller_msg += f"\n\n🔄 **Új ciklus:** {current_count}/10 db\n📊 **Összes eladás:** {total_sold} db\nVedd fel a kapcsolatot az adminnal!"
            else:
                seller_msg = f"📈 **Rendelés véglegesítve!**\n\n📊 **Összes eladás:** {total_sold} db"
                seller_msg += f"\n📊 **Jelenlegi ciklus:** {current_count}/10 db"
                remaining = 10 - current_count if current_count > 0 else 10
                seller_msg += f"\nMég {remaining} db az ingyen termékig! 💪"
            
            await send_private_message(context, actual_user_id, seller_msg)
            
            # Visszajelzés a chatben
            success_msg = f"✅ **Rendelés sikeresen véglegesítve!**\n\n{summary_text.replace('🛒 **Rendelési összesítő:**', '📦 **Leadott rendelés:**')}"
            
            keyboard = [
                [InlineKeyboardButton("🛒 Új rendelés", callback_data="rendeles")],
                [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
            ]
            await safe_edit_message(query, success_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            
            # Lefoglalt készlet törlése (mert már le van vonva a végleges készletből)
            session["reserved_stock"] = {}
            
            # Session törlése
            session["order_state"] = {}

        elif data == "feltoltes" and actual_user_id == ADMIN_ID:
            keyboard = []
            keyboard.append([InlineKeyboardButton("🔹 VapSolo Triple 60K", callback_data="feltoltes_VapSolo")])
            keyboard.append([InlineKeyboardButton("🔹 Elf Bar MoonNight 40K", callback_data="feltoltes_Elf Bar")])
            keyboard.append([InlineKeyboardButton("⬅️ Vissza", callback_data="back_to_main")])
            await query.edit_message_text("📥 **Készlet feltöltés**\n\nVálassz terméket:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data.startswith("feltoltes_") and actual_user_id == ADMIN_ID:
            termek = data.split("_", 1)[1]
            session["state"] = {"mode": "stock_add", "termek": termek}
            display_name = "VapSolo Triple 60K" if termek == "VapSolo" else "Elf Bar MoonNight 40K"
            
            keyboard = [[InlineKeyboardButton("❌ Mégsem", callback_data="feltoltes")]]
            await query.edit_message_text(f"📥 **{display_name} feltöltés**\n\nÍrd be az íz nevét:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif data == "back_to_main":
            await show_main_menu(query, actual_user_id)

    except Exception as e:
        try:
            data_str = data if 'data' in locals() else "UNKNOWN"
            print(f"Hiba a gomb kezelésben - Data: {data_str}, Error: {e}")
            
            # Ha van query és user_id, térjünk vissza a főmenüre
            if 'query' in locals() and 'actual_user_id' in locals():
                await show_main_menu(query, actual_user_id)
        except Exception as ex:
            print(f"Exception handling hiba: {ex}")
            pass

async def handle_text_message(update, context):
    """Szöveges üzenetek kezelése"""
    global akciok, vip, keszlet, termek_leirasok
    
    if not update.effective_user or not update.message:
        return
        
    user_id = update.effective_user.id
    message_text = update.message.text
    session = get_user_session(user_id)
    
    # Csak admin és árusítók szöveges üzenetei
    if user_id not in ARUSITO_IDK and user_id != ADMIN_ID:
        return
    
    if "state" not in session or not session["state"]:
        return
    
    state = session["state"]
    
    try:
        # Termék leírás szerkesztése
        if state.get("mode") == "termek_edit":
            termek = state.get("termek")
            if termek and user_id == ADMIN_ID:
                termek_leirasok[termek] = message_text
                
                display_name = "VapSolo Triple 60K" if termek == "VapSolo" else "Elf Bar MoonNight 40K"
                
                # Felhasználó üzenetének törlése
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                except Exception:
                    pass
                
                # Menü frissítése a session-ben tárolt üzenettel
                if "last_menu_message_id" in session and session["last_menu_message_id"]:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=session["last_menu_message_id"],
                            text=f"✅ **{display_name}** leírás frissítve!\n\nVálassz a menüből:",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📋 Termékek", callback_data="termekek")],
                                [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
                            ])
                        )
                    except Exception:
                        # Ha nem sikerül a szerkesztés, új üzenet küldése
                        new_message = await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"✅ **{display_name}** leírás frissítve!\n\nVálassz a menüből:",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📋 Termékek", callback_data="termekek")],
                                [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
                            ])
                        )
                        session["last_menu_message_id"] = new_message.message_id
                session["state"] = {}
        
        # Akció szerkesztése
        elif state.get("mode") == "akcio_edit" and user_id == ADMIN_ID:
            akciok = message_text
            
            # Felhasználó üzenetének törlése
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
            except Exception:
                pass
            
            # Menü frissítése
            if "last_menu_message_id" in session and session["last_menu_message_id"]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=session["last_menu_message_id"],
                        text="✅ **Akció frissítve!**\n\nVálassz a menüből:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎯 Akció", callback_data="akcio")],
                            [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
                        ])
                    )
                except Exception:
                    new_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="✅ **Akció frissítve!**\n\nVálassz a menüből:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎯 Akció", callback_data="akcio")],
                            [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
                        ])
                    )
                    session["last_menu_message_id"] = new_message.message_id
            session["state"] = {}
        
        # VIP szerkesztése
        elif state.get("mode") == "vip_edit" and user_id == ADMIN_ID:
            vip = message_text
            
            # Felhasználó üzenetének törlése
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
            except Exception:
                pass
            
            # Menü frissítése
            if "last_menu_message_id" in session and session["last_menu_message_id"]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=session["last_menu_message_id"],
                        text="✅ **V.I.P. ajánlat frissítve!**\n\nVálassz a menüből:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⭐ V.I.P.", callback_data="vip")],
                            [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
                        ])
                    )
                except Exception:
                    new_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="✅ **V.I.P. ajánlat frissítve!**\n\nVálassz a menüből:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⭐ V.I.P.", callback_data="vip")],
                            [InlineKeyboardButton("🏠 Főmenü", callback_data="back_to_main")]
                        ])
                    )
                    session["last_menu_message_id"] = new_message.message_id
            session["state"] = {}
        
        # Készlet feltöltés - íz neve
        elif state.get("mode") == "stock_add" and user_id == ADMIN_ID:
            termek = state.get("termek")
            if termek:
                session["state"]["iz"] = message_text
                session["state"]["mode"] = "stock_add_quantity"
                
                keyboard = [[InlineKeyboardButton("❌ Mégsem", callback_data="feltoltes")]]
                await update.message.reply_text(
                    f"📦 **{message_text}** - Mennyiség megadása\n\nÍrd be a darabszámot:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        
        # Készlet feltöltés - mennyiség
        elif state.get("mode") == "stock_add_quantity" and user_id == ADMIN_ID:
            try:
                quantity = int(message_text)
                if quantity <= 0:
                    await update.message.reply_text("❌ A mennyiség csak pozitív szám lehet!")
                    return
                
                termek = state.get("termek")
                iz = state.get("iz")
                
                if termek and iz:
                    if iz in keszlet[termek]:
                        keszlet[termek][iz] += quantity
                    else:
                        keszlet[termek][iz] = quantity
                    
                    display_name = "VapSolo Triple 60K" if termek == "VapSolo" else "Elf Bar MoonNight 40K"
                    
                    keyboard = [[InlineKeyboardButton("✅ Rendben", callback_data="feltoltes")]]
                    await update.message.reply_text(
                        f"✅ **Készlet frissítve!**\n\n{display_name}\n{iz}: {keszlet[termek][iz]} db",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                    session["state"] = {}
                    
            except ValueError:
                await update.message.reply_text("❌ Kérlek, csak számot írj be!")
    
    except Exception as e:
        print(f"Hiba a szöveges üzenet kezelésben: {e}")
        session["state"] = {}

# Main function
if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    print("Bot elindult...")
    application.run_polling()