# app.py

import streamlit as st
import backend # Import the backend functions (qna_backend_v6)
import os
from datetime import datetime
import traceback # Import traceback for better error logging

# --- Page Configuration ---
st.set_page_config(
    page_title="Q&A Headline Generator (Configurable)",
    page_icon="✨",
    layout="wide" # Use wide layout to better accommodate sidebar
)

# --- Default Prompt Template ---
DEFAULT_PROMPT_TEMPLATE = """السؤال التالي وإجابته مقتبسان من وثيقة. قم بإنشاء عنوان قصير ومناسب باللغة العربية يلخص الموضوع الرئيسي لهذا السؤال والإجابة. اجعل العنوان موجزًا وواضحًا. لا تقم بتضمين الكلمات "سؤال" أو "إجابة" في العنوان.

السؤال:
{question}

الإجابة:
{answer}

العنوان المقترح:"""

# --- Initialize Session State ---
if 'merged_processed_file' not in st.session_state:
    st.session_state.merged_processed_file = None
if 'processed_filenames' not in st.session_state:
    st.session_state.processed_filenames = []
if 'current_prompt_template' not in st.session_state:
    st.session_state.current_prompt_template = DEFAULT_PROMPT_TEMPLATE

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("⚙️ Configuration")

    # API Key Input
    api_key = st.text_input(
        "🔑 Google AI API Key:",
        type="password",
        help="Get your key from Google AI Studio. Your key will not be stored persistently."
    )

    # Model Selection
    available_models = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    selected_model = st.selectbox(
        "🤖 Select Gemini Model:",
        options=available_models,
        index=0,
        help="Choose the AI model for generating headlines."
    )

    # Editable Prompt Template
    st.subheader("📝 Prompt Template")
    st.markdown("""
    Edit the prompt used to instruct the AI. Use `{question}` and `{answer}` as placeholders for the actual content.
    """, help="The text below will be sent to the AI, with the placeholders replaced by the actual question and answer from your document.")

    edited_prompt = st.text_area(
        "Prompt:",
        value=st.session_state.current_prompt_template,
        height=300
    )
    st.session_state.current_prompt_template = edited_prompt

    if st.button("Reset Prompt to Default"):
        st.session_state.current_prompt_template = DEFAULT_PROMPT_TEMPLATE
        st.rerun()

# --- Main Page Interface ---
st.title("✨ Automatic Q&A Headline Generator ✨")
st.markdown("""
Upload one or more Word (.docx) files containing questions and answers in Arabic.
Configure the API Key, Model, and Prompt in the sidebar (←).
The application will process each file using your settings and merge the results into a single downloadable document.

**Expected File Format (for each file):**
* Starts with **`السؤال`** (or `سؤال`, `Question`).
* Starts with **`الجواب`** (or `جواب`, `Answer`).
* **Merging Note:** Results are merged with page breaks. Complex formatting may be lost.
""")

# --- File Upload ---
file_uploader_disabled = not bool(api_key)
if not api_key:
    st.warning("Please enter your Google AI API Key in the sidebar to enable file upload.")

uploaded_files = st.file_uploader(
    "Choose one or more Word (.docx) files",
    type=["docx"],
    accept_multiple_files=True,
    disabled=file_uploader_disabled,
    key="file_uploader"
)

