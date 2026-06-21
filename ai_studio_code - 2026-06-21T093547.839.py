import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import google.generativeai as genai
import os
import json
import shutil

# --- إعدادات الصفحة الأساسية ---
st.set_page_config(
    page_title="محرر تجوال الرقمي",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- إعدادات المجلدات المحلية لحفظ الكتب والملاحظات ---
BOOKS_DIR = "saved_books"
NOTES_FILE = "notes.json"

if not os.path.exists(BOOKS_DIR):
    os.makedirs(BOOKS_DIR)

if not os.path.exists(NOTES_FILE):
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# دالة لتحميل الملاحظات
def load_notes():
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# دالة لحفظ الملاحظات
def save_notes(notes_dict):
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes_dict, f, ensure_ascii=False, indent=4)

# الحصول على قائمة الكتب المحفوظة
def get_saved_books():
    return [f for f in os.listdir(BOOKS_DIR) if f.endswith(".pdf")]

# --- حقن CSS مخصص لتحسين الواجهة وتغيير الاتجاه لليمين (RTL) ---
st.markdown("""
    <style>
        /* جعل الاتجاه من اليمين لليسار */
        .stApp { direction: rtl; font-family: 'Tajawal', sans-serif; }
        /* نقل القائمة الجانبية لليمين */
        [data-testid="stSidebar"] { right: 0; left: auto; border-left: 1px solid #ddd; border-right: none; }
        /* تحسين مظهر أزرار القائمة */
        .stButton button { width: 100%; border-radius: 5px; }
        /* تحسين شكل صناديق النصوص */
        .stTextArea textarea { text-align: right; direction: rtl; font-size: 18px; line-height: 1.6; }
        .stTextInput input { text-align: right; direction: rtl; }
        /* إخفاء القائمة العلوية الافتراضية الخاصة بـ Streamlit */
        #MainMenu {visibility: hidden;}
    </style>
    
    <!-- سكريبت للتنقل بزر المسافة (Spacebar) - يعمل في بعض المتصفحات -->
    <script>
        document.addEventListener('keydown', function(e) {
            if (e.code === 'Space' && e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'INPUT') {
                e.preventDefault();
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: 'next_page'}, '*');
            }
        });
    </script>
""", unsafe_allow_html=True)

# --- إدارة الحالة (Session State) ---
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
if 'current_page' not in st.session_state: st.session_state.current_page = 0
if 'active_book' not in st.session_state: st.session_state.active_book = None
if 'user_notes' not in st.session_state: st.session_state.user_notes = load_notes()

# --- إعداد مسار Tesseract ---
TESSERACT_EXE_DEFAULT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if shutil.which("tesseract"): pass
else: pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE_DEFAULT

