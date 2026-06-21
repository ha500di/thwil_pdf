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

# --- حقن CSS مخصص لتحسين الواجهة ---
st.markdown("""
    <style>
        .stApp { direction: rtl; font-family: 'Tajawal', sans-serif; }
        [data-testid="stSidebar"] { right: 0; left: auto; border-left: 1px solid #ddd; border-right: none; }
        .stButton button { width: 100%; border-radius: 5px; }
        .stTextArea textarea { text-align: right; direction: rtl; font-size: 18px; line-height: 1.6; }
        .stTextInput input { text-align: right; direction: rtl; }
        #MainMenu {visibility: hidden;}
    </style>
    
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
    uploaded_files = st.file_uploader("📥 أضف كتاباً جديداً للمكتبة", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        new_file_added = False
        for file in uploaded_files:
            file_path = os.path.join(BOOKS_DIR, file.name)
            # إصلاح مشكلة الـ Loop: التأكد من أن الملف غير موجود مسبقاً قبل الحفظ
            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(file.getbuffer())
                new_file_added = True
                st.session_state.active_book = file.name # تعيين الكتاب المرفوع ككتاب نشط
                st.session_state.current_page = 0
        
        if new_file_added:
            st.success("تم الحفظ بنجاح! يتم الآن عرض الكتاب...")
            st.rerun()

    st.divider()

    # 2. إدارة الكتب الموجودة
    saved_books = get_saved_books()
    if not saved_books:
        st.info("لا توجد كتب محفوظة. قم برفع كتاب للبدء.")
        st.session_state.active_book = None
    else:
        # التأكد من أن الكتاب النشط موجود في القائمة، وإلا نختار الأول
        if st.session_state.active_book not in saved_books:
            st.session_state.active_book = saved_books[0]

        selected_book = st.selectbox("📖 اختر الكتاب للقراءة:", options=saved_books, 
                                     index=saved_books.index(st.session_state.active_book))
        
        if selected_book != st.session_state.active_book:
            st.session_state.active_book = selected_book
            st.session_state.current_page = 0
            st.rerun()

        # زر حذف الكتاب
        if st.button("🗑️ حذف الكتاب المختار", type="secondary"):
            os.remove(os.path.join(BOOKS_DIR, selected_book))
            st.session_state.active_book = None
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
        zoom_level = st.slider("دقة الصورة (Zoom)", 1.0, 4.0, 2.0, 0.5)
        
        st.divider()
        api_key = st.text_input("🔑 مفتاح Gemini API:", type="password")

# ==========================================
# 2. منطقة العرض الرئيسية
# ==========================================
col_title, col_help = st.columns([4, 1])
with col_title:
    st.header(f"📖 {st.session_state.active_book}" if st.session_state.active_book else "مرحباً بك في محرر تجوال")
with col_help:
    with st.expander("ℹ️ عن البرنامج"):
        st.write("""
        **طريقة العمل:**
        1. ارفع كتاباً، وسيحفظ تلقائياً ولن تحتاج لرفعه مجدداً.
        2. استخدم أزرار التنقل.
        3. يمكنك تعديل ونسخ النص المستخرج.
        """)

if st.session_state.active_book and saved_books:
    book_path = os.path.join(BOOKS_DIR, st.session_state.active_book)
    
    try:
        doc = fitz.open(book_path)
        total_pages = doc.page_count
        book_id = st.session_state.active_book

        # تصحيح رقم الصفحة
        if st.session_state.current_page >= total_pages: st.session_state.current_page = total_pages - 1
        if st.session_state.current_page < 0: st.session_state.current_page = 0

        # شريط الانتقال
        st.write(f"**الصفحة {st.session_state.current_page + 1} من {total_pages}**")
        page_input = st.number_input("اذهب إلى صفحة:", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1, label_visibility="collapsed")
        if page_input - 1 != st.session_state.current_page:
            st.session_state.current_page = page_input - 1
            st.rerun()

        main_col_pdf, main_col_text = st.columns([1.2, 1])

        # -----------------------------
        # القسم الأيمن: عرض المستند
        # -----------------------------
        with main_col_pdf:
            st.subheader("📄 المستند الأصلي")
            page = doc.load_page(st.session_state.current_page)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom_level, zoom_level))
            
            # إصلاح مشكلة شفافية الصور في بعض ملفات الـ PDF
            mode = "RGBA" if pix.alpha else "RGB"
            img_display = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            
            st.image(img_display, use_container_width=True)

        # -----------------------------
        # القسم الأيسر: النص المستخرج
        # -----------------------------
        with main_col_text:
            st.subheader("📝 النص المستخرج")
            
            if book_id not in st.session_state.ocr_cache: st.session_state.ocr_cache[book_id] = {}
            
            if st.session_state.current_page not in st.session_state.ocr_cache[book_id]:
                with st.spinner("جاري استخراج النص..."):
                    try:
                        pix_ocr = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        mode_ocr = "RGBA" if pix_ocr.alpha else "RGB"
                        img_ocr = Image.frombytes(mode_ocr, [pix_ocr.width, pix_ocr.height], pix_ocr.samples)
                        extracted_text = pytesseract.image_to_string(img_ocr, lang='ara')
                        st.session_state.ocr_cache[book_id][st.session_state.current_page] = extracted_text
                    except Exception as e:
                        extracted_text = f"حدث خطأ أثناء استخراج النص: {e}"
                        st.session_state.ocr_cache[book_id][st.session_state.current_page] = extracted_text
            else:
                extracted_text = st.session_state.ocr_cache[book_id][st.session_state.current_page]

            st.markdown("**انسخ النص بالضغط على الأيقونة في زاوية المربع:**")
            st.code(extracted_text, language="text")
            
            edited_text = st.text_area("أو قم بتعديل النص المستخرج هنا:", value=extracted_text, height=300)
            st.session_state.ocr_cache[book_id][st.session_state.current_page] = edited_text

            # الملاحظات
            st.divider()
            st.subheader("📌 ملاحظاتي على هذه الصفحة")
            page_key = str(st.session_state.current_page)
            if book_id not in st.session_state.user_notes:
                st.session_state.user_notes[book_id] = {}
                
            current_note = st.session_state.user_notes[book_id].get(page_key, "")
            new_note = st.text_area("اكتب أفكارك هنا...", value=current_note, height=150)
            
            if st.button("💾 حفظ الملاحظة"):
                st.session_state.user_notes[book_id][page_key] = new_note
                save_notes(st.session_state.user_notes)
                st.success("تم الحفظ!")

            # التلخيص
            if st.button("✨ تلخيص (يتطلب API)"):
                if not api_key:
                    st.error("أدخل مفتاح הـ API أولاً.")
                else:
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(f"لخص النص التالي بلغة واضحة:\n\n{edited_text}")
                        st.info(response.text)
                    except Exception as e:
                        st.error(f"خطأ: {str(e)}")
        
        doc.close()
    except Exception as e:
        st.error(f"حدث خطأ أثناء قراءة ملف الـ PDF: {e}")
