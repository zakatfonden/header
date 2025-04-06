import google.generativeai as genai
import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import io
import re
import copy
import traceback # Import traceback for better error logging

# --- Configuration ---

def configure_gemini(api_key):
    """Configures the Google Generative AI SDK."""
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        return False

# --- Document Parsing (Code remains the same as qna_backend_v5) ---

def parse_qna_pairs(docx_file):
    """
    Parses a DOCX file to extract Q&A pairs based on specific keywords.
    Primarily looks for paragraphs starting with 'السؤال'/'سؤال'/'Question'
    or 'الجواب'/'جواب'/'Answer'. Handles Arabic text.
    """
    qna_pairs = []
    current_q = None
    current_a = []
    q_start_index = -1
    is_parsing_answer = False

    try:
        if hasattr(docx_file, 'seek'):
            docx_file.seek(0)
        document = docx.Document(docx_file)
        all_paragraphs = document.paragraphs

        q_pattern = re.compile(r"^\s*(?:السؤال|سؤال|Question)\b\s*[:.)]?\s*", re.IGNORECASE)
        a_pattern = re.compile(r"^\s*(?:الجواب|جواب|Answer)\b\s*[:.)]?\s*", re.IGNORECASE)

        for i, para in enumerate(all_paragraphs):
            text = para.text.strip()
            if not text:
                continue

            is_question_start = q_pattern.match(text)
            is_answer_start = a_pattern.match(text)

            if is_question_start:
                if current_q and current_a:
                    qna_pairs.append({
                        "question": current_q.strip(),
                        "answer": "\n".join(current_a).strip(),
                        "q_para_index": q_start_index
                    })
                elif current_q and not current_a:
                     print(f"Warning: Question starting at index {q_start_index} ('{current_q[:50]}...') seems to have no corresponding answer before the next question.")

                current_q = q_pattern.sub('', text).strip()
                q_start_index = i
                current_a = []
                is_parsing_answer = False

            elif is_answer_start and current_q:
                answer_text = a_pattern.sub('', text).strip()
                if answer_text:
                    current_a.append(answer_text)
                is_parsing_answer = True

            elif current_q:
                 if is_parsing_answer:
                     if text: current_a.append(text)
                 else:
                     if text: current_q += "\n" + text

        if current_q and current_a:
            qna_pairs.append({
                "question": current_q.strip(),
                "answer": "\n".join(current_a).strip(),
                "q_para_index": q_start_index
            })
        elif current_q and not current_a:
             print(f"Warning: The last question found ('{current_q[:50]}...') appears to have no corresponding answer.")

        return qna_pairs, all_paragraphs

    except Exception as e:
        print(f"Error parsing DOCX: {e}")
        traceback.print_exc()
        return [], []

# --- Headline Generation (UPDATED SIGNATURE) ---

def generate_headline(question, answer, model_name, prompt_template):
    """
    Generates a headline for a given Q&A pair using the Gemini API,
    based on the provided model name and prompt template.

    Args:
        question (str): The question text (Arabic).
        answer (str): The answer text (Arabic).
        model_name (str): The Gemini model to use (e.g., 'gemini-1.5-flash').
        prompt_template (str): The template string for the prompt, containing
                               placeholders like {question} and {answer}.

    Returns:
        str: The generated headline in Arabic, or an error message string.
    """
    # Format the prompt using the template and the specific Q&A
    try:
        prompt = prompt_template.format(question=question, answer=answer)
    except KeyError as e:
        print(f"Error formatting prompt template. Missing key: {e}")
        traceback.print_exc()
        return f"خطأ في تنسيق القالب: مفتاح مفقود {e}" # Error in formatting template: Missing key {e}
    except Exception as e_fmt:
        print(f"Error formatting prompt template: {e_fmt}")
        traceback.print_exc()
        return f"خطأ غير متوقع في تنسيق القالب" # Unexpected error formatting template

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt) # Use the formatted prompt

        # Check for valid response and text attribute
        if hasattr(response, 'text') and response.text:
            headline = response.text.strip().replace('*', '').replace('#', '')
            return headline
        else:
            block_reason = "Unknown"
            # Check finish_reason if available (e.g., 'SAFETY')
            finish_reason = "N/A"
            if hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                 finish_reason = response.candidates[0].finish_reason.name # Get enum name
            # Check prompt feedback for safety blocks
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                 block_reason = str(response.prompt_feedback)
            print(f"Warning: Received empty or potentially blocked response. Finish Reason: {finish_reason}. Block Details: {block_reason}. Q: {question[:50]}...")
            return f"خطأ: استجابة فارغة أو محظورة (السبب: {finish_reason})" # Error: Empty or blocked response (Reason: {finish_reason})

    except Exception as e:
        print(f"Error generating headline with Gemini (Model: {model_name}): {e}")
        traceback.print_exc()
        # Provide more specific feedback if possible (e.g., API key invalid, model not found)
        error_msg = f"خطأ API عند إنشاء العنوان (النموذج: {model_name})" # API Error generating headline (Model: {model_name})
        if "API key not valid" in str(e):
            error_msg = "خطأ: مفتاح API غير صالح. يرجى التحقق منه في الشريط الجانبي." # Error: Invalid API key. Please check it in the sidebar.
        elif "permission" in str(e).lower() or "access" in str(e).lower():
             error_msg = f"خطأ: مشكلة في الإذن أو الوصول للنموذج {model_name}." # Error: Permission/access issue for model {model_name}.
        return error_msg


