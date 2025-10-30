import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
import openai

# 🔐 المتغيرات البيئية (يتم جلبها من Railway Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 🚨 مفاتيح البحث الذكي
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CX_ID = os.environ.get("GOOGLE_SEARCH_CX_ID")

# إعداد OpenAI
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# إعدادات التسجيل
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ثوابت وإعدادات الملفات ---
MAX_FILE_SIZE = 50 * 1024 * 1024 # 50 ميجابايت كحد أقصى لملفات البوت
ALLOWED_CONTENT_TYPE = 'application/pdf'

# ----------------------------------------------------------------------
# 🌐 دوال البحث والجلب الأساسية
# ----------------------------------------------------------------------

# --- دالة البحث الذكي عن رابط التحميل باستخدام Google Search API ---
def smart_google_search(book_title: str):
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_CX_ID:
        return None, "يرجى إعداد مفاتيح Google Search API في المتغيرات البيئية."
    
    # البحث عن الكتاب مع تحديد نوع الملف PDF
    search_query = f'"{book_title}" filetype:pdf تحميل مجاني'
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': GOOGLE_SEARCH_API_KEY,
        'cx': GOOGLE_SEARCH_CX_ID,
        'q': search_query,
        'num': 5  # جلب 5 نتائج محتملة
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('items', [])
        if not results:
            return None, "لم يتم العثور على أي نتائج تحميل مباشرة (PDF) لبحثك."

        # إعداد البيانات لإرسالها إلى الذكاء الاصطناعي
        search_snippets = ""
        for i, item in enumerate(results):
            search_snippets += f"نتيجة {i+1}: {item.get('title')}\n الرابط: {item.get('link')}\n"

        return results, search_snippets
        
    except Exception as e:
        logger.error(f"خطأ في Google Search API: {e}")
        return None, "حدث خطأ أثناء الاتصال بخدمة بحث جوجل."

# --- دالة اختيار أفضل رابط بالذكاء الاصطناعي ---
def select_best_link_with_ai(book_title: str, snippets: str):
    if not OPENAI_API_KEY:
        return None
    
    prompt = (
        f"المهمة: أنت خبير في تحديد روابط تحميل الكتب. بناءً على نتائج البحث التالية، اختر *الرابط الوحيد الأفضل* الذي من المرجح أن يؤدي مباشرة إلى ملف PDF للكتاب بعنوان: '{book_title}'.\n"
        f"المتطلبات: يجب أن تكون الإجابة عبارة عن الرابط الصافي فقط، بدون أي نص إضافي أو شرح.\n\n"
        f"نتائج البحث:\n{snippets}"
    )
    
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "أنت مساعد متخصص ومختصر مهمتك الوحيدة هي استخراج رابط واحد صافي."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.1
        )
        link = response.choices[0].message.content.strip()
        
        if link.startswith("http"):
            return link
        else:
            return None
            
    except Exception as e:
        logger.error(f"خطأ في OpenAI API أثناء الاختيار: {e}")
        return None
        
# ----------------------------------------------------------------------
# ✨ دوال الذكاء الاصطناعي الثورية (الردود / المحتوى)
# ----------------------------------------------------------------------

# --- دالة توليد المحتوى (نبذة / خطة قراءة) باستخدام الذكاء الاصطناعي ---
def generate_ai_content(book_title: str, mode: str):
    if not OPENAI_API_KEY:
        return f"({mode} غير متوفرة: مفتاح OpenAI غير موجود.)"
    
    if mode == "summary":
        system_role = "أنت مساعد متخصص في تلخيص الكتب بشكل موجز وجذاب."
        user_prompt = f"اكتب نبذة مُلهمة وجذابة عن كتاب بعنوان: '{book_title}'. يجب ألا تتجاوز النبذة 100 كلمة."
        max_tokens = 250
    
    elif mode == "reading_plan":
        system_role = "أنت مدرب قراءة متخصص في إنشاء خطط زمنية مرنة."
        user_prompt = (
            f"أنشئ خطة قراءة مُنظمة ومحفزة لمدة 10 أيام لقراءة كتاب بعنوان: '{book_title}'."
            f"قسم الكتاب إلى جلسات يومية قابلة للتطبيق مع تحديد هدف لكل جلسة (مثلاً: الفصل الأول والثاني). "
            f"اجعل تنسيق الإخراج سهل القراءة باستخدام العناوين والأرقام ورموز الإيموجي المناسبة."
        )
        max_tokens = 1024
    else:
        return "وضع غير معروف."

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"خطأ في OpenAI API أثناء توليد {mode}: {e}")
        return f"عذراً، حدث خطأ أثناء توليد {mode} للكتاب."

# --- دالة توليد رسالة الفشل بالذكاء الاصطناعي (مخصصة للمكتبات العربية) ---
def generate_failure_response(book_title: str, reason: str):
    if not OPENAI_API_KEY:
        return f"عذراً، لم أتمكن من العثور على رابط مباشر لكتاب '{book_title}'. السبب التقني: {reason}"
    
    system_role = (
        "أنت مساعد مكتبة رقمي محترف ولبق. مهمتك هي الاعتذار للمستخدم عن عدم توفر كتاب، "
        "وتقديم تفسير موجز يركز على حقوق النشر وتحديات التوفر. "
        "يجب أن تشير في ردك إلى أن المشكلة قد تكون مرتبطة بالقيود المفروضة على النشر الرقمي من قبل "
        "المكتبات الكبرى التي تنشر الكتب العربية (مثل: مكتبة نور، مكتبة الكتي، كتوباتي). "
        "يجب أن يكون الرد دافئاً ومهنياً وألا يتجاوز ثلاثة جمل."
    )
    user_prompt = (
        f"أبحث عن كتاب بعنوان: '{book_title}'. لم يتمكن البوت من إيجاده أو إرساله. "
        f"السبب التقني التقريبي هو: {reason}"
    )

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=200, 
            temperature=0.7 
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"خطأ في OpenAI API أثناء توليد رسالة الفشل: {e}")
        return f"عذراً، لم أتمكن من العثور على رابط مباشر لكتاب '{book_title}'. هناك مشكلة في الاتصال بالخدمات الذكية."
        
