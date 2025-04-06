# app.py

import streamlit as st
import backend # Import the backend functions (qna_backend_v6)
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Q&A Headline Generator (Configurable)",
    page_icon="✨",
    layout="wide" # Use wide layout to better accommodate sidebar
)

# --- Default Prompt Template ---
# Moved from backend so it can be displayed and edited in the UI
# Uses .format() style placeholders
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
# Initialize prompt in session state if it doesn't exist
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
    # Add more models here if available and compatible with the API key/task
    available_models = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro'] # Example list
    selected_model = st.selectbox(
        "🤖 Select Gemini Model:",
        options=available_models,
        index=0, # Default to the first model in the list
        help="Choose the AI model for generating headlines."
    )

    # Editable Prompt Template
    st.subheader("📝 Prompt Template")
    st.markdown("""
    Edit the prompt used to instruct the AI. Use `{question}` and `{answer}` as placeholders for the actual content.
    """, help="The text below will be sent to the AI, with the placeholders replaced by the actual question and answer from your document.")

    # Use session state to store and retrieve the current prompt
    edited_prompt = st.text_area(
        "Prompt:",
        value=st.session_state.current_prompt_template,
        height=300 # Adjust height as needed
    )
    # Update session state when the text area changes
    st.session_state.current_prompt_template = edited_prompt

    if st.button("Reset Prompt to Default"):
        st.session_state.current_prompt_template = DEFAULT_PROMPT_TEMPLATE
        st.rerun() # Rerun to update the text area display

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
# Disable upload if API key is missing
file_uploader_disabled = not bool(api_key)
if not api_key:
    st.warning("Please enter your Google AI API Key in the sidebar to enable file upload.")

uploaded_files = st.file_uploader(
    "Choose one or more Word (.docx) files",
    type=["docx"],
    accept_multiple_files=True,
    disabled=file_uploader_disabled,
    key="file_uploader" # Add a key for potential state management if needed
)

# --- Processing Logic ---
if uploaded_files and api_key: # Check if list is not empty and key provided
    st.success(f"{len(uploaded_files)} file(s) selected.")
    st.session_state.processed_filenames = [f.name for f in uploaded_files]

    if st.button(f"🚀 Process {len(uploaded_files)} File(s) and Merge"):
        st.session_state.merged_processed_file = None # Reset download state
        processed_docs_list = []
        files_processed_count = 0
        files_error_count = 0
        total_files = len(uploaded_files)
        overall_progress = st.progress(0)
        status_messages = st.container()

        # Configure Gemini API once (using key from sidebar)
        api_key_configured = backend.configure_gemini(api_key)
        if not api_key_configured:
            st.error("Failed to configure the Gemini API with the provided key. Please check the key in the sidebar.")
            st.stop()

        # Get current prompt from session state (edited via sidebar)
        current_prompt = st.session_state.current_prompt_template
        # Get selected model from sidebar widget state
        current_model = selected_model

        status_messages.info(f"Using Model: `{current_model}`")

        # Process each file
        for i, uploaded_file in enumerate(uploaded_files):
            file_name = uploaded_file.name
            status_messages.info(f"Processing file {i+1}/{total_files}: {file_name}...")
            error_occured_this_file = False
            qna_pairs_with_headlines = []
            modified_doc_object = None

            try:
                # 1. Parse
                qna_pairs, original_paragraphs = backend.parse_qna_pairs(uploaded_file)
                if not qna_pairs:
                    status_messages.warning(f"File '{file_name}': Could not find Q&A pairs starting with 'السؤال'/'الجواب'. Skipping headline generation.")
                    error_occured_this_file = True
                else:
                    status_messages.write(f"File '{file_name}': Found {len(qna_pairs)} potential Q&A pair(s). Generating headlines...")

                # 2. Generate headlines (pass model and prompt)
                if not error_occured_this_file:
                    headlines_generated_this_file = 0
                    total_pairs_this_file = len(qna_pairs)
                    for pair_idx, pair in enumerate(qna_pairs):
                        # Call backend with selected model and current prompt
                        headline = backend.generate_headline(
                            pair['question'],
                            pair['answer'],
                            model_name=current_model,
                            prompt_template=current_prompt
                        )
                        # Check if headline indicates an error (starts with 'خطأ')
                        if "خطأ" not in headline:
                            pair['headline'] = headline
                            qna_pairs_with_headlines.append(pair)
                            headlines_generated_this_file += 1
                        else:
                            # Display the specific error message returned by the backend
                            status_messages.warning(f"File '{file_name}', Q starting '{pair['question'][:30]}...': {headline}")

                    # Report summary for the file
                    if headlines_generated_this_file == 0 and total_pairs_this_file > 0:
                         status_messages.warning(f"File '{file_name}': No headlines generated successfully.")
                    elif headlines_generated_this_file < total_pairs_this_file:
                         status_messages.write(f"File '{file_name}': Generated {headlines_generated_this_file}/{total_pairs_this_file} headlines.")
                    else:
                         status_messages.write(f"File '{file_name}': Generated {headlines_generated_this_file} headlines successfully.")


                # 3. Create modified doc object (pass pairs that got headlines)
                if qna_pairs_with_headlines: # Only create if some headlines were successful
                    modified_doc_object = backend.create_modified_document(original_paragraphs, qna_pairs_with_headlines)
                    if modified_doc_object is None:
                         status_messages.error(f"File '{file_name}': Failed to create the modified document structure.")
                         error_occured_this_file = True # Mark as error if creation fails
                elif not error_occured_this_file and qna_pairs: # Pairs found but no headlines generated
                     status_messages.warning(f"File '{file_name}': No headlines generated, cannot create modified content section.")
                     error_occured_this_file = True # Treat as error for merging modified content


            except Exception as e_proc:
                status_messages.error(f"Critical error processing file '{file_name}': {e_proc}")
                import traceback
                traceback.print_exc()
                error_occured_this_file = True

            # Add successfully processed document object to list
            if not error_occured_this_file and modified_doc_object:
                processed_docs_list.append(modified_doc_object)
                files_processed_count += 1
            elif not modified_doc_object: # Covers parsing errors or headline generation failures leading to no doc obj
                files_error_count += 1

            overall_progress.progress((i + 1) / total_files)

        overall_progress.empty()

        # 4. Merge documents if any were successful
        if processed_docs_list:
            status_messages.info(f"Merging content from {files_processed_count} successfully processed file(s)...")
            try:
                merged_doc = backend.merge_documents(processed_docs_list)
                st.session_state.merged_processed_file = backend.save_doc_to_bytes(merged_doc)
                st.success(f"Processing complete! Merged content from {files_processed_count} file(s).")
                if files_error_count > 0:
                     st.warning(f"{files_error_count} file(s) encountered errors or had no content to merge.")
                st.balloons()
            except Exception as e_merge:
                st.error(f"Error merging documents: {e_merge}")
                st.session_state.merged_processed_file = None
        else:
            st.error("No files were processed successfully. Cannot create a merged document.")
            st.session_state.merged_processed_file = None


# --- Download Button ---
if st.session_state.merged_processed_file is not None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    download_filename = f"merged_qna_headlines_{timestamp}.docx"

    st.download_button(
        label="⬇️ Download Merged File",
        data=st.session_state.merged_processed_file,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

# --- Footer/Info ---
st.markdown("---")
# Intentionally removing the API cost warning as it's less direct now
# st.info("This application makes calls to the Google AI API. Usage costs and rate limits may apply.")

