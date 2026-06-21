import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import google.generativeai as genai
import json
import re
from streamlit_drawable_canvas import st_canvas

# --- إعدادات الصفحة ---
st.set_page_config(page_title="محرر تجوال الرقمي", layout="wide", initial_sidebar_state="expanded")

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

# --- إدارة الذاكرة السحابية (Session State) ---
if 'books_db' not in st.session_state: st.session_state.books_db = {} 
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}

if 'current_page' not in st.session_state or not isinstance(st.session_state.current_page, dict): 
    st.session_state.current_page = {}
    
if 'active_book' not in st.session_state: st.session_state.active_book = None
if 'user_notes' not in st.session_state: st.session_state.user_notes = {}
if 'drawings' not in st.session_state: st.session_state.drawings = {}

# ==========================================
# 1. القائمة الجانبية (الأدوات والتنقل)
# ==========================================
with st.sidebar:
    st.title("📚 مكتبتي السحابية")
    
    # -- رفع الكتب للذاكرة --
    uploaded_files = st.file_uploader("📥 إضافة كتاب PDF", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            st.session_state.books_db[file.name] = file.getvalue()
            if file.name not in st.session_state.current_page:
                st.session_state.current_page[file.name] = 0
            st.session_state.active_book = file.name
        st.success("تم الحفظ في الذاكرة بنجاح!")

    st.divider()

    saved_books = list(st.session_state.books_db.keys())
    if saved_books:
        if st.session_state.active_book not in saved_books: 
            st.session_state.active_book = saved_books[0]
            
        selected_book = st.selectbox("📖 الكتاب النشط:", options=saved_books, index=saved_books.index(st.session_state.active_book))
        if selected_book != st.session_state.active_book:
            st.session_state.active_book = selected_book
            st.rerun()

        # -- رفع ملف نصي مصحح --
        uploaded_text = st.file_uploader("📄 إرفاق ملف نصي (TXT) مصحح", type=["txt"])
        if uploaded_text:
            text_content = uploaded_text.read().decode('utf-8')
            pages_data = re.split(r'---\s*صفحة\s*(\d+)\s*---', text_content)
            if st.session_state.active_book not in st.session_state.ocr_cache:
                st.session_state.ocr_cache[st.session_state.active_book] = {}
            if len(pages_data) > 1:
                for i in range(1, len(pages_data), 2):
                    page_num = int(pages_data[i]) - 1 
                    page_text = pages_data[i+1].strip()
                    st.session_state.ocr_cache[st.session_state.active_book][page_num] = page_text
                st.success("تم توزيع النصوص المصححة!")

        st.divider()
        st.markdown("### 🧭 التنقل")
        nav_col1, nav_col2 = st.columns(2)
        with nav_col2:
            if st.button("التالية ▶"): 
                st.session_state.current_page[st.session_state.active_book] += 1
                st.rerun()
        with nav_col1:
            if st.button("◀ السابقة"):
                if st.session_state.current_page[st.session_state.active_book] > 0: 
                    st.session_state.current_page[st.session_state.active_book] -= 1
                    st.rerun()

        st.divider()
        # -- تنزيل الملاحظات --
        st.markdown("### 📥 تصدير الملاحظات")
        notes_str = ""
        for b_name, b_notes in st.session_state.user_notes.items():
            notes_str += f"\n{'='*30}\nكتاب: {b_name}\n{'='*30}\n"
            for p_num, p_note in b_notes.items():
                notes_str += f"--- صفحة {int(p_num) + 1} ---\n{p_note}\n\n"
        st.download_button("تنزيل الملاحظات (TXT)", data=notes_str.encode('utf-8'), file_name="my_notes.txt", mime="text/plain")

        st.divider()
        zoom_level = st.slider("دقة الصورة", 1.0, 3.0, 1.5, 0.5)
        api_key = st.text_input("🔑 مفتاح Gemini API:", type="password")
        
        if st.button("🧹 مسح الذاكرة بالكامل", type="secondary"):
            st.session_state.clear()
            st.rerun()
    else:
        st.info("لا توجد كتب، ارفع كتاباً للبدء.")

# ==========================================
# 2. منطقة العرض الرئيسية
# ==========================================
st.header(f"📖 {st.session_state.active_book}" if st.session_state.active_book else "محرر تجوال الرقمي")

if st.session_state.active_book and saved_books:
    book_id = st.session_state.active_book
    pdf_bytes = st.session_state.books_db[book_id]
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count

    curr_page = st.session_state.current_page[book_id]
    if curr_page >= total_pages: st.session_state.current_page[book_id] = total_pages - 1
    if curr_page < 0: st.session_state.current_page[book_id] = 0
    curr_page = st.session_state.current_page[book_id]

    page_input = st.number_input(f"الصفحة الحالية (من {total_pages}):", min_value=1, max_value=total_pages, value=curr_page + 1)
    if page_input - 1 != curr_page:
        st.session_state.current_page[book_id] = page_input - 1
        st.rerun()

    main_col_pdf, main_col_text = st.columns([1.2, 1])

    with main_col_pdf:
        st.subheader("🖍️ المستند الأصلي (تحديد ورسم)")
        
        draw_col1, draw_col2, draw_col3 = st.columns([1, 1, 1])
        with draw_col1:
            drawing_mode = st.selectbox("أداة الرسم:", ("freedraw", "line", "rect"), format_func=lambda x: "قلم حر" if x=="freedraw" else "مربع تحديد" if x=="rect" else "خط")
        with draw_col2:
            stroke_color = st.color_picker("لون القلم:", "#FFFF00")
        with draw_col3:
            stroke_width = st.slider("سماكة القلم", 1, 25, 5)

        page = doc.load_page(curr_page)
        
        # --- [ الحل هنا ] إجبار الخلفية على أن تكون بيضاء ومصمتة (alpha=False) ---
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom_level, zoom_level), alpha=False)
        img_display = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        canvas_key = f"canvas_{book_id}_{curr_page}"
        if book_id not in st.session_state.drawings: st.session_state.drawings[book_id] = {}
        initial_drawing = st.session_state.drawings[book_id].get(str(curr_page), None)

        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 0, 0.3)",
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

        if canvas_result.json_data is not None:
            st.session_state.drawings[book_id][str(curr_page)] = canvas_result.json_data

    with main_col_text:
        st.subheader("📝 النص المستخرج")
        
        if book_id not in st.session_state.ocr_cache: st.session_state.ocr_cache[book_id] = {}
        
        if curr_page not in st.session_state.ocr_cache[book_id]:
            with st.spinner("جاري قراءة الصفحة..."):
                try:
                    # نلغي الشفافية أيضاً هنا للـ OCR للضمان
                    pix_ocr = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img_ocr = Image.frombytes("RGB", [pix_ocr.width, pix_ocr.height], pix_ocr.samples)
                    extracted_text = pytesseract.image_to_string(img_ocr, lang='ara')
                    st.session_state.ocr_cache[book_id][curr_page] = extracted_text
                except Exception as e:
                    st.session_state.ocr_cache[book_id][curr_page] = ""
        
        current_text = st.session_state.ocr_cache[book_id][curr_page]

        if st.button("🤖 تصحيح النص آلياً (مطابقة 100%)", type="primary"):
            if not api_key: st.error("أدخل مفتاح API أولاً.")
            else:
                with st.spinner("جاري التصحيح..."):
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(f"قم بتصحيح هذا النص المستخرج ضوئياً ليكون مطابقاً للكتاب الأصلي بدون أي إضافات خارجية:\n{current_text}")
                        st.session_state.ocr_cache[book_id][curr_page] = response.text.strip()
                        st.rerun()
                    except Exception as e:
                        st.error(f"خطأ: {e}")

        edited_text = st.text_area("محرر النص:", value=st.session_state.ocr_cache[book_id][curr_page], height=400, label_visibility="collapsed")
        if edited_text != st.session_state.ocr_cache[book_id][curr_page]:
            st.session_state.ocr_cache[book_id][curr_page] = edited_text

        st.divider()
        st.subheader("📌 تعليقاتي")
        page_key = str(curr_page)
        if book_id not in st.session_state.user_notes: st.session_state.user_notes[book_id] = {}
            
        current_note = st.session_state.user_notes[book_id].get(page_key, "")
        new_note = st.text_area("ملاحظاتي:", value=current_note, height=100)
        if st.button("💾 حفظ الملاحظة"):
            st.session_state.user_notes[book_id][page_key] = new_note
            st.success("تم الحفظ!")

    doc.close()
