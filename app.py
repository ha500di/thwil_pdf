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

# --- CSS لتحسين الأزرار وتصميم الإطار ---
st.markdown("""
    <style>
        .stApp { direction: rtl; font-family: 'Tajawal', sans-serif; }
        [data-testid="stSidebar"] { right: 0; left: auto; border-left: 1px solid #ddd; border-right: none; }
        .stButton button { width: 100%; border-radius: 8px; font-weight: bold; }
        .stTextArea textarea { text-align: right; direction: rtl; font-size: 18px; line-height: 1.6; }
        #MainMenu {visibility: hidden;}
        
        /* تصميم إطار الكتاب */
        .book-frame {
            border: 3px solid #ccc;
            border-radius: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        
        /* إخفاء خلفيات أزرار الأطراف لجعلها كأنها جزء من الشاشة */
        .side-btn button { height: 100%; min-height: 400px; background-color: transparent; border: 1px dashed #eee; color: #888; }
        .side-btn button:hover { background-color: rgba(0, 120, 255, 0.1); color: #007bff; border: 1px solid #007bff; }
    </style>
""", unsafe_allow_html=True)

# --- إدارة الذاكرة السحابية ---
if 'books_db' not in st.session_state: st.session_state.books_db = {} 
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}

if 'current_page' not in st.session_state or not isinstance(st.session_state.current_page, dict): 
    st.session_state.current_page = {}
    
if 'active_book' not in st.session_state: st.session_state.active_book = None
if 'user_notes' not in st.session_state: st.session_state.user_notes = {}
if 'drawings' not in st.session_state: st.session_state.drawings = {}

# --- دوال التنقل ---
def go_next():
    if st.session_state.current_page[st.session_state.active_book] < st.session_state.total_pages - 1:
        st.session_state.current_page[st.session_state.active_book] += 1

def go_prev():
    if st.session_state.current_page[st.session_state.active_book] > 0:
        st.session_state.current_page[st.session_state.active_book] -= 1

