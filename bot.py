import os
import re
import io
import cv2
import pytesseract
from pyzbar.pyzbar import decode
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import pandas as pd

TOKEN = os.environ["BOT_TOKEN"]
DATA_FILE = "data.xlsx"

def read_image(data):
    arr = cv2.imdecode(__import__("numpy").frombuffer(data, dtype="uint8"), cv2.IMREAD_COLOR)
    return arr

def extract_barcode(img):
    results = decode(img)
    for r in results:
        try:
            return r.data.decode("utf-8")
        except:
            pass
    # Try grayscale/upscaled image
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    for r in decode(gray):
        try:
            return r.data.decode("utf-8")
        except:
            pass
    return ""

def ocr_text(img):
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return pytesseract.image_to_string(Image.fromarray(rgb), config="--psm 6")

def parse_fields(img, text):
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    code = ""
    for line in lines:
        m = re.search(r"\b[A-Z0-9]{5,}\b", line.upper())
        if m and any(c.isalpha() for c in m.group()):
            code = m.group()
            break

    name = ""
    for line in lines:
        up = line.upper()
        if any(k in up for k in ["ARTO ", "LION ", "PURO "]):
            name = line
            break

    price = 0
    for line in reversed(lines):
        nums = re.findall(r"\b\d[\d\s.,]{3,}\b", line)
        for n in nums:
            digits = re.sub(r"\D", "", n)
            if len(digits) >= 4:
                value = int(digits)
                if value >= 10000:
                    price = value
                    break
        if price:
            break

    # Quantity is usually the small standalone number near the left of the label.
    qty = 0
    for line in lines:
        if re.fullmatch(r"\d{1,3}", line):
            n = int(line)
            if 1 <= n <= 999:
                qty = n
                break

    barcode = extract_barcode(img)
    return code, barcode, name, price, qty

def save_row(row):
    if os.path.exists(DATA_FILE):
        df = pd.read_excel(DATA_FILE)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_excel(DATA_FILE, index=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! 📸 Mahsulot yorlig‘ining rasmini yuboring.\n"
        "Men kod, shtrix-kod, nomi, narxi va sonini aniqlab, tasdiqlashingizni so‘rayman."
    )

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔎 Rasm o‘qilmoqda...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    data = bytes(await file.download_as_bytearray())
    img = read_image(data)
    text = ocr_text(img)
    code, barcode, name, price, qty = parse_fields(img, text)

    row = {
        "Kod": code,
        "Shtrix-kod": barcode,
        "Mahsulot nomi": name,
        "Narx": price,
        "Soni": qty,
    }
    context.user_data["pending"] = row

    shown = (
        f"🏷 Kod: {code or 'topilmadi'}\n"
        f"🔢 Shtrix-kod: {barcode or 'topilmadi'}\n"
        f"📝 Nomi: {name or 'topilmadi'}\n"
        f"💰 Narxi: {price:,} so‘m\n"
        f"📦 Soni: {qty or 'topilmadi'}\n\n"
        "Ma’lumotlar to‘g‘rimi?"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")
    ]]
    await msg.edit_text(shown, reply_markup=InlineKeyboardMarkup(keyboard))

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm":
        row = context.user_data.pop("pending", None)
        if not row:
            await query.edit_message_text("Ma’lumot topilmadi.")
            return
        save_row(row)
        await query.edit_message_text("✅ Saqlandi! Keyingi rasmni yuborishingiz mumkin.")
    else:
        context.user_data.pop("pending", None)
        await query.edit_message_text("❌ Bekor qilindi. Yangi rasm yuboring.")

async def excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(DATA_FILE):
        await update.message.reply_text("Hali tasdiqlangan ma’lumot yo‘q.")
        return
    with open(DATA_FILE, "rb") as f:
        await update.message.reply_document(document=f, caption="📊 Tayyor Excel fayl")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("excel", excel))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(CallbackQueryHandler(buttons))
    app.run_polling()

if __name__ == "__main__":
    main()
