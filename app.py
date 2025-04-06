# app.py

import streamlit as st
import backend # Import the backend functions
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Q&A Headline Generator", # English Title
    page_icon="✨"
)

# --- App Interface ---
st.title("✨ Automatic Q&A Headline Generator ✨") # English Title
st.markdown("""
Upload a Word (.docx) file containing questions and answers in Arabic.
Enter your Google AI API Key below, upload your file, and click the process button.
The application will automatically generate a headline (in Arabic) for each question-answer pair and insert it into the document.

**Expected File Format:**
* Each question should start with `س:` or `Q:` (optional space and colon allowed, case-insensitive).
* Each answer should start with `ج:` or `A:` (optional space and colon allowed, case-insensitive).
* Paragraphs following the question or answer (before the next Q/A marker) will be treated as part of it.
""") # English Instructions

# --- API Key Input ---
api_key = st.text_input(
    "🔑 Enter your Google AI API Key here:", # English Label
    type="password",
    help="Get your key from Google AI Studio. Your key will not be stored." # English Help Text
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
    "Choose a Word (.docx) file", # English Label
    type=["docx"],
    disabled=file_uploader_disabled
)

if not api_key:
    st.warning("Please enter your Google AI API Key to continue.") # English Warning

# --- Processing Logic ---
if uploaded_file is not None and api_key:
    st.success(f"File uploaded: {uploaded_file.name}") # English Success Msg
    st.session_state.original_filename = uploaded_file.name # Store filename

    if st.button("🚀 Process File and Generate Headlines"): # English Button Label
        st.session_state.processed_file = None # Reset download state
        error_occured = False
        qna_pairs_with_headlines = []

        # Configure Gemini with the provided key *before* processing
        api_key_configured = backend.configure_gemini(api_key)

        if not api_key_configured:
            st.error("Failed to configure the Gemini API with the provided key. Please check the key and try again.") # English Error
            st.stop() # Stop execution if API key is invalid

        with st.spinner("Analyzing document and calling AI... This may take a moment."): # English Spinner Text
            # 1. Parse the document
            try:
                # Pass the uploaded file object directly
                qna_pairs, original_paragraphs = backend.parse_qna_pairs(uploaded_file)
                if not qna_pairs:
                    st.warning("No Q&A pairs found in the expected format (س:/ج: or Q:/A:). Please check the file.") # English Warning
                    error_occured = True
                else:
                    st.info(f"Found {len(qna_pairs)} Q&A pair(s).") # English Info Msg

            except Exception as e:
                st.error(f"Error parsing Word file: {e}") # English Error
                error_occured = True


            # 2. Generate headlines if parsing succeeded
            if not error_occured:
                progress_bar = st.progress(0)
                headlines_generated = 0
                total_pairs = len(qna_pairs) # Store total number before filtering

                for i, pair in enumerate(qna_pairs):
                    try:
                        # Backend still generates Arabic headline based on its internal prompt
                        headline = backend.generate_headline(pair['question'], pair['answer'])
                        if headline and not headline.startswith("خطأ"): # Check for success (backend returns Arabic error prefix on failure)
                            pair['headline'] = headline
                            qna_pairs_with_headlines.append(pair) # Only add pairs with successful headlines
                            headlines_generated += 1
                        else:
                            # Display warning in English, but show the start of the Arabic question
                            st.warning(f"Could not generate headline for question starting with: '{pair['question'][:50]}...' (Reason: {headline or 'API Failure'})")
                    except Exception as e:
                         # Display error in English, show start of Arabic question
                        st.error(f"Error generating headline for question: '{pair['question'][:50]}...' Error: {e}")

                    # Update progress based on total pairs initially found
                    progress_bar.progress((i + 1) / total_pairs if total_pairs > 0 else 0)

                progress_bar.empty() # Remove progress bar after loop

                if headlines_generated == 0 and total_pairs > 0:
                    st.error("No headlines were generated successfully. There might be an issue connecting to the Gemini API or with the file format.") # English Error
                    error_occured = True # Mark error if no headlines generated
                elif headlines_generated < total_pairs:
                    st.warning(f"Successfully generated {headlines_generated} headlines out of {total_pairs} pairs found.") # English Warning
                elif total_pairs == 0:
                    pass # Already handled by the parsing warning
                else:
                    st.success(f"Successfully generated {headlines_generated} headlines!") # English Success


            # 3. Create the modified document only if headlines were generated successfully
            if not error_occured and qna_pairs_with_headlines:
                 try:
                     # Backend still handles inserting Arabic headlines correctly
                     modified_doc = backend.create_modified_document(original_paragraphs, qna_pairs_with_headlines)
                     st.session_state.processed_file = backend.save_doc_to_bytes(modified_doc)
                     st.balloons() # Fun success indicator
                 except Exception as e:
                     st.error(f"Error creating the modified document: {e}") # English Error
                     error_occured = True
                     st.session_state.processed_file = None # Ensure no download if error

            elif not qna_pairs_with_headlines and not error_occured and total_pairs > 0:
                # Handles case where parsing found pairs, but *no* headlines were generated successfully
                st.error("No headlines were successfully generated. Cannot create the modified file.") # English Error
                st.session_state.processed_file = None


# --- Download Button ---
if st.session_state.processed_file is not None:
    original_name = st.session_state.original_filename or "document"
    # Remove extension and add suffix
    base_name = os.path.splitext(original_name)[0]
    # Get current date/time for uniqueness
    # Using current time based on server where Streamlit runs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    download_filename = f"{base_name}_with_Arabic_headlines_{timestamp}.docx" # Clarified filename

    st.download_button(
        label="⬇️ Download Modified File", # English Label
        data=st.session_state.processed_file,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
elif api_key and uploaded_file is not None and not st.session_state.processed_file:
     pass


# --- Footer/Info ---
st.markdown("---")
st.info("This application makes calls to the Google AI API. Usage costs and rate limits may apply.") # English Info
