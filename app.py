# app.py

import streamlit as st
import backend # Import the backend functions (qna_backend_v5)
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Q&A Headline Generator (Multi-File)",
    page_icon="✨"
)

# --- App Interface ---
st.title("✨ Automatic Q&A Headline Generator (Multi-File) ✨")
st.markdown("""
Upload one or more Word (.docx) files containing questions and answers in Arabic.
Enter your Google AI API Key, upload your files, and click the process button.
The application will process each file, generate headlines (in Arabic) for each Q&A pair,
and then **merge the results into a single downloadable Word document**.

**Expected File Format (for each file):**
* The app primarily looks for paragraphs starting with **`السؤال`** (or `سؤال`, `Question`).
* It looks for paragraphs starting with **`الجواب`** (or `جواب`, `Answer`).
    *(Variations in spacing/punctuation after these words are usually handled)*.
* Paragraphs following markers are assumed to be part of the Q or A.
* **Merging Note:** The final merged document will contain the processed content of all uploaded files, separated by page breaks. Complex formatting (headers, footers, etc.) might be lost during merging.
""")

# --- API Key Input ---
api_key = st.text_input(
    "🔑 Enter your Google AI API Key here:",
    type="password",
    help="Get your key from Google AI Studio. Your key will not be stored."
)

# Initialize session state
if 'merged_processed_file' not in st.session_state:
    st.session_state.merged_processed_file = None
if 'processed_filenames' not in st.session_state:
    st.session_state.processed_filenames = []


# --- File Upload ---
file_uploader_disabled = not bool(api_key)
uploaded_files = st.file_uploader(
    "Choose one or more Word (.docx) files", # Updated Label
    type=["docx"],
    accept_multiple_files=True, # Allow multiple files
    disabled=file_uploader_disabled
)

if not api_key:
    st.warning("Please enter your Google AI API Key to continue.")