# ==========================================
# 1. القائمة الجانبية
# ==========================================
with st.sidebar:
    st.title("📚 مكتبتي السحابية")
    
    uploaded_files = st.file_uploader("📥 إضافة كتاب PDF", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            st.session_state.books_db[file.name] = file.getvalue()
            if file.name not in st.session_state.current_page:
                st.session_state.current_page[file.name] = 0
            st.session_state.active_book = file.name
        st.success("تم الحفظ في الذاكرة بنجاح!")
        st.rerun()

    st.divider()

    saved_books = list(st.session_state.books_db.keys())
    if saved_books:
        if st.session_state.active_book not in saved_books: 
            st.session_state.active_book = saved_books[0]
            
        selected_book = st.selectbox("📖 الكتاب النشط:", options=saved_books, index=saved_books.index(st.session_state.active_book))
        if selected_book != st.session_state.active_book:
            st.session_state.active_book = selected_book
            st.rerun()

        st.divider()
        st.markdown("### ⚙️ إعدادات العرض")
        # أداة التحكم بحجم الكتاب بنسبة مئوية
        frame_size = st.slider("حجم إطار الكتاب (%)", min_value=30, max_value=100, value=70, help="يصغر أو يكبر مساحة عرض الكتاب")
        zoom_level = st.slider("دقة الصورة (Zoom)", 1.0, 3.0, 1.5, 0.5)
        api_key = st.text_input("🔑 مفتاح Gemini API:", type="password")
        
        if st.button("🧹 مسح الذاكرة", type="secondary"):
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
    st.session_state.total_pages = doc.page_count
    total_pages = doc.page_count

    curr_page = st.session_state.current_page[book_id]
    if curr_page >= total_pages: st.session_state.current_page[book_id] = total_pages - 1
    if curr_page < 0: st.session_state.current_page[book_id] = 0
    curr_page = st.session_state.current_page[book_id]

    main_col_pdf, main_col_text = st.columns([1.5, 1])

    # -----------------------------
    # القسم الأيمن: المستند والإطار والتنقل
    # -----------------------------
    with main_col_pdf:
        # خيار العرض (لضمان سرعة التصفح)
        view_mode = st.radio("اختر وضع العرض:", ["📖 قراءة وتقليب سريع", "🖍️ تحديد ورسم"], horizontal=True, label_visibility="collapsed")
        
        # --- استخراج وتجهيز الصورة بخلفية بيضاء مضمونة ---
        page = doc.load_page(curr_page)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom_level, zoom_level), alpha=True)
        img_transparent = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
        
        # إنشاء خلفية بيضاء صلبة ودمجها لحل مشكلة الشاشة السوداء نهائياً
        img_display = Image.new("RGB", img_transparent.size, (255, 255, 255))
        img_display.paste(img_transparent, mask=img_transparent.split()[3])

        st.markdown('<div class="book-frame">', unsafe_allow_html=True)
        
        # --- تصميم أطراف التقليب وحجم الإطار ---
        # نقوم بتقسيم المساحة بناءً على نسبة الحجم (frame_size) التي اختارها المستخدم
        spacer_width = (100 - frame_size) / 2
        
        # ترتيب الأعمدة: يمين (زر السابق)، وسط (الكتاب)، يسار (زر التالي)
        nav_right, book_col, nav_left = st.columns([max(spacer_width, 10), frame_size, max(spacer_width, 10)])
        
        with nav_right:
            st.markdown('<div class="side-btn">', unsafe_allow_html=True)
            st.button("▶\nلـلـخـلـف", key="side_prev", on_click=go_prev, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with book_col:
            if view_mode == "📖 قراءة وتقليب سريع":
                # العرض السريع والممتاز (يتأقلم مع حجم الإطار)
                st.image(img_display, use_container_width=True)
            else:
                # وضع الرسم
                draw_col1, draw_col2 = st.columns([2, 1])
                with draw_col1: drawing_mode = st.selectbox("الأداة:", ("freedraw", "rect"), format_func=lambda x: "قلم حر" if x=="freedraw" else "مربع تحديد")
                with draw_col2: stroke_color = st.color_picker("اللون:", "#FFFF00")
                
                canvas_key = f"canvas_{book_id}_{curr_page}"
                initial_drawing = st.session_state.drawings.get(book_id, {}).get(str(curr_page), None)

                canvas_result = st_canvas(
                    fill_color="rgba(255, 255, 0, 0.3)",
                    stroke_width=3, stroke_color=stroke_color,
                    background_image=img_display, update_streamlit=True,
                    height=img_display.height, width=img_display.width,
                    drawing_mode=drawing_mode, key=canvas_key,
                    initial_drawing=initial_drawing
                )
                if canvas_result.json_data is not None:
                    if book_id not in st.session_state.drawings: st.session_state.drawings[book_id] = {}
                    st.session_state.drawings[book_id][str(curr_page)] = canvas_result.json_data

        with nav_left:
            st.markdown('<div class="side-btn">', unsafe_allow_html=True)
            st.button("◀\nلـلأـمـام", key="side_next", on_click=go_next, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True) # إغلاق إطار الكتاب

        # --- أزرار التنقل السفلية في الزوايا ---
        st.write("") # مسافة
        bot_prev, bot_center, bot_next = st.columns([1, 2, 1])
        with bot_prev:
            st.button("السابق ▶", key="bot_prev", on_click=go_prev, use_container_width=True)
        with bot_center:
            st.markdown(f"<h5 style='text-align: center; color: #555;'>صفحة {curr_page + 1} من {total_pages}</h5>", unsafe_allow_html=True)
        with bot_next:
            st.button("◀ التالي", key="bot_next", on_click=go_next, use_container_width=True)


    # -----------------------------
    # القسم الأيسر: النص المستخرج
    # -----------------------------
    with main_col_text:
        st.subheader("📝 النص المستخرج")
        
        if book_id not in st.session_state.ocr_cache: st.session_state.ocr_cache[book_id] = {}
        
        if curr_page not in st.session_state.ocr_cache[book_id]:
            with st.spinner("جاري قراءة الصفحة..."):
                try:
                    # نستخدم النسخة ذات الخلفية البيضاء لضمان قراءة OCR ممتازة
                    extracted_text = pytesseract.image_to_string(img_display, lang='ara')
                    st.session_state.ocr_cache[book_id][curr_page] = extracted_text
                except Exception as e:
                    st.session_state.ocr_cache[book_id][curr_page] = ""
        
        current_text = st.session_state.ocr_cache[book_id][curr_page]

        if st.button("🤖 تصحيح النص آلياً (مطابقة 100%)", type="primary"):
            if not api_key: st.error("أدخل مفتاح API في القائمة الجانبية أولاً.")
            else:
                with st.spinner("جاري التصحيح..."):
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(f"قم بتصحيح هذا النص المستخرج ضوئياً ليكون مطابقاً للكتاب الأصلي بدون أي إضافات:\n{current_text}")
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