# --- Processing Logic ---
if uploaded_files and api_key:
    st.success(f"{len(uploaded_files)} file(s) selected.")
    st.session_state.processed_filenames = [f.name for f in uploaded_files]

    if st.button(f"🚀 Process {len(uploaded_files)} File(s) and Merge"):

        # --- Placeholders for Download Button and Status ---
        # Define placeholders *before* starting the process
        download_placeholder = st.empty()
        processing_status_placeholder = st.empty()

        # --- Start Processing within the Status Placeholder ---
        with processing_status_placeholder.container():
            st.session_state.merged_processed_file = None # Reset state
            processed_docs_list = []
            files_processed_count = 0
            files_error_count = 0
            total_files = len(uploaded_files)
            overall_progress = st.progress(0) # Progress bar inside the container

            # Configure Gemini API
            api_key_configured = backend.configure_gemini(api_key)
            if not api_key_configured:
                st.error("Failed to configure the Gemini API with the provided key. Please check the key in the sidebar.")
                st.stop() # Stop if API key fails

            # Get current settings from sidebar/session state
            current_prompt = st.session_state.current_prompt_template
            current_model = selected_model
            st.info(f"Using Model: `{current_model}`") # Show model info

            # --- Process each file ---
            for i, uploaded_file in enumerate(uploaded_files):
                file_name = uploaded_file.name
                st.info(f"Processing file {i+1}/{total_files}: {file_name}...") # Status update
                error_occured_this_file = False
                qna_pairs_with_headlines = []
                modified_doc_object = None

                try:
                    # 1. Parse
                    qna_pairs, original_paragraphs = backend.parse_qna_pairs(uploaded_file)
                    if not qna_pairs:
                        st.warning(f"File '{file_name}': Could not find Q&A pairs starting with 'السؤال'/'الجواب'. Skipping headline generation.")
                        error_occured_this_file = True
                    else:
                        st.write(f"File '{file_name}': Found {len(qna_pairs)} potential Q&A pair(s). Generating headlines...")

                    # 2. Generate headlines
                    if not error_occured_this_file:
                        headlines_generated_this_file = 0
                        total_pairs_this_file = len(qna_pairs)
                        for pair_idx, pair in enumerate(qna_pairs):
                            headline = backend.generate_headline(
                                pair['question'], pair['answer'],
                                model_name=current_model, prompt_template=current_prompt
                            )
                            if "خطأ" not in headline: # Check for backend error string
                                pair['headline'] = headline
                                qna_pairs_with_headlines.append(pair)
                                headlines_generated_this_file += 1
                            else:
                                st.warning(f"File '{file_name}', Q starting '{pair['question'][:30]}...': {headline}") # Display specific error

                        # Report summary
                        if headlines_generated_this_file == 0 and total_pairs_this_file > 0:
                             st.warning(f"File '{file_name}': No headlines generated successfully.")
                        elif headlines_generated_this_file < total_pairs_this_file:
                             st.write(f"File '{file_name}': Generated {headlines_generated_this_file}/{total_pairs_this_file} headlines.")
                        # No need for success message here, covered by overall summary later

                    # 3. Create modified doc object
                    if qna_pairs_with_headlines:
                        modified_doc_object = backend.create_modified_document(original_paragraphs, qna_pairs_with_headlines)
                        if modified_doc_object is None:
                             st.error(f"File '{file_name}': Failed to create the modified document structure.")
                             error_occured_this_file = True
                    elif not error_occured_this_file and qna_pairs:
                         st.warning(f"File '{file_name}': No headlines generated, cannot create modified content section.")
                         error_occured_this_file = True

                except Exception as e_proc:
                    st.error(f"Critical error processing file '{file_name}': {e_proc}")
                    traceback.print_exc() # Log detailed error
                    error_occured_this_file = True

                # Add successfully processed doc object
                if not error_occured_this_file and modified_doc_object:
                    processed_docs_list.append(modified_doc_object)
                    files_processed_count += 1
                elif not modified_doc_object:
                    files_error_count += 1

                # Update progress bar
                overall_progress.progress((i + 1) / total_files)

            # --- End of File Loop ---
            overall_progress.empty() # Remove progress bar after loop

            # --- Merging ---
            if processed_docs_list:
                st.info(f"Merging content from {files_processed_count} successfully processed file(s)...")
                try:
                    merged_doc = backend.merge_documents(processed_docs_list)
                    # Store result in session state BEFORE populating download button
                    st.session_state.merged_processed_file = backend.save_doc_to_bytes(merged_doc)
                    st.success(f"Processing complete! Merged content from {files_processed_count} file(s).")
                    if files_error_count > 0:
                         st.warning(f"{files_error_count} file(s) encountered errors or had no content to merge.")
                except Exception as e_merge:
                    st.error(f"Error merging documents: {e_merge}")
                    traceback.print_exc()
                    st.session_state.merged_processed_file = None
            else:
                st.error("No files were processed successfully. Cannot create a merged document.")
                st.session_state.merged_processed_file = None

        # --- End of processing within the status placeholder ---

        # --- Populate Download Button Placeholder (AFTER processing) ---
        # This code runs *after* the 'with processing_status_placeholder.container():' block finishes
        if st.session_state.merged_processed_file is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            download_filename = f"merged_qna_headlines_{timestamp}.docx"

            # Use the placeholder created *before* the processing block
            with download_placeholder.container():
                st.download_button(
                    label="⬇️ Download Merged File",
                    data=st.session_state.merged_processed_file,
                    file_name=download_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="download_button" # Unique key for the button
                )
                st.balloons() # Show balloons on success near download button
            # Optional: Clear the status messages now that download is ready
            # processing_status_placeholder.empty()


# --- Footer/Info ---
st.markdown("---")

