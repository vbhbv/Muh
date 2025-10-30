import os
import logging
import requests
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from openai import OpenAI

# ----------------------------------------------------------------------
# 1. إعدادات المتغيرات والمفاتيح (يتم قراءتها من Railway)
# ----------------------------------------------------------------------

# يتم قراءة المفاتيح من متغيرات البيئة (Railway)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_CX_ID = os.environ.get("GOOGLE_SEARCH_CX_ID") # تم تعديل الاسم ليتطابق مع Railway

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

# دالة البحث الذكي عن رابط التحميل باستخدام Google Search API
def smart_google_search(book_title: str):
    """
    يبحث عن ملف PDF لكتاب معين باستخدام Google Custom Search API.
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_CX_ID:
        # رسالة الخطأ توضح المشكلة بوضوح إذا لم يتم العثور على المفاتيح
        return None, "يرجى إعداد مفاتيح Google Search API و CX ID بشكل صحيح في المتغيرات البيئية."
    
    # تحسين استعلام البحث للتركيز على ملفات PDF
    query = f"{book_title} filetype:pdf"
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': GOOGLE_SEARCH_API_KEY,
        'cx': GOOGLE_SEARCH_CX_ID,
        'q': query,
        'num': 5  # طلب 5 نتائج لزيادة فرصة العثور على رابط مباشر
    }
    
    try:
        logger.info(f"جاري البحث عن: {query}")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status() # إثارة خطأ لردود HTTP سيئة (4xx أو 5xx)
        data = response.json()
        
        if 'items' in data:
            for item in data['items']:
                link = item.get('link')
                # التحقق من أن الرابط ينتهي بـ .pdf للتأكد من أنه رابط مباشر للملف
                if link and link.lower().endswith('.pdf'):
                    return link, None
            
            # إذا لم يتم العثور على رابط مباشر لملف PDF
            return None, "تم العثور على نتائج بحث، لكن لم يتم العثور على رابط مباشر لملف PDF."
        
        return None, "لم يتم العثور على نتائج بحث ذات صلة."
    
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في طلب Google Search API: {e}")
        return None, f"فشل الاتصال بخدمة Google Search API: {e}"
    except Exception as e:
        logger.error(f"خطأ غير متوقع أثناء البحث: {e}")
        return None, f"خطأ تقني غير متوقع: {e}"


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
# 3. دوال التعامل مع أوامر تليجرام
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
    
    await update.message.reply_text(f"🔍 جاري البحث الذكي عن الكتاب: {book_title}...")
    
    # 1. البحث عن الكتاب
    pdf_link, error = smart_google_search(book_title)
    
    if pdf_link:
        # تم العثور على الكتاب، الآن اطلب الملخص
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
# 4. الدالة الرئيسية للتشغيل
# ----------------------------------------------------------------------

def main():
    # 🚨 التصحيح النهائي لضمان قراءة التوكن قبل البدء
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN") 
    
    if not telegram_token:
        # رسالة خطأ واضحة في سجلات Railway
        logger.error("🚫 فشل البدء: لم يتم العثور على رمز التوكن (TELEGRAM_BOT_TOKEN). تحقق من المتغيرات البيئية.")
        return

    # بناء التطبيق
    application = ApplicationBuilder().token(telegram_token).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)) 

    logger.info("✅ البوت يعمل الآن بنظام البحث الذكي الثوري...")
    # بدء تشغيل البوت (Polling)
    application.run_polling()

if __name__ == '__main__':
    main()