# --- Document Creation (Code remains the same as qna_backend_v5) ---

def create_modified_document(original_paragraphs, qna_pairs_with_headlines):
    """
    Creates a new DOCX document object with headlines inserted before Q&A pairs.
    """
    try:
        new_document = docx.Document()
        style = new_document.styles['Normal']
        font = style.font
        paragraph_format = style.paragraph_format
        paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

        headlines_map = {item['q_para_index']: item['headline'] for item in qna_pairs_with_headlines}
        processed_para_indices = set()
        qna_ranges = {}

        sorted_qna = sorted(qna_pairs_with_headlines, key=lambda x: x['q_para_index'])
        for i, item in enumerate(sorted_qna):
            q_index = item['q_para_index']
            next_q_start_index = len(original_paragraphs)
            if i + 1 < len(sorted_qna):
                next_q_start_index = sorted_qna[i+1]['q_para_index']

            qna_ranges[q_index] = next_q_start_index
            for j in range(q_index, next_q_start_index):
                processed_para_indices.add(j)

        para_index = 0
        while para_index < len(original_paragraphs):
            if para_index in headlines_map:
                headline_text = headlines_map[para_index]
                # Check if headline indicates an error before adding
                if "خطأ" in headline_text: # Basic check for error string from generate_headline
                     # Option 1: Add the error message as the headline
                     headline_para = new_document.add_paragraph()
                     headline_para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
                     runner = headline_para.add_run(f"[{headline_text}]") # Mark as error
                     runner.italic = True
                     runner.font.size = Pt(10)
                     # Option 2: Skip adding a headline entirely if error
                     # pass
                else:
                    # Add normal headline
                    headline_para = new_document.add_paragraph()
                    headline_para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
                    runner = headline_para.add_run(headline_text)
                    runner.bold = True
                    runner.font.size = Pt(14)

                end_index = qna_ranges[para_index]
                for i in range(para_index, end_index):
                    original_para = original_paragraphs[i]
                    new_para = new_document.add_paragraph(original_para.text)
                    new_para.alignment = original_para.alignment
                para_index = end_index

            elif para_index not in processed_para_indices:
                 original_para = original_paragraphs[para_index]
                 new_para = new_document.add_paragraph(original_para.text)
                 new_para.alignment = original_para.alignment
                 para_index += 1
            else:
                para_index += 1

        return new_document
    except Exception as e:
        print(f"Error creating modified document structure: {e}")
        traceback.print_exc()
        return None

# --- Document Merging (Code remains the same as qna_backend_v5) ---

def merge_documents(doc_list):
    """
    Merges multiple docx.Document objects into a single document.
    Copies paragraph text and basic run formatting. Inserts page breaks.
    """
    merged_document = docx.Document()
    style = merged_document.styles['Normal']
    paragraph_format = style.paragraph_format
    paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

    first_doc = True
    for doc_to_merge in doc_list:
        if not doc_to_merge:
            print("Warning: Skipping a None document object during merge.")
            continue
        if not first_doc:
            merged_document.add_page_break()
        first_doc = False
        for para in doc_to_merge.paragraphs:
            new_para = merged_document.add_paragraph()
            new_para.alignment = para.alignment
            for run in para.runs:
                new_run = new_para.add_run(run.text)
                new_run.bold = run.bold
                new_run.italic = run.italic
                new_run.underline = run.underline
                new_run.font.size = run.font.size
                new_run.font.name = run.font.name
    return merged_document

# --- Saving Document (Code remains the same as qna_backend_v5) ---

def save_doc_to_bytes(document):
    """Saves the DOCX document object to a byte stream."""
    doc_io = io.BytesIO()
    document.save(doc_io)
    doc_io.seek(0)
    return doc_io.getvalue()
