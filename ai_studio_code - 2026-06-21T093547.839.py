import streamlit as st

# --- الحل السحري لمشكلة لوحة الرسم مع تحديثات Streamlit الجديدة ---
import streamlit.elements.image as st_image
if not hasattr(st_image, 'image_to_url'):
    try:
        from streamlit.elements.lib.image_utils import image_to_url
        st_image.image_to_url = image_to_url
    except ImportError:
        pass
# -------------------------------------------------------------------

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import google.generativeai as genai
import os
import json
import shutil
import re
from streamlit_drawable_canvas import st_canvas

# --- إعدادات الصفحة الأساسية ---
# (أكمل باقي الكود الخاص بك بشكل طبيعي كما هو من هنا فصاعداً...)
import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import google.generativeai as genai
import os
import json
import shutil
import re
from streamlit_drawable_canvas import st_canvas

# --- إعدادات الصفحة الأساسية ---
st.set_page_config(
    page_title="محرر تجوال الرقمي - الإصدار المتقدم",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- إعدادات المجلدات المحلية ---
BOOKS_DIR = "saved_books"
NOTES_FILE = "notes.json"

if not os.path.exists(BOOKS_DIR): os.makedirs(BOOKS_DIR)
if not os.path.exists(NOTES_FILE):
    with open(NOTES_FILE, "w", encoding="utf-8") as f: json.dump({}, f)

def load_notes():
    with open(NOTES_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_notes(notes_dict):
    with open(NOTES_FILE, "w", encoding="utf-8") as f: json.dump(notes_dict, f, ensure_ascii=False, indent=4)

def get_saved_books():
    return [f for f in os.listdir(BOOKS_DIR) if f.endswith(".pdf")]

# --- CSS ---
st.markdown("""
    <style>
        .stApp { direction: rtl; font-family: 'Tajawal', sans-serif; }
        [data-testid="stSidebar"] { right: 0; left: auto; border-left: 1px solid #ddd; border-right: none; }
        .stButton button { width: 100%; border-radius: 5px; }
        .stTextArea textarea { text-align: right; direction: rtl; font-size: 18px; line-height: 1.6; }
        #MainMenu {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- إدارة الحالة (Session State) ---
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
if 'current_page' not in st.session_state: st.session_state.current_page = 0
if 'active_book' not in st.session_state: st.session_state.active_book = None
if 'user_notes' not in st.session_state: st.session_state.user_notes = load_notes()
if 'drawings' not in st.session_state: st.session_state.drawings = {} # لحفظ الرسومات

TESSERACT_EXE_DEFAULT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if not shutil.which("tesseract"): pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE_DEFAULT

# ==========================================
# 1. القائمة الجانبية (الأدوات والتنقل)
# ==========================================
with st.sidebar:
    st.title("📚 مكتبتي المحلية")
    
    # -- إضافة كتاب --
    uploaded_files = st.file_uploader("📥 إضافة كتاب PDF", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            file_path = os.path.join(BOOKS_DIR, file.name)
            if not os.path.exists(file_path):
                with open(file_path, "wb") as f: f.write(file.getbuffer())
                st.session_state.active_book = file.name
                st.session_state.current_page = 0
        st.success("تم الحفظ!")
        st.rerun()

    st.divider()

    saved_books = get_saved_books()
    if saved_books:
        if st.session_state.active_book not in saved_books: st.session_state.active_book = saved_books[0]
        selected_book = st.selectbox("📖 الكتاب النشط:", options=saved_books, index=saved_books.index(st.session_state.active_book))
        if selected_book != st.session_state.active_book:
            st.session_state.active_book = selected_book
            st.session_state.current_page = 0
            st.rerun()

        # -- رفع ملف نصي مصحح --
        uploaded_text = st.file_uploader("📄 إرفاق ملف نصي (TXT) مصحح لعرضه مع الصفحات", type=["txt"])
        if uploaded_text:
            text_content = uploaded_text.read().decode('utf-8')
            # تقسيم الملف بناءً على النمط "--- صفحة X ---"
            pages_data = re.split(r'---\s*صفحة\s*(\d+)\s*---', text_content)
            if st.session_state.active_book not in st.session_state.ocr_cache:
                st.session_state.ocr_cache[st.session_state.active_book] = {}
            
            # قراءة النصوص المعالجة وتوزيعها
            if len(pages_data) > 1:
                for i in range(1, len(pages_data), 2):
                    page_num = int(pages_data[i]) - 1 # تحويل لرقم برمجي يبدأ من 0
                    page_text = pages_data[i+1].strip()
                    st.session_state.ocr_cache[st.session_state.active_book][page_num] = page_text
                st.success("تم استيراد النصوص المصححة وتوزيعها على الصفحات!")
            else:
                st.warning("لم يتم العثور على ترقيم الصفحات في الملف النصي. يجب أن يحتوي على: '--- صفحة 1 ---'")

        st.divider()
        st.markdown("### 🧭 التنقل")
        nav_col1, nav_col2 = st.columns(2)
        with nav_col2:
            if st.button("التالية ▶"): st.session_state.current_page += 1; st.rerun()
        with nav_col1:
            if st.button("◀ السابقة"):
                if st.session_state.current_page > 0: st.session_state.current_page -= 1; st.rerun()

        st.divider()
        # -- تنزيل الملاحظات --
        st.markdown("### 📥 تصدير")
        notes_str = ""
        for b_name, b_notes in st.session_state.user_notes.items():
            notes_str += f"\n{'='*30}\nكتاب: {b_name}\n{'='*30}\n"
            for p_num, p_note in b_notes.items():
                notes_str += f"--- صفحة {int(p_num) + 1} ---\n{p_note}\n\n"
        
        st.download_button("تنزيل الملاحظات (TXT)", data=notes_str.encode('utf-8'), file_name="my_notes.txt", mime="text/plain")

        st.divider()
        zoom_level = st.slider("دقة الصورة", 1.0, 3.0, 1.5, 0.5)
        api_key = st.text_input("🔑 مفتاح Gemini API:", type="password")
    else:
        st.info("لا توجد كتب، ارفع كتاباً للبدء.")

# ==========================================
# 2. منطقة العرض الرئيسية
# ==========================================
st.header(f"📖 {st.session_state.active_book}" if st.session_state.active_book else "محرر تجوال الرقمي")

if st.session_state.active_book and saved_books:
    book_path = os.path.join(BOOKS_DIR, st.session_state.active_book)
    doc = fitz.open(book_path)
    total_pages = doc.page_count
    book_id = st.session_state.active_book

    if st.session_state.current_page >= total_pages: st.session_state.current_page = total_pages - 1
    if st.session_state.current_page < 0: st.session_state.current_page = 0

    page_input = st.number_input(f"الصفحة الحالية (من {total_pages}):", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1)
    if page_input - 1 != st.session_state.current_page:
        st.session_state.current_page = page_input - 1
        st.rerun()

    main_col_pdf, main_col_text = st.columns([1.2, 1])

    # -----------------------------
    # القسم الأيمن: المستند وأدوات الرسم
    # -----------------------------
    with main_col_pdf:
        st.subheader("🖍️ المستند الأصلي (تحديد ورسم)")
        
        # أدوات الرسم والتحديد
        draw_col1, draw_col2, draw_col3 = st.columns([1, 1, 1])
        with draw_col1:
            drawing_mode = st.selectbox("أداة الرسم:", ("freedraw", "line", "rect"), index=0, format_func=lambda x: "قلم حر" if x=="freedraw" else "خط مستقيم" if x=="line" else "مربع تحديد")
        with draw_col2:
            stroke_color = st.color_picker("لون القلم:", "#FFFF00") # أصفر افتراضي للتحديد
        with draw_col3:
            stroke_width = st.slider("سماكة القلم", 1, 25, 10)

        # تحضير صورة الـ PDF
        page = doc.load_page(st.session_state.current_page)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom_level, zoom_level))
        mode = "RGBA" if pix.alpha else "RGB"
        img_display = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

        # استرجاع الرسومات السابقة لهذه الصفحة
        canvas_key = f"canvas_{book_id}_{st.session_state.current_page}"
        if book_id not in st.session_state.drawings: st.session_state.drawings[book_id] = {}
        initial_drawing = st.session_state.drawings[book_id].get(str(st.session_state.current_page), None)

        # لوحة الرسم
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 0, 0.3)",  # لون تعبئة شفاف للمربعات
            stroke_width=stroke_width,
            stroke_color=stroke_color,
            background_image=img_display,
            update_streamlit=True,
            height=img_display.height,
            width=img_display.width,
            drawing_mode=drawing_mode,
            key=canvas_key,
            initial_drawing=initial_drawing
        )

        # حفظ الرسومات في المتغيرات
        if canvas_result.json_data is not None:
            st.session_state.drawings[book_id][str(st.session_state.current_page)] = canvas_result.json_data

    # -----------------------------
    # القسم الأيسر: النص والذكاء الاصطناعي
    # -----------------------------
    with main_col_text:
        st.subheader("📝 النص والذكاء الاصطناعي")
        
        if book_id not in st.session_state.ocr_cache: st.session_state.ocr_cache[book_id] = {}
        
        # استخراج OCR إذا لم يكن النص موجوداً
        if st.session_state.current_page not in st.session_state.ocr_cache[book_id]:
            with st.spinner("جاري قراءة الصفحة..."):
                try:
                    pix_ocr = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    mode_ocr = "RGBA" if pix_ocr.alpha else "RGB"
                    img_ocr = Image.frombytes(mode_ocr, [pix_ocr.width, pix_ocr.height], pix_ocr.samples)
                    extracted_text = pytesseract.image_to_string(img_ocr, lang='ara')
                    st.session_state.ocr_cache[book_id][st.session_state.current_page] = extracted_text
                except Exception as e:
                    st.session_state.ocr_cache[book_id][st.session_state.current_page] = ""
        
        current_text = st.session_state.ocr_cache[book_id][st.session_state.current_page]

        # زر التصحيح الذكي (يطابق 100%)
        if st.button("🤖 تصحيح النص آلياً (مطابقة 100%)", type="primary"):
            if not api_key:
                st.error("أدخل مفتاح API في القائمة الجانبية أولاً.")
            else:
                with st.spinner("الذكاء الاصطناعي يقوم بمطابقة وتصحيح النص، انتظر..."):
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-pro')
                        prompt = f"""
                        أنت مدقق لغوي ونسّاخ محترف. هذا نص تم استخراجه ضوئياً (OCR) من كتاب باللغة العربية.
                        المطلوب:
                        1. تصحيح الأخطاء الإملائية والكلمات المتداخلة الناتجة عن المسح الضوئي.
                        2. استنتاج الكلمات غير الواضحة من السياق.
                        3. ألا تضيف أي تعليقات أو شروحات أو معلومات خارجية من عندك إطلاقاً.
                        4. أعد النص فقط ليكون مطابقاً 100% لصفحة الكتاب الأصلية ومقروءاً بشكل سليم.
                        
                        النص المبدئي:
                        {current_text}
                        """
                        response = model.generate_content(prompt)
                        # تحديث الكاش بالنص المصحح
                        st.session_state.ocr_cache[book_id][st.session_state.current_page] = response.text.strip()
                        st.success("تم التصحيح بنجاح!")
                        st.rerun() # تحديث الصفحة لعرض النص الجديد
                    except Exception as e:
                        st.error(f"حدث خطأ أثناء التصحيح: {e}")

        st.markdown("**النص الحالي (يمكنك نسخه والتعديل عليه):**")
        edited_text = st.text_area("محرر النص:", value=st.session_state.ocr_cache[book_id][st.session_state.current_page], height=400, label_visibility="collapsed")
        
        # حفظ التعديل اليدوي في الذاكرة
        if edited_text != st.session_state.ocr_cache[book_id][st.session_state.current_page]:
            st.session_state.ocr_cache[book_id][st.session_state.current_page] = edited_text

        st.divider()
        
        # قسم الملاحظات
        st.subheader("📌 تعليقاتي وملاحظاتي")
        page_key = str(st.session_state.current_page)
        if book_id not in st.session_state.user_notes: st.session_state.user_notes[book_id] = {}
            
        current_note = st.session_state.user_notes[book_id].get(page_key, "")
        new_note = st.text_area("اكتب أفكارك أو تلخيصك هنا...", value=current_note, height=100)
        
        if st.button("💾 حفظ الملاحظة"):
            st.session_state.user_notes[book_id][page_key] = new_note
            save_notes(st.session_state.user_notes)
            st.success("تم حفظ الملاحظة! (يمكنك تنزيل جميع الملاحظات من القائمة الجانبية)")

    doc.close()
