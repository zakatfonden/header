# app.py

import streamlit as st
import backend # Import the backend functions
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Q&A Headline Generator",
    page_icon="✨"
)

# --- App Interface ---
st.title("✨ Automatic Q&A Headline Generator ✨")
st.markdown("""
Upload a Word (.docx) file containing questions and answers in Arabic.
Enter your Google AI API Key below, upload your file, and click the process button.
The application will automatically generate a headline (in Arabic) for each question-answer pair and insert it into the document.

**Expected File Format:**
* The app primarily looks for paragraphs starting with the word **`سؤال`** (or `Question`) to identify questions.
* It looks for paragraphs starting with the word **`جواب`** (or `Answer`) to identify answers.
    *(Variations in spacing/punctuation after these words are usually handled)*.
* Paragraphs following a question marker (before an answer marker) are assumed to be part of the question.
* Paragraphs following an answer marker (before the next question marker) are assumed to be part of the answer.
* **Important:** If these keywords are missing, the app might not correctly identify all Q&A pairs. It cannot reliably understand the structure without these common markers.
""") # English Instructions Updated

# --- API Key Input ---
api_key = st.text_input(
    "🔑 Enter your Google AI API Key here:",
    type="password",
    help="Get your key from Google AI Studio. Your key will not be stored."
)

# Initialize session state for download
if 'processed_file' not in st.session_state:
    st.session_state.processed_file = None
if 'original_filename' not in st.session_state:
    st.session_state.original_filename = None

# --- File Upload ---
file_uploader_disabled = not bool(api_key)
uploaded_file = st.file_uploader(
    "Choose a Word (.docx) file",
    type=["docx"],
    disabled=file_uploader_disabled
)

if not api_key:
    st.warning("Please enter your Google AI API Key to continue.")

# --- Processing Logic ---
if uploaded_file is not None and api_key:
    st.success(f"File uploaded: {uploaded_file.name}")
    st.session_state.original_filename = uploaded_file.name

    if st.button("🚀 Process File and Generate Headlines"):
        st.session_state.processed_file = None
        error_occured = False
        qna_pairs_with_headlines = []

        api_key_configured = backend.configure_gemini(api_key)

        if not api_key_configured:
            st.error("Failed to configure the Gemini API with the provided key. Please check the key and try again.")
            st.stop()

        with st.spinner("Analyzing document and calling AI... This may take a moment."):
            # 1. Parse the document using the updated backend logic
            try:
                qna_pairs, original_paragraphs = backend.parse_qna_pairs(uploaded_file)
                if not qna_pairs:
                    # Updated warning message
                    st.warning("Could not find Q&A pairs starting with 'سؤال'/'Question' or 'جواب'/'Answer'. Please check the file format.")
                    error_occured = True
                else:
                    st.info(f"Found {len(qna_pairs)} potential Q&A pair(s) based on keywords.")

            except Exception as e:
                st.error(f"Error parsing Word file: {e}")
                error_occured = True

            # 2. Generate headlines if parsing found pairs
            if not error_occured and qna_pairs: # Ensure qna_pairs is not empty
                progress_bar = st.progress(0)
                headlines_generated = 0
                total_pairs = len(qna_pairs)

                for i, pair in enumerate(qna_pairs):
                    try:
                        headline = backend.generate_headline(pair['question'], pair['answer'])
                        if headline and not headline.startswith("خطأ"):
                            pair['headline'] = headline
                            qna_pairs_with_headlines.append(pair)
                            headlines_generated += 1
                        else:
                            st.warning(f"Could not generate headline for question starting with: '{pair['question'][:50]}...' (Reason: {headline or 'API Failure'})")
                    except Exception as e:
                        st.error(f"Error generating headline for question: '{pair['question'][:50]}...' Error: {e}")

                    progress_bar.progress((i + 1) / total_pairs if total_pairs > 0 else 0)

                progress_bar.empty()

                if headlines_generated == 0 and total_pairs > 0:
                    st.error("No headlines were generated successfully. There might be an issue connecting to the Gemini API.")
                    error_occured = True # Mark error if no headlines generated
                elif headlines_generated < total_pairs:
                    st.warning(f"Successfully generated {headlines_generated} headlines out of {total_pairs} pairs found.")
                elif total_pairs == 0:
                     # This case should be caught by the initial parsing warning
                     pass
                else:
                    st.success(f"Successfully generated {headlines_generated} headlines!")


            # 3. Create the modified document only if headlines were generated successfully
            # Check specifically if qna_pairs_with_headlines has content
            if not error_occured and qna_pairs_with_headlines:
                 try:
                     modified_doc = backend.create_modified_document(original_paragraphs, qna_pairs_with_headlines)
                     st.session_state.processed_file = backend.save_doc_to_bytes(modified_doc)
                     st.balloons()
                 except Exception as e:
                     st.error(f"Error creating the modified document: {e}")
                     error_occured = True
                     st.session_state.processed_file = None

            elif not qna_pairs_with_headlines and not error_occured and qna_pairs: # Check if parsing found pairs but none got headlines
                st.error("No headlines were successfully generated. Cannot create the modified file.")
                st.session_state.processed_file = None
            elif not qna_pairs: # Handles case where parsing found nothing initially
                 st.session_state.processed_file = None # Ensure no download button


# --- Download Button ---
if st.session_state.processed_file is not None:
    original_name = st.session_state.original_filename or "document"
    base_name = os.path.splitext(original_name)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    download_filename = f"{base_name}_with_Arabic_headlines_{timestamp}.docx"

    st.download_button(
        label="⬇️ Download Modified File",
        data=st.session_state.processed_file,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
elif api_key and uploaded_file is not None and not st.session_state.processed_file:
     pass


# --- Footer/Info ---
st.markdown("---")
st.info("This application makes calls to the Google AI API. Usage costs and rate limits may apply.")