# ==========================================
# 1. القائمة الجانبية (الأدوات والتنقل والكتب)
# ==========================================
with st.sidebar:
    st.title("📚 مكتبتي المحلية")
    
    # 1. رفع الكتب وحفظها
    uploaded_files = st.file_uploader("📥 أضف كتاباً جديداً للمكتبة (يُحفظ على جهازك)", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            file_path = os.path.join(BOOKS_DIR, file.name)
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
        st.success("تم الحفظ بنجاح! يتم الآن تحديث المكتبة...")
        st.rerun()

    st.divider()

    # 2. إدارة الكتب الموجودة
    saved_books = get_saved_books()
    if not saved_books:
        st.info("لا توجد كتب محفوظة. قم برفع كتاب للبدء.")
        st.session_state.active_book = None
    else:
        selected_book = st.selectbox("📖 اختر الكتاب للقراءة:", options=saved_books, 
                                     index=saved_books.index(st.session_state.active_book) if st.session_state.active_book in saved_books else 0)
        
        if selected_book != st.session_state.active_book:
            st.session_state.active_book = selected_book
            st.session_state.current_page = 0
            st.rerun()

        # زر حذف الكتاب
        if st.button("🗑️ حذف الكتاب المختار", type="secondary"):
            os.remove(os.path.join(BOOKS_DIR, selected_book))
            st.rerun()

        st.divider()
        
        # 3. أزرار التنقل السريع في القائمة الجانبية
        st.markdown("### 🧭 التنقل")
        nav_col1, nav_col2 = st.columns(2)
        with nav_col2:
            if st.button("التالية ▶"):
                st.session_state.current_page += 1
                st.rerun()
        with nav_col1:
            if st.button("◀ السابقة"):
                if st.session_state.current_page > 0:
                    st.session_state.current_page -= 1
                    st.rerun()

        # 4. إعدادات العرض
        st.markdown("### ⚙️ إعدادات العرض")
        zoom_level = st.slider("دقة الصورة (Zoom)", 1.0, 4.0, 2.0, 0.5, help="يزيد من وضوح الصورة عند التكبير")
        
        st.divider()
        api_key = st.text_input("🔑 مفتاح Gemini API (للتلخيص):", type="password")

# ==========================================
# 2. منطقة العرض الرئيسية
# ==========================================
# شريط العنوان وزر الشرح
col_title, col_help = st.columns([4, 1])
with col_title:
    st.header(f"📖 {st.session_state.active_book}" if st.session_state.active_book else "مرحباً بك في محرر تجوال")
with col_help:
    with st.expander("ℹ️ عن البرنامج"):
        st.write("""
        **طريقة العمل:**
        1. ارفع كتاباً من القائمة الجانبية (سيُحفظ في جهازك ولن يرفع للإنترنت).
        2. استخدم أزرار التنقل للانتقال بين الصفحات.
        3. سيقوم البرنامج بقراءة النص تلقائياً من الصورة باستخدام OCR.
        4. يمكنك كتابة تعليقاتك الخاصة تحت النص المستخرج وستبقى محفوظة.
        5. لنسخ النص، استخدم أيقونة النسخ الصغيرة أعلى مربع النص.
        """)

if st.session_state.active_book and saved_books:
    book_path = os.path.join(BOOKS_DIR, st.session_state.active_book)
    doc = fitz.open(book_path)
    total_pages = doc.page_count
    book_id = st.session_state.active_book

    # تصحيح رقم الصفحة إذا تجاوز الحدود
    if st.session_state.current_page >= total_pages: st.session_state.current_page = total_pages - 1
    if st.session_state.current_page < 0: st.session_state.current_page = 0

    # التنقل وإدخال رقم الصفحة يدوياً من الشاشة الرئيسية
    st.write(f"**الصفحة {st.session_state.current_page + 1} من {total_pages}**")
    page_input = st.number_input("اذهب إلى صفحة:", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1, label_visibility="collapsed")
    if page_input - 1 != st.session_state.current_page:
        st.session_state.current_page = page_input - 1
        st.rerun()

    # إنشاء تخطيط متجاوب (على الجوال ستكون عمودية، على الكمبيوتر أفقية)
    main_col_pdf, main_col_text = st.columns([1.2, 1])

    # -----------------------------
    # القسم الأيمن: عرض مستند الـ PDF
    # -----------------------------
    with main_col_pdf:
        st.subheader("📄 عرض المستند الأصلي")
        page = doc.load_page(st.session_state.current_page)
        # استخدام مستوى الدقة المختار
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom_level, zoom_level))
        img_display = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # use_container_width=True يضمن احتواء الصورة داخل الإطار بشكل مثالي (Fit to frame)
        st.image(img_display, use_container_width=True)

    # -----------------------------
    # القسم الأيسر: النص المستخرج والملاحظات
    # -----------------------------
    with main_col_text:
        st.subheader("📝 النص المستخرج")
        
        # استخراج النص
        if book_id not in st.session_state.ocr_cache: st.session_state.ocr_cache[book_id] = {}
        
        if st.session_state.current_page not in st.session_state.ocr_cache[book_id]:
            with st.spinner("جاري استخراج النص (OCR)..."):
                pix_ocr = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_ocr = Image.frombytes("RGB", [pix_ocr.width, pix_ocr.height], pix_ocr.samples)
                extracted_text = pytesseract.image_to_string(img_ocr, lang='ara')
                st.session_state.ocr_cache[book_id][st.session_state.current_page] = extracted_text
        else:
            extracted_text = st.session_state.ocr_cache[book_id][st.session_state.current_page]

        # 1. عرض النص مع إمكانية النسخ (يظهر مربع داخله زر نسخ في الأعلى)
        st.markdown("**انسخ النص من المربع أدناه:**")
        st.code(extracted_text, language="text")
        
        # 2. مربع قابل للتعديل
        edited_text = st.text_area("أو قم بتعديل النص المستخرج هنا:", value=extracted_text, height=300)
        st.session_state.ocr_cache[book_id][st.session_state.current_page] = edited_text

        # 3. نظام التعليقات والملاحظات (يُحفظ محلياً)
        st.divider()
        st.subheader("📌 ملاحظاتي على هذه الصفحة")
        
        # جلب الملاحظة السابقة إن وجدت
        page_key = str(st.session_state.current_page)
        if book_id not in st.session_state.user_notes:
            st.session_state.user_notes[book_id] = {}
            
        current_note = st.session_state.user_notes[book_id].get(page_key, "")
        
        new_note = st.text_area("اكتب أفكارك أو تلخيصك هنا...", value=current_note, height=150)
        if st.button("💾 حفظ الملاحظة"):
            st.session_state.user_notes[book_id][page_key] = new_note
            save_notes(st.session_state.user_notes)
            st.success("تم حفظ الملاحظة!")

        # 4. التلخيص بالذكاء الاصطناعي
        if st.button("✨ لخص هذه الصفحة (يحتاج API)"):
            if not api_key:
                st.error("أدخل مفتاح الـ API في القائمة الجانبية أولاً.")
            else:
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-pro')
                    response = model.generate_content(f"لخص النص التالي بلغة واضحة:\n\n{edited_text}")
                    st.info(response.text)
                except Exception as e:
                    st.error(f"خطأ: {str(e)}")
    
    doc.close()
else:
    st.info("الرجاء رفع كتاب من القائمة لاختياره والبدء بالقراءة.")