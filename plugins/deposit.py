import asyncio
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply, CallbackQuery, Message
from config import ADMINS, PAYMENT_UPI_ID, BINANCE_ID, TRC20_ADDRESS, ADMIN_GROUP_ID
from database import get_user, update_balance, create_deposit, get_deposit, add_user, check_referral_milestone
from utils import format_price

deposit_session = {}

def clear_deposit_session(user_id):
    if user_id in deposit_session:
        del deposit_session[user_id]

async def safe_deposit_menu(client, message_or_callback):
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇳 UPI (Manual)", callback_data="pay_upi")],
        [InlineKeyboardButton("🪙 Crypto (Manual)", callback_data="pay_crypto")],
        [InlineKeyboardButton("🔙 Back to Home", callback_data="home")]
    ])
    user_id = message_or_callback.from_user.id
    
    try:
        clear_deposit_session(user_id)
        is_callback = isinstance(message_or_callback, CallbackQuery)
        msg = message_or_callback.message if is_callback else message_or_callback

        try:
            user = await get_user(user_id)
            if not user:
                await add_user(user_id, message_or_callback.from_user.first_name)
                user = await get_user(user_id)

            raw_balance = user.get("balance", 0)
            if isinstance(raw_balance, str):
                try: balance_val = float(raw_balance)
                except: balance_val = 0.0
            else:
                balance_val = float(raw_balance)
        except Exception:
            balance_val = 0.0

        text = (
            f"<b>🏦 ADD FUNDS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Wallet Balance:</b> {format_price(balance_val)}\n\n"
            "👇 <b>Select Payment Method:</b>"
        )

        if is_callback:
            try:
                await msg.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)
            except Exception:
                try: await msg.delete()
                except: pass 
                await client.send_message(user_id, text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)
        else:
            await msg.reply_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)

    except Exception:
        text_fallback = "<b>🏦 ADD FUNDS</b>\n👇 Select Payment Method:"
        try:
            await client.send_message(user_id, text_fallback, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)
        except: pass

@Client.on_message(filters.command("deposit"))
async def deposit_command(c, msg):
    await safe_deposit_menu(c, msg)

@Client.on_callback_query(filters.regex("deposit_home"))
async def deposit_callback(c, cb):
    await safe_deposit_menu(c, cb)

@Client.on_callback_query(filters.regex("pay_upi"))
async def pay_upi(c, cb):
    user_id = cb.from_user.id
    clear_deposit_session(user_id)
    qr_image_url = "https://i.ibb.co/NdM8BQV6/BHARATPE-QR-1.png"
    
    text = (
        "<b>💳 UPI PAYMENT (Manual)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>UPI ID:</b> <code>{PAYMENT_UPI_ID}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>STEPS TO PAY:</b>\n"
        "1️⃣ Scan QR or Copy UPI ID.\n"
        "2️⃣ Pay any amount you want.\n"
        "3️⃣ Take a screenshot of successful payment.\n"
        "4️⃣ Click 'Upload Screenshot' below."
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Screenshot", callback_data="submit_proof_upi")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="deposit_home")]
    ])
    
    try: await cb.message.delete()
    except: pass
    
    await c.send_photo(user_id, photo=qr_image_url, caption=text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)

@Client.on_callback_query(filters.regex("pay_crypto"))
async def pay_crypto(c, cb):
    user_id = cb.from_user.id
    clear_deposit_session(user_id)
    
    text = (
        "<b>🪙 CRYPTO DEPOSIT (USDT)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🆔 Binance Pay ID:</b>\n"
        f"<code>{BINANCE_ID}</code>\n\n"
        "<b>🔗 USDT TRC20 Address:</b>\n"
        f"<code>{TRC20_ADDRESS}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>Min Deposit:</b> $1\n"
        "👇 <b>After payment, upload screenshot below.</b>"
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Screenshot", callback_data="submit_proof_crypto")],
        [InlineKeyboardButton("🔙 Back", callback_data="deposit_home")]
    ])
    
    try:
        await cb.message.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)
    except:
        try: await cb.message.delete()
        except: pass
        await c.send_message(user_id, text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)

