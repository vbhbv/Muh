import os
import logging
import requests
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from openai import OpenAI

# ----------------------------------------------------------------------
# 1. إعدادات المتغيرات والمفاتيح
# ----------------------------------------------------------------------

# تم توحيد الأسماء إلى الأحرف الكبيرة والخطوط السفلية (التنسيق القياسي)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY") 
GOOGLE_SEARCH_CX_ID = os.environ.get("GOOGLE_SEARCH_CX_ID") 

# إعدادات التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعداد عميل OpenAI
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    logger.warning("❌ مفتاح OPENAI_API_KEY غير موجود. سيتم تعطيل ميزة الملخصات الذكية.")

# ----------------------------------------------------------------------
# 2. دوال المساعدة (AI & Google Search)
# ----------------------------------------------------------------------

def _perform_search_stage(query: str):
    """
    تنفذ عملية البحث الفعلية باستخدام Google Custom Search API.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': GOOGLE_SEARCH_API_KEY,
        'cx': GOOGLE_SEARCH_CX_ID,
        'q': query,
        'num': 10 # زيادة عدد النتائج إلى 10
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        return data.get('items', [])
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في طلب Google Search API: {e}")
        return []
    except Exception as e:
        logger.error(f"خطأ غير متوقع أثناء البحث: {e}")
        return []

def smart_google_search(book_title: str):
    """
    استراتيجية بحث ذكية متعددة المراحل لزيادة فرصة العثور على رابط مباشر.
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_CX_ID:
        return None, "يرجى إعداد مفاتيح Google Search API و CX ID بشكل صحيح في المتغيرات البيئية."
    
    # قائمة بأسماء نطاقات المكتبات الشائعة للتركيز عليها
    known_library_domains = "site:kutub.info OR site:kutub-pdf.net OR site:pdf-books.org"
    
    # ------------------
    # المرحلة 1: البحث الدقيق في المكتبات الشائعة عن ملف PDF
    # ------------------
    query_stage1 = f"{book_title} filetype:pdf {known_library_domains}"
    logger.info(f"جاري المرحلة 1: {query_stage1}")
    items = _perform_search_stage(query_stage1)

    # ------------------
    # المرحلة 2: البحث الواسع عن ملف PDF (الاستراتيجية السابقة)
    # ------------------
    if not items:
        query_stage2 = f"{book_title} filetype:pdf"
        logger.info(f"جاري المرحلة 2: {query_stage2}")
        items = _perform_search_stage(query_stage2)

    # ------------------
    # المرحلة 3: البحث الشامل عن كلمات مفتاحية (تحميل، رابط، كتاب)
    # ------------------
    if not items:
        query_stage3 = f"{book_title} تحميل رابط كتاب pdf"
        logger.info(f"جاري المرحلة 3: {query_stage3}")
        items = _perform_search_stage(query_stage3)
        
    # ------------------
    # التحقق من الروابط
    # ------------------
    if items:
        # الكلمات المفتاحية التي تدل على رابط تحميل مباشر
        download_keywords = ['.pdf', 'download', 'تحميل', 'file', 'مباشر', 'كتاب']
        
        for item in items:
            link = item.get('link')
            # إذا كان الرابط ينتهي بـ .pdf أو يحتوي على كلمة تحميل
            if link and any(keyword in link.lower() for keyword in download_keywords):
                logger.info(f"تم العثور على رابط محتمل: {link}")
                return link, None
    
    return None, "لم يتم العثور على رابط تحميل مباشر يطابق معايير البحث الذكي."


# دالة الملخص الذكي باستخدام OpenAI
def get_ai_summary(book_title: str) -> str:
    """
    يطلب ملخصًا للكتاب من OpenAI.
    """
    if not OPENAI_API_KEY:
        return "⚠️ لا يمكنني إنشاء ملخص ذكي، مفتاح OpenAI API مفقود."
    
    prompt = f"قم بإنشاء ملخص احترافي ومحفز لكتاب بعنوان '{book_title}' في 100 كلمة، مع ذكر الفكرة الرئيسية والجمهور المستهدف."
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "أنت خبير أدبي ومراجع كتب عربي محترف."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"خطأ في OpenAI API: {e}")
        return "❌ حدث خطأ أثناء محاولة الاتصال بـ OpenAI."

# ----------------------------------------------------------------------
# 3. دوال التعامل مع أوامر تليجرام (بدون تغيير)
# ----------------------------------------------------------------------

# دالة /start
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 أهلاً بك في بوت البحث الذكي عن الكتب!\n"
        "ما عليك سوى إرسال اسم الكتاب الذي تبحث عنه، وسأحاول العثور على رابط مباشر لملف PDF وإرسال ملخص ذكي عنه (إذا توفر)."
    )

# دالة التعامل مع الرسائل النصية
async def handle_message(update: Update, context):
    book_title = update.message.text.strip()
    logger.info(f"تلقيت طلب بحث عن: {book_title}")
    
    await update.message.reply_text(f"🔍 جاري البحث الذكي متعدد المراحل عن الكتاب: {book_title}...")
    
    # 1. البحث عن الكتاب
    pdf_link, error = smart_google_search(book_title)
    
    if pdf_link:
        await update.message.reply_text("✅ تم العثور على الكتاب! جاري إعداد الملخص الذكي...")
        
        # 2. طلب الملخص من الذكاء الاصطناعي
        ai_summary = get_ai_summary(book_title)
        
        final_message = (
            f"📚 **تم العثور على الكتاب:** {book_title}\n\n"
            f"✨ **ملخص وتفاصيل ذكية:**\n{ai_summary}\n\n"
            f"⬇️ **رابط التحميل المباشر:**\n{pdf_link}"
        )
        
        await update.message.reply_markdown(final_message)
        
    else:
        # لم يتم العثور على الكتاب أو حدث خطأ
        await update.message.reply_text(
            f"🚫 عذراً، لم أتمكن من العثور على رابط مباشر لكتاب '{book_title}'.\n"
            f"السبب التقني: {error}"
        )

# ----------------------------------------------------------------------
# 4. الدالة الرئيسية للتشغيل (بدون تغيير)
# ----------------------------------------------------------------------

def main():
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN") 
    
    if not telegram_token:
        logger.error("🚫 فشل البدء: لم يتم العثور على رمز التوكن (TELEGRAM_BOT_TOKEN). تحقق من المتغيرات البيئية.")
        return

    application = ApplicationBuilder().token(telegram_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)) 

    logger.info("✅ البوت يعمل الآن بنظام البحث الذكي الثوري متعدد المراحل...")
    application.run_polling()

if __name__ == '__main__':
    main()
