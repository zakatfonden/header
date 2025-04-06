# app.py

import streamlit as st
import backend # Import the backend functions
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="مُنشئ عناوين الأسئلة والأجوبة", # Q&A Headline Generator
    page_icon="✨"
)

# --- App Interface ---
st.title("✨ مُنشئ عناوين الأسئلة والأجوبة التلقائي ✨")
st.markdown("""
قم بتحميل ملف Word (.docx) يحتوي على أسئلة وأجوبة باللغة العربية.
أدخل مفتاح Google AI API الخاص بك أدناه، ثم قم بتحميل الملف واضغط على زر المعالجة.
سيقوم التطبيق تلقائيًا بإنشاء عنوان لكل زوج من الأسئلة والأجوبة وإدراجه في المستند.

**تنسيق الملف المتوقع:**
* يجب أن يبدأ كل سؤال بـ `س:` أو `Q:` (مع مسافة اختيارية ونقطتين).
* يجب أن تبدأ كل إجابة بـ `ج:` أو `A:` (مع مسافة اختيارية ونقطتين).
* سيتم التعامل مع الفقرات التي تلي السؤال أو الإجابة (قبل علامة السؤال/الإجابة التالية) كجزء منها.
""")

# --- API Key Input ---
api_key = st.text_input(
    "🔑 أدخل مفتاح Google AI API الخاص بك هنا:",
    type="password",
    help="احصل على مفتاحك من Google AI Studio. لن يتم تخزين مفتاحك."
)

# Initialize session state for download
if 'processed_file' not in st.session_state:
    st.session_state.processed_file = None
if 'original_filename' not in st.session_state:
    st.session_state.original_filename = None

# --- File Upload ---
# Enable uploader only if API key is entered
file_uploader_disabled = not bool(api_key)
uploaded_file = st.file_uploader(
    "اختر ملف Word (.docx)",
    type=["docx"],
    disabled=file_uploader_disabled
)

if not api_key:
    st.warning("يرجى إدخال مفتاح Google AI API للمتابعة.")

# --- Processing Logic ---
if uploaded_file is not None and api_key:
    st.success(f"تم تحميل الملف: {uploaded_file.name}")
    st.session_state.original_filename = uploaded_file.name # Store filename

    if st.button("🚀 معالجة الملف وإنشاء العناوين"):
        st.session_state.processed_file = None # Reset download state
        error_occured = False
        qna_pairs_with_headlines = []

        # Configure Gemini with the provided key *before* processing
        api_key_configured = backend.configure_gemini(api_key)

        if not api_key_configured:
            st.error("فشل في تكوين Gemini API باستخدام المفتاح المقدم. يرجى التحقق من المفتاح والمحاولة مرة أخرى.")
            st.stop() # Stop execution if API key is invalid

        with st.spinner("جاري تحليل المستند واستدعاء الذكاء الاصطناعي... قد يستغرق هذا بعض الوقت."):
            # 1. Parse the document
            try:
                # Pass the uploaded file object directly
                qna_pairs, original_paragraphs = backend.parse_qna_pairs(uploaded_file)
                if not qna_pairs:
                    st.warning("لم يتم العثور على أزواج أسئلة وأجوبة بالتنسيق المتوقع (س:/ج: أو Q:/A:). يرجى التحقق من الملف.")
                    error_occured = True
                else:
                    st.info(f"تم العثور على {len(qna_pairs)} زوج من الأسئلة والأجوبة.")

            except Exception as e:
                st.error(f"حدث خطأ أثناء تحليل ملف Word: {e}")
                # Reset file uploader state to allow re-uploading after error maybe?
                # uploaded_file = None # This might cause issues with Streamlit's flow
                error_occured = True


            # 2. Generate headlines if parsing succeeded
            if not error_occured:
                progress_bar = st.progress(0)
                headlines_generated = 0
                total_pairs = len(qna_pairs) # Store total number before filtering

                for i, pair in enumerate(qna_pairs):
                    try:
                        headline = backend.generate_headline(pair['question'], pair['answer'])
                        if headline and not headline.startswith("خطأ"): # Check for success
                            pair['headline'] = headline
                            qna_pairs_with_headlines.append(pair) # Only add pairs with successful headlines
                            headlines_generated += 1
                        else:
                            st.warning(f"تعذر إنشاء عنوان للسؤال الذي يبدأ بـ: '{pair['question'][:50]}...' (السبب المحتمل: {headline or 'فشل API'})")
                    except Exception as e:
                        st.error(f"حدث خطأ أثناء إنشاء عنوان للسؤال: '{pair['question'][:50]}...' الخطأ: {e}")

                    # Update progress based on total pairs initially found
                    progress_bar.progress((i + 1) / total_pairs if total_pairs > 0 else 0)

                progress_bar.empty() # Remove progress bar after loop

                if headlines_generated == 0 and total_pairs > 0:
                    st.error("لم يتم إنشاء أي عناوين بنجاح. قد تكون هناك مشكلة في الاتصال بواجهة برمجة التطبيقات Gemini أو تنسيق الملف.")
                    error_occured = True # Mark error if no headlines generated
                elif headlines_generated < total_pairs:
                    st.warning(f"تم إنشاء {headlines_generated} عنوان بنجاح من أصل {total_pairs} زوج تم العثور عليه.")
                elif total_pairs == 0:
                    pass # Already handled by the parsing warning
                else:
                    st.success(f"تم إنشاء {headlines_generated} عنوان بنجاح!")


            # 3. Create the modified document only if headlines were generated successfully
            if not error_occured and qna_pairs_with_headlines:
                 try:
                     modified_doc = backend.create_modified_document(original_paragraphs, qna_pairs_with_headlines)
                     st.session_state.processed_file = backend.save_doc_to_bytes(modified_doc)
                     st.balloons() # Fun success indicator
                 except Exception as e:
                     st.error(f"حدث خطأ أثناء إنشاء المستند المعدل: {e}")
                     error_occured = True
                     st.session_state.processed_file = None # Ensure no download if error

            elif not qna_pairs_with_headlines and not error_occured and total_pairs > 0:
                # Handles case where parsing found pairs, but *no* headlines were generated successfully
                st.error("لم يتم إنشاء أي عناوين بنجاح. لا يمكن إنشاء الملف المعدل.")
                st.session_state.processed_file = None


# --- Download Button ---
if st.session_state.processed_file is not None:
    original_name = st.session_state.original_filename or "document"
    # Remove extension and add suffix
    base_name = os.path.splitext(original_name)[0]
    # Get current date/time for uniqueness
    # Using current time based on server where Streamlit runs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    download_filename = f"{base_name}_with_headlines_{timestamp}.docx"

    st.download_button(
        label="⬇️ تحميل الملف المعدل",
        data=st.session_state.processed_file,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
elif api_key and uploaded_file is not None and not st.session_state.processed_file:
     # Show message if processing was attempted but failed before download state was set
     # Errors/warnings are shown during the processing steps, so this might not be needed
     pass


# --- Footer/Info ---
st.markdown("---")
st.info("يقوم هذا التطبيق بإجراء مكالمات لواجهة برمجة تطبيقات Google AI. قد يتم تطبيق تكاليف ومعدلات الاستخدام.")