@Client.on_callback_query(filters.regex(r"submit_proof_(upi|crypto)"))
async def ask_proof(c, cb):
    user_id = cb.from_user.id
    method = cb.data.split("_")[2]
    deposit_session[user_id] = {"mode": "waiting_proof", "method": method, "menu_id": cb.message.id}
    
    try: await cb.message.delete()
    except: pass
    
    sent = await c.send_message(
        user_id, 
        f"<b>📸 SUBMIT PROOF ({method.upper()})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send the payment screenshot now.\n"
        "<i>Make sure the transaction ID is visible.</i>",
        reply_markup=ForceReply(placeholder="Send Image..."),
        parse_mode=enums.ParseMode.HTML
    )
    deposit_session[user_id]["menu_id"] = sent.id

@Client.on_message(filters.reply & (filters.photo | filters.document), group=2)
async def handle_proof(c, msg):
    user_id = msg.from_user.id
    if user_id not in deposit_session: return
    state = deposit_session[user_id]
    if state.get("mode") != "waiting_proof": return

    method = state.get("method", "UNKNOWN").upper()
    
    caption = (
        f"<b>🏦 NEW DEPOSIT ({method})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {msg.from_user.mention} (`{user_id}`)\n"
        f"📅 <b>Date:</b> {msg.date}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Verify & Approve:</b>"
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Add Funds", callback_data=f"admin_approve_{user_id}_{method.lower()}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{user_id}")]
    ])
    
    try:
        if msg.photo:
            await c.send_photo(ADMIN_GROUP_ID, photo=msg.photo.file_id, caption=caption, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
        else:
            await c.send_document(ADMIN_GROUP_ID, document=msg.document.file_id, caption=caption, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
        await msg.reply_text("✅ <b>Proof Submitted!</b>\nWait for admin approval.", parse_mode=enums.ParseMode.HTML)
        clear_deposit_session(user_id)
    except Exception as e:
        await msg.reply_text(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex(r"admin_approve_(\d+)_(.+)"))
async def admin_approve_ask(c, cb):
    data = cb.data.split("_")
    user_id = data[2]
    ref_id = data[3]
    
    await cb.message.reply_text(
        f"<b>💰 CREDIT AMOUNT (INR)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"User ID: `{user_id}`\n"
        f"Ref: `{ref_id}`\n\n"
        "👇 <i>Reply with amount (e.g. 500):</i>",
        reply_markup=ForceReply(selective=True),
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.reply & filters.regex(r"^\d+$") & filters.chat(ADMIN_GROUP_ID))
async def admin_finalize_deposit(c, msg):
    if msg.reply_to_message and "CREDIT AMOUNT" in msg.reply_to_message.text:
        try:
            target_user_id = int(msg.reply_to_message.text.split("User ID: `")[1].split("`")[0])
            amount = int(msg.text)
            
            await update_balance(target_user_id, amount)
            
            referrer_id = await check_referral_milestone(target_user_id, amount)
            if referrer_id:
                try:
                    await c.send_message(referrer_id, f"🎉 <b>Referral Bonus!</b>\nYour invitee deposited funds.\n💰 <b>You got:</b> ₹20")
                except: pass
            
            await create_deposit(target_user_id, amount, "admin_manual", "manual", "success")
            
            await msg.reply_text(f"✅ <b>Done!</b> Added ₹{amount} to `{target_user_id}`.")
            
            try:
                await c.send_message(
                    target_user_id,
                    f"<b>✅ DEPOSIT APPROVED!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>Credited:</b> ₹{amount}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "<i>Use /start to check balance.</i>",
                    parse_mode=enums.ParseMode.HTML
                )
            except: pass
            
        except Exception as e:
            await msg.reply_text(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex(r"admin_reject_(\d+)"))
async def admin_reject(c, cb):
    user_id = cb.data.split("_")[2]
    
    try:
        await c.send_message(user_id, "❌ <b>Deposit Rejected.</b>\nReason: Invalid proof or payment not found.")
    except: pass
    
    await cb.message.edit_caption(cb.message.caption + "\n\n🚫 <b>REJECTED BY ADMIN</b>")