# --- Processing Logic ---
if uploaded_files and api_key: # Check if list is not empty
    st.success(f"{len(uploaded_files)} file(s) selected.")
    st.session_state.processed_filenames = [f.name for f in uploaded_files]

    if st.button(f"🚀 Process {len(uploaded_files)} File(s) and Merge"): # Updated Button Label
        st.session_state.merged_processed_file = None # Reset download state
        processed_docs_list = [] # To store processed doc objects
        files_processed_count = 0
        files_error_count = 0
        total_files = len(uploaded_files)
        overall_progress = st.progress(0)
        status_messages = st.container() # To display per-file status

        # Configure Gemini API once
        api_key_configured = backend.configure_gemini(api_key)
        if not api_key_configured:
            st.error("Failed to configure the Gemini API with the provided key. Please check the key and try again.")
            st.stop()

        # Process each file
        for i, uploaded_file in enumerate(uploaded_files):
            file_name = uploaded_file.name
            status_messages.info(f"Processing file {i+1}/{total_files}: {file_name}...")
            error_occured_this_file = False
            qna_pairs_with_headlines = []
            modified_doc_object = None # Initialize for this file

            try:
                # 1. Parse the document
                qna_pairs, original_paragraphs = backend.parse_qna_pairs(uploaded_file)
                if not qna_pairs:
                    status_messages.warning(f"File '{file_name}': Could not find Q&A pairs starting with 'السؤال'/'الجواب'. Skipping headline generation for this file.")
                    # We might still want to include its original content in merge, or skip entirely
                    # For now, let's skip adding it to processed_docs_list if no pairs found
                    error_occured_this_file = True # Consider this an "error" for merging purposes
                else:
                    status_messages.write(f"File '{file_name}': Found {len(qna_pairs)} potential Q&A pair(s). Generating headlines...")

                # 2. Generate headlines if parsing found pairs
                if not error_occured_this_file:
                    headlines_generated_this_file = 0
                    total_pairs_this_file = len(qna_pairs)
                    for pair_idx, pair in enumerate(qna_pairs):
                        try:
                            headline = backend.generate_headline(pair['question'], pair['answer'])
                            if headline and not headline.startswith("خطأ"):
                                pair['headline'] = headline
                                qna_pairs_with_headlines.append(pair)
                                headlines_generated_this_file += 1
                            else:
                                status_messages.warning(f"File '{file_name}', Q starting '{pair['question'][:30]}...': Could not generate headline ({headline or 'API Failure'}).")
                        except Exception as e_gen:
                            status_messages.error(f"File '{file_name}', Q starting '{pair['question'][:30]}...': Error during headline generation: {e_gen}")

                    if headlines_generated_this_file == 0 and total_pairs_this_file > 0:
                         status_messages.warning(f"File '{file_name}': No headlines generated successfully.")
                         # Decide if this constitutes an error preventing merge inclusion
                         # error_occured_this_file = True
                    elif headlines_generated_this_file < total_pairs_this_file:
                         status_messages.write(f"File '{file_name}': Generated {headlines_generated_this_file}/{total_pairs_this_file} headlines.")
                    else:
                         status_messages.write(f"File '{file_name}': Generated {headlines_generated_this_file} headlines successfully.")


                # 3. Create the modified document object if headlines were generated
                if not error_occured_this_file and qna_pairs_with_headlines:
                    modified_doc_object = backend.create_modified_document(original_paragraphs, qna_pairs_with_headlines)
                    if modified_doc_object is None:
                         status_messages.error(f"File '{file_name}': Failed to create the modified document structure.")
                         error_occured_this_file = True
                elif not error_occured_this_file and not qna_pairs_with_headlines and qna_pairs:
                     # Case: Pairs found, but NO headlines generated. Should we include original content?
                     # For now, treat as error for adding headlines, don't create modified doc object.
                     status_messages.warning(f"File '{file_name}': No headlines generated, cannot create modified content section.")
                     error_occured_this_file = True # Treat as error for merging modified content
                elif error_occured_this_file: # If parsing failed
                     pass # Already handled


            except Exception as e_proc:
                status_messages.error(f"Error processing file '{file_name}': {e_proc}")
                import traceback
                traceback.print_exc() # Log full traceback to console/logs
                error_occured_this_file = True

            # Add successfully processed document object to list for merging
            if not error_occured_this_file and modified_doc_object:
                processed_docs_list.append(modified_doc_object)
                files_processed_count += 1
            elif error_occured_this_file:
                files_error_count += 1

            # Update overall progress
            overall_progress.progress((i + 1) / total_files)

        overall_progress.empty() # Remove progress bar

        # 4. Merge the processed documents if any were successful
        if processed_docs_list:
            status_messages.info(f"Merging content from {files_processed_count} successfully processed file(s)...")
            try:
                merged_doc = backend.merge_documents(processed_docs_list)
                st.session_state.merged_processed_file = backend.save_doc_to_bytes(merged_doc)
                st.success(f"Processing complete! Merged content from {files_processed_count} file(s).")
                if files_error_count > 0:
                     st.warning(f"{files_error_count} file(s) encountered errors and were not included in the merge.")
                st.balloons()
            except Exception as e_merge:
                st.error(f"Error merging documents: {e_merge}")
                st.session_state.merged_processed_file = None
        else:
            st.error("No files were processed successfully. Cannot create a merged document.")
            st.session_state.merged_processed_file = None


# --- Download Button ---
if st.session_state.merged_processed_file is not None:
    # Create a generic filename or base it on the first processed file?
    # Using a generic name for simplicity
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    download_filename = f"merged_qna_headlines_{timestamp}.docx"

    st.download_button(
        label="⬇️ Download Merged File", # Updated Label
        data=st.session_state.merged_processed_file,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# --- Footer/Info ---
st.markdown("---")
st.info("This application makes calls to the Google AI API. Usage costs and rate limits may apply.")

