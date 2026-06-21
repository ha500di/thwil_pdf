import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import google.generativeai as genai
import json
import re
import os
import io

# --- إعدادات الصفحة ---
st.set_page_config(page_title="محرر تجوال الرقمي", layout="wide", initial_sidebar_state="expanded")

# --- CSS لتحسين الأزرار وإصلاح مشكلة الخط المزعج ---
st.markdown("""
    <style>
        .stApp { direction: rtl; font-family: 'Tajawal', sans-serif; }
        [data-testid="stSidebar"] { border: none !important; box-shadow: -2px 0 5px rgba(0,0,0,0.05); right: 0; left: auto; }
        [data-testid="collapsedControl"] { right: 0; left: auto; }
        .stButton button { width: 100%; border-radius: 8px; font-weight: bold; }
        .stTextArea textarea { text-align: right; direction: rtl; font-size: 18px; line-height: 1.6; }
        #MainMenu {visibility: hidden;}
        .book-frame { border: 3px solid #ccc; border-radius: 10px; padding: 10px; background-color: #f8f9fa; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .side-btn button { height: 100%; min-height: 400px; background-color: transparent; border: 1px dashed #eee; color: #888; }
        .side-btn button:hover { background-color: rgba(0, 120, 255, 0.1); color: #007bff; border: 1px solid #007bff; }
    </style>
""", unsafe_allow_html=True)

# --- إدارة الذاكرة ---
if 'books_db' not in st.session_state: st.session_state.books_db = {} 
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
if 'current_page' not in st.session_state: st.session_state.current_page = {}
if 'active_book' not in st.session_state: st.session_state.active_book = None
if 'user_notes' not in st.session_state: st.session_state.user_notes = {}