# ----------------------------------------------------------------------
# 🤖 دوال تليجرام الرئيسية
# ----------------------------------------------------------------------

# --- دالة أمر /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "مرحباً بك في بوت المكتبة الثورية! 📚\n"
        "أرسل لي اسم الكتاب وسأقوم بما يلي:\n"
        "1. البحث بذكاء عن رابط التحميل المباشر.\n"
        "2. إرسال الملف (إذا كان مسموحاً وأقل من 50 ميجابايت).\n"
        "3. إرسال **نبذة ذكية** و**خطة قراءة مخصصة**."
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


# --- دالة إرسال الملف بعد التحقق والإجراءات اللاحقة ---
async def send_document_if_valid(update: Update, context: ContextTypes.DEFAULT_TYPE, best_link: str, book_title: str):
    
    await update.message.reply_text(f"جاري محاولة جلب وإرسال ملف الكتاب *{book_title}*، الرجاء الانتظار قليلاً...", parse_mode='Markdown')

    try:
        # 1. محاولة جلب الملف
        with requests.get(best_link, stream=True, timeout=30) as r:
            r.raise_for_status()
            
            # التحقق من نوع المحتوى وحجم الملف
            content_type = r.headers.get('Content-Type', '').split(';')[0]
            content_length = int(r.headers.get('Content-Length', 0))

            if ALLOWED_CONTENT_TYPE not in content_type and 'application/octet-stream' not in content_type:
                 await update.message.reply_text(f"❌ فشل: الرابط المحدد لا يشير مباشرة إلى ملف PDF، بل يشير إلى صفحة ويب أو نوع ملف غير مدعوم ({content_type}).")
                 return
            
            if content_length > MAX_FILE_SIZE and content_length != 0:
                await update.message.reply_text(f"❌ فشل: حجم الملف أكبر من الحد الأقصى المسموح به (50 ميجابايت).")
                return

            # 2. إرسال الملف عبر تليجرام
            await update.message.reply_document(
                document=r.raw, 
                filename=f"{book_title}.pdf",
                caption=f"✅ تم إرسال ملف *{book_title}* بناءً على البحث الذكي.",
                parse_mode='Markdown'
            )
            
            # 3. الإضافة الثورية الجديدة: إرسال المحتوى الذكي
            
            # أ. توليد وإرسال النبذة
            summary_text = generate_ai_content(book_title, "summary")
            await update.message.reply_text(
                f"🌟 *نبذة عن الكتاب: {book_title}* 🌟\n\n"
                f"{summary_text}",
                parse_mode='Markdown'
            )

            # ب. توليد وإرسال خطة القراءة
            reading_plan_text = generate_ai_content(book_title, "reading_plan")
            await update.message.reply_text(
                f"🗓️ *خطة القراءة المقترحة لـ {book_title}* 🗓️\n"
                f"--- (مدة الخطة 10 أيام) ---\n\n"
                f"{reading_plan_text}",
                parse_mode='Markdown'
            )
            
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في تحميل الملف: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء محاولة تحميل الملف من الرابط المختار. قد يكون الرابط غير صالح أو محجوب.")
    except Exception as e:
        logger.error(f"خطأ عام أثناء الإرسال: {e}")
        await update.message.reply_text("❌ عذراً، حدث خطأ غير متوقع أثناء إرسال الملف.")


# --- دالة معالجة الرسائل الرئيسية (MessageHandler) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text
    
    await update.message.reply_text(f"جاري البحث الذكي عن الكتاب: *{user_query}*...", parse_mode='Markdown')

    # 1. البحث في جوجل والحصول على النتائج
    results, search_error = smart_google_search(user_query) 

    if search_error:
        # الفشل الأول: فشل في الاتصال بالخدمات
        ai_failure_response = generate_failure_response(user_query, search_error)
        await update.message.reply_text(ai_failure_response, parse_mode='Markdown')
        return

    # 2. تحليل النتائج بالذكاء الاصطناعي لاختيار الرابط الأفضل
    snippets = search_error # يجب أن تكون search_error الآن تحمل بيانات النتائج if results is not None
    best_link = select_best_link_with_ai(user_query, snippets)

    if best_link:
        # 3. محاولة جلب وإرسال الملف مباشرة
        await send_document_if_valid(update, context, best_link, user_query)
        
    else:
        # الفشل الثاني: الذكاء الاصطناعي لم يختر رابطاً موثوقاً
        reason = "الذكاء الاصطناعي لم يتمكن من تحديد رابط تحميل PDF موثوق به من بين نتائج البحث."
        ai_failure_response = generate_failure_response(user_query, reason)
        
        # إرسال الرد المخصص والمولّد بالذكاء الاصطناعي
        await update.message.reply_text(ai_failure_response, parse_mode='Markdown')


# --- الدالة الرئيسية لتشغيل البوت ---
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("لم يتم العثور على رمز التوكن (TELEGRAM_BOT_TOKEN). الرجاء إضافته كمتغير بيئي.")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)) 

    logger.info("البوت يعمل الآن بنظام البحث الذكي الثوري...")
    application.run_polling()

if __name__ == '__main__':
    main()