# --- دوال الحفظ ---
def save_workspace():
    if 'workspace_dir' in st.session_state and os.path.isdir(st.session_state.workspace_dir):
        data = {
            "ocr_cache": st.session_state.ocr_cache,
            "user_notes": st.session_state.user_notes,
            "current_page": st.session_state.current_page
        }
        try:
            with open(os.path.join(st.session_state.workspace_dir, "tajawal_workspace.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

def load_workspace(path):
    json_path = os.path.join(path, "tajawal_workspace.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                st.session_state.ocr_cache = data.get("ocr_cache", {})
                st.session_state.user_notes = data.get("user_notes", {})
                st.session_state.current_page = data.get("current_page", {})
        except Exception:
            pass
    for file_name in os.listdir(path):
        if file_name.lower().endswith(".pdf"):
            if file_name not in st.session_state.books_db:
                try:
                    with open(os.path.join(path, file_name), "rb") as f:
                        st.session_state.books_db[file_name] = f.read()
                        if file_name not in st.session_state.current_page:
                            st.session_state.current_page[file_name] = 0
                except Exception:
                    pass

# --- التنقل ---
def go_next():
    if st.session_state.active_book in st.session_state.current_page:
        if st.session_state.current_page[st.session_state.active_book] < st.session_state.total_pages - 1:
            st.session_state.current_page[st.session_state.active_book] += 1
            save_workspace()

def go_prev():
    if st.session_state.active_book in st.session_state.current_page:
        if st.session_state.current_page[st.session_state.active_book] > 0:
            st.session_state.current_page[st.session_state.active_book] -= 1
            save_workspace()

def jump_to_page(page_idx):
    st.session_state.current_page[st.session_state.active_book] = page_idx
    save_workspace()

# ==========================================
# 1. القائمة الجانبية
# ==========================================
with st.sidebar:
    st.title("📚 مكتبتي السحابية")
    
    st.markdown("### 📂 مسار الحفظ (للاستخدام المحلي فقط)")
    workspace_input = st.text_input("المسار (مثال: C:/MyBooks):", value=st.session_state.get('workspace_dir', ''))
    
    if st.button("🔄 ربط المجلد"):
        # معالجة المسار لتجنب أخطاء الويندوز (إزالة علامات التنصيص وتعديل الشرطات)
        clean_path = workspace_input.strip().strip('"').strip("'").replace('\\', '/')
        if clean_path and os.path.isdir(clean_path):
            st.session_state.workspace_dir = clean_path
            load_workspace(clean_path)
            st.success("✅ تم ربط المجلد بنجاح!")
            st.rerun()
        else:
            st.warning("⚠️ المسار غير موجود (إذا كنت تستخدم نسخة سحابية Cloud، تجاهل هذا الخيار واستخدم الرفع أدناه).")

    st.divider()
    
    st.markdown("### 📥 رفع كتاب جديد")
    uploaded_files = st.file_uploader("اختر ملف PDF من جهازك", type=["pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        new_books_added = False
        for file in uploaded_files:
            if file.name not in st.session_state.books_db:
                file_bytes = file.getvalue()
                st.session_state.books_db[file.name] = file_bytes
                st.session_state.current_page[file.name] = 0
                st.session_state.active_book = file.name
                new_books_added = True
                
                if 'workspace_dir' in st.session_state and os.path.isdir(st.session_state.workspace_dir):
                    try:
                        with open(os.path.join(st.session_state.workspace_dir, file.name), "wb") as f:
                            f.write(file_bytes)
                    except Exception:
                        pass 
                        
        if new_books_added:
            save_workspace()
            st.success("✅ تم حفظ الكتاب بنجاح وجاهز للقراءة!")
            st.rerun()

    st.divider()

    saved_books = list(st.session_state.books_db.keys())
    if saved_books:
        if st.session_state.active_book not in saved_books: 
            st.session_state.active_book = saved_books[0]
            
        selected_book = st.selectbox("📖 الكتاب النشط:", options=saved_books, index=saved_books.index(st.session_state.active_book))
        if selected_book != st.session_state.active_book:
            st.session_state.active_book = selected_book
            save_workspace()
            st.rerun()

        st.divider()
        st.markdown("### ⚙️ إعدادات العرض")
        frame_size = st.slider("حجم إطار الكتاب (%)", min_value=30, max_value=100, value=70)
        zoom_level = st.slider("دقة الصورة (Zoom)", 1.0, 3.0, 1.5, 0.5)
        
        st.divider()
        api_key = st.text_input("🔑 مفتاح Gemini API:", type="password")
        
        if st.button("🧹 مسح الذاكرة بالكامل", type="secondary"):
            st.session_state.clear()
            st.rerun()

# ==========================================
# 2. منطقة العرض الرئيسية
# ==========================================
if st.session_state.active_book and saved_books:
    st.header(f"📖 {st.session_state.active_book}")
    book_id = st.session_state.active_book
    pdf_bytes = st.session_state.books_db[book_id]
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    st.session_state.total_pages = doc.page_count
    total_pages = doc.page_count

    curr_page = st.session_state.current_page[book_id]
    if curr_page >= total_pages: st.session_state.current_page[book_id] = total_pages - 1
    if curr_page < 0: st.session_state.current_page[book_id] = 0
    curr_page = st.session_state.current_page[book_id]

    page_input = st.number_input(f"الصفحة الحالية (من {total_pages}):", min_value=1, max_value=total_pages, value=curr_page + 1)
    if page_input - 1 != curr_page:
        st.session_state.current_page[book_id] = page_input - 1
        save_workspace()
        st.rerun()

    main_col_pdf, main_col_text = st.columns([1.5, 1])

    # -----------------------------
    # القسم الأيمن: المستند والإطار والتنقل
    # -----------------------------
    with main_col_pdf:
        # **الحل الجديد هنا: تحويل آمن لمختلف صيغ الألوان**
        page = doc.load_page(curr_page)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom_level, zoom_level), alpha=False)
        img_bytes = pix.tobytes("png")  # تحويل آمن إلى صيغة PNG مهما كانت صيغة ألوان الكتاب الأصلية
        img_display = Image.open(io.BytesIO(img_bytes))

        st.markdown('<div class="book-frame">', unsafe_allow_html=True)
        
        spacer_width = (100 - frame_size) / 2
        nav_right, book_col, nav_left = st.columns([max(spacer_width, 10), frame_size, max(spacer_width, 10)])
        
        with nav_right:
            st.markdown('<div class="side-btn">', unsafe_allow_html=True)
            st.button("▶\nلـلـخـلـف", key="side_prev", on_click=go_prev, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with book_col:
            st.image(img_display, use_container_width=True)

        with nav_left:
            st.markdown('<div class="side-btn">', unsafe_allow_html=True)
            st.button("◀\nلـلأـمـام", key="side_next", on_click=go_next, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True) 

        st.write("") 
        bot_prev, bot_center, bot_next = st.columns([1, 2, 1])
        with bot_prev:
            st.button("السابق ▶", key="bot_prev", on_click=go_prev, use_container_width=True)
        with bot_center:
            st.markdown(f"<h5 style='text-align: center; color: #555;'>صفحة {curr_page + 1} من {total_pages}</h5>", unsafe_allow_html=True)
        with bot_next:
            st.button("◀ التالي", key="bot_next", on_click=go_next, use_container_width=True)

    # -----------------------------
    # القسم الأيسر: النص المستخرج والبحث
    # -----------------------------
    with main_col_text:
        st.subheader("📝 النص المستخرج")
        
        curr_page_str = str(curr_page)
        if book_id not in st.session_state.ocr_cache: st.session_state.ocr_cache[book_id] = {}
        
        with st.expander("📥 / 📤 تصدير واستيراد النص (ملف TXT)"):
            full_text = ""
            for p in range(total_pages):
                p_text = st.session_state.ocr_cache.get(book_id, {}).get(str(p), "")
                full_text += f"--- [صفحة {p + 1}] ---\n{p_text}\n\n"
                
            st.download_button(
                label="⬇️ تحميل نصوص الكتاب (.txt)",
                data=full_text,
                file_name=f"{book_id}_Text.txt",
                mime="text/plain",
                use_container_width=True
            )
            
            st.divider()
            
            uploaded_txt = st.file_uploader("📂 رفع ملف نصي (.txt)", type=["txt"])
            if uploaded_txt:
                content = uploaded_txt.getvalue().decode("utf-8")
                pages_text = re.split(r'--- \[صفحة \d+\] ---', content)
                
                if pages_text and pages_text[0].strip() == "":
                    pages_text = pages_text[1:]
                
                if st.button("✅ تأكيد استيراد وتوزيع النص على الصفحات", type="primary", use_container_width=True):
                    for i, text in enumerate(pages_text):
                        if i < total_pages:
                            st.session_state.ocr_cache[book_id][str(i)] = text.strip()
                    save_workspace()
                    st.success("تم توزيع النصوص على صفحات الكتاب بنجاح!")
                    st.rerun()

        with st.expander("🔍 البحث في نصوص الكتاب"):
            search_query = st.text_input("أدخل الكلمة أو العبارة للبحث:")
            if search_query:
                found_pages = []
                for p_idx_str, text in st.session_state.ocr_cache.get(book_id, {}).items():
                    if text and search_query in text:
                        found_pages.append(int(p_idx_str))
                
                found_pages.sort()
                
                if found_pages:
                    st.success(f"✅ تم العثور على '{search_query}' في {len(found_pages)} صفحة/صفحات.")
                    cols = st.columns(min(len(found_pages), 5))
                    for i, p_idx in enumerate(found_pages):
                        col = cols[i % 5]
                        with col:
                            if st.button(f"صفحة {p_idx + 1}", key=f"jump_{p_idx}"):
                                jump_to_page(p_idx)
                                st.rerun()
                else:
                    st.warning("⚠️ لم يتم العثور على الكلمة.")

        if curr_page_str not in st.session_state.ocr_cache[book_id] or st.session_state.ocr_cache[book_id][curr_page_str] == "":
            with st.spinner("جاري قراءة الصفحة..."):
                try:
                    extracted_text = pytesseract.image_to_string(img_display, lang='ara')
                    st.session_state.ocr_cache[book_id][curr_page_str] = extracted_text
                    save_workspace()
                except Exception as e:
                    st.session_state.ocr_cache[book_id][curr_page_str] = ""
        
        current_text = st.session_state.ocr_cache[book_id][curr_page_str]

        if st.button("🤖 تصحيح النص آلياً (مطابقة 100%)", type="primary"):
            if not api_key: st.error("أدخل مفتاح API في القائمة الجانبية أولاً.")
            else:
                with st.spinner("جاري التصحيح..."):
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(f"قم بتصحيح هذا النص المستخرج ضوئياً ليكون مطابقاً للكتاب الأصلي بدون أي إضافات:\n{current_text}")
                        st.session_state.ocr_cache[book_id][curr_page_str] = response.text.strip()
                        save_workspace()
                        st.rerun()
                    except Exception as e:
                        st.error(f"خطأ: {e}")

        edited_text = st.text_area("محرر النص:", value=current_text, height=400, label_visibility="collapsed")
        if edited_text != current_text:
            st.session_state.ocr_cache[book_id][curr_page_str] = edited_text
            save_workspace()

        st.divider()
        st.subheader("📌 تعليقاتي")
        if book_id not in st.session_state.user_notes: st.session_state.user_notes[book_id] = {}
            
        current_note = st.session_state.user_notes[book_id].get(curr_page_str, "")
        new_note = st.text_area("ملاحظاتي للصفحة الحالية:", value=current_note, height=100)
        if st.button("💾 حفظ الملاحظة"):
            st.session_state.user_notes[book_id][curr_page_str] = new_note
            save_workspace()
            st.success("تم حفظ الملاحظة بنجاح!")

    doc.close()
else:
    st.markdown("""
    <div style="text-align: center; padding: 100px 20px;">
        <h1 style="color: #007bff; font-family: 'Tajawal', sans-serif;">📚 مرحباً بك في محرر تجوال الرقمي</h1>
        <p style="font-size: 20px; color: #666; margin-top: 20px;">تطبيقك الذكي لقراءة الكتب، البحث الذكي، وتصحيحها بالذكاء الاصطناعي.</p>
        <div style="background-color: #f1f3f5; padding: 20px; border-radius: 10px; display: inline-block; margin-top: 30px; border: 1px solid #e0e0e0;">
            <p style="font-size: 18px; color: #333; margin: 0;">👉 <b>للبدء:</b> يرجى رفع ملف PDF من القائمة الجانبية على اليمين.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
