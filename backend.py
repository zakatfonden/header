import google.generativeai as genai
import docx
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import io
import re # Import regular expressions for parsing

# --- Configuration ---

def configure_gemini(api_key):
    """Configures the Google Generative AI SDK."""
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        return False

# --- Document Parsing ---

def parse_qna_pairs(docx_file):
    """
    Parses a DOCX file to extract Q&A pairs based on specific keywords.
    Primarily looks for paragraphs starting with 'سؤال'/'Question' or 'جواب'/'Answer'.
    Handles Arabic text.

    Args:
        docx_file (file-like object): The uploaded Word document.

    Returns:
        list: A list of dictionaries, each containing 'question', 'answer',
              and 'q_para_index' (index of the first paragraph of the question).
              Returns an empty list if parsing fails or no pairs are found.
        list: A list of all paragraphs from the original document.
    """
    qna_pairs = []
    current_q = None
    current_a = []
    q_start_index = -1
    is_parsing_answer = False # Flag to know if we are currently collecting answer paragraphs

    try:
        document = docx.Document(docx_file)
        all_paragraphs = document.paragraphs

        # Define regex patterns for flexibility (handles whitespace, optional punctuation)
        # Using \b for word boundary to avoid matching parts of words. Case-insensitive.
        # Allows for optional : . ) after the keyword
        q_pattern = re.compile(r"^\s*(?:سؤال|Question)\b\s*[:.)]?\s*", re.IGNORECASE)
        a_pattern = re.compile(r"^\s*(?:جواب|Answer)\b\s*[:.)]?\s*", re.IGNORECASE)

        for i, para in enumerate(all_paragraphs):
            text = para.text.strip()
            # Skip empty paragraphs for detection logic
            if not text:
                continue

            is_question_start = q_pattern.match(text)
            is_answer_start = a_pattern.match(text)

            if is_question_start:
                # If we find a new question, store the previous Q&A pair if complete
                if current_q and current_a:
                    qna_pairs.append({
                        "question": current_q.strip(),
                        "answer": "\n".join(current_a).strip(),
                        "q_para_index": q_start_index
                    })
                elif current_q and not current_a:
                     # Handle case where a question was found but no answer followed before the next question
                     print(f"Warning: Question starting at index {q_start_index} ('{current_q[:50]}...') seems to have no corresponding answer before the next question.")
                     # Optionally add it with an empty answer:
                     # qna_pairs.append({"question": current_q.strip(), "answer": "", "q_para_index": q_start_index})


                # Start the new question
                # Remove the marker (e.g., "سؤال:") from the question text itself
                current_q = q_pattern.sub('', text).strip()
                q_start_index = i
                current_a = [] # Reset answer
                is_parsing_answer = False # We are now parsing the question part

            elif is_answer_start and current_q:
                # Start the answer only if we have a current question active
                # Remove the marker (e.g., "جواب:") from the answer text
                answer_text = a_pattern.sub('', text).strip()
                if answer_text: # Only add non-empty answer parts
                    current_a.append(answer_text)
                is_parsing_answer = True # We are now parsing the answer part

            elif current_q: # If we have an active question...
                 # And it's not the start of a new Q or A...
                 if is_parsing_answer:
                     # If we've already started the answer, append to answer
                     if text: current_a.append(text)
                 else:
                     # If we haven't started the answer yet, append to the question
                     if text: current_q += "\n" + text

            # else: Paragraph is before the first question or doesn't seem related, ignore for Q&A pairing.


        # Add the last Q&A pair if it exists and has an answer
        if current_q and current_a:
            qna_pairs.append({
                "question": current_q.strip(),
                "answer": "\n".join(current_a).strip(),
                "q_para_index": q_start_index
            })
        elif current_q and not current_a:
             # Handle the very last question potentially having no answer in the doc
             print(f"Warning: The last question found ('{current_q[:50]}...') appears to have no corresponding answer.")
             # Optionally add it with an empty answer:
             # qna_pairs.append({"question": current_q.strip(), "answer": "", "q_para_index": q_start_index})


        return qna_pairs, all_paragraphs

    except Exception as e:
        print(f"Error parsing DOCX: {e}")
        # Consider raising the error or returning a specific error indicator
        return [], [] # Return empty lists on error

# --- Headline Generation (No changes needed here) ---

def generate_headline(question, answer, model_name="gemini-1.5-flash"):
    """
    Generates a headline for a given Q&A pair using the Gemini API.
    (Kept the Arabic prompt as document content is Arabic)

    Args:
        question (str): The question text (Arabic).
        answer (str): The answer text (Arabic).
        model_name (str): The Gemini model to use.

    Returns:
        str: The generated headline in Arabic, or None if an error occurs.
    """
    prompt = f"""
    السؤال التالي وإجابته مقتبسان من وثيقة. قم بإنشاء عنوان قصير ومناسب باللغة العربية يلخص الموضوع الرئيسي لهذا السؤال والإجابة. اجعل العنوان موجزًا وواضحًا. لا تقم بتضمين الكلمات "سؤال" أو "إجابة" في العنوان.

    السؤال:
    {question}

    الإجابة:
    {answer}

    العنوان المقترح:
    """

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        if response.text:
            headline = response.text.strip().replace('*', '').replace('#', '')
            return headline
        else:
            print(f"Warning: Received empty or blocked response for Q: {question[:50]}...")
            # Check response.prompt_feedback for block reasons if needed
            return f"خطأ في إنشاء عنوان للسؤال: {question[:30]}..." # Placeholder error headline

    except Exception as e:
        print(f"Error generating headline with Gemini: {e}")
        return f"خطأ في إنشاء عنوان للسؤال: {question[:30]}..." # Placeholder error headline


# --- Document Creation (No changes needed here) ---

def create_modified_document(original_paragraphs, qna_pairs_with_headlines):
    """
    Creates a new DOCX document with headlines inserted before Q&A pairs.

    Args:
        original_paragraphs (list): List of all paragraphs from the original doc.
        qna_pairs_with_headlines (list): List of Q&A dicts, now including a 'headline' key.

    Returns:
        docx.Document: The new document object with headlines.
    """
    new_document = docx.Document()
    style = new_document.styles['Normal']
    font = style.font
    paragraph_format = style.paragraph_format
    paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

    headlines_map = {item['q_para_index']: item['headline'] for item in qna_pairs_with_headlines}
    processed_para_indices = set()
    qna_ranges = {} # Store start and end index for each Q&A pair

    # Pre-calculate ranges to handle copying correctly
    sorted_qna = sorted(qna_pairs_with_headlines, key=lambda x: x['q_para_index'])
    for i, item in enumerate(sorted_qna):
        q_index = item['q_para_index']
        # Find the start of the next Q&A pair, or the end of the document
        next_q_start_index = len(original_paragraphs)
        if i + 1 < len(sorted_qna):
            next_q_start_index = sorted_qna[i+1]['q_para_index']

        qna_ranges[q_index] = next_q_start_index
        for j in range(q_index, next_q_start_index):
            processed_para_indices.add(j)


    para_index = 0
    while para_index < len(original_paragraphs):
        if para_index in headlines_map:
            # Insert headline
            headline_text = headlines_map[para_index]
            headline_para = new_document.add_paragraph()
            headline_para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
            runner = headline_para.add_run(headline_text)
            runner.bold = True
            runner.font.size = Pt(14)

            # Get the end index for this Q&A pair
            end_index = qna_ranges[para_index]

            # Copy the original Q&A paragraphs for this range
            for i in range(para_index, end_index):
                 original_para = original_paragraphs[i]
                 new_para = new_document.add_paragraph(original_para.text)
                 # Attempt to copy basic formatting (alignment)
                 new_para.alignment = original_para.alignment
                 # Note: Copying detailed formatting requires more complex run iteration.

            # Skip the original paragraphs that were just copied
            para_index = end_index

        elif para_index not in processed_para_indices:
             # Copy paragraphs that are not part of any detected Q&A
             original_para = original_paragraphs[para_index]
             new_para = new_document.add_paragraph(original_para.text)
             new_para.alignment = original_para.alignment
             para_index += 1
        else:
            # This index was part of a processed Q&A but wasn't the start,
            # so just increment to skip it (already handled).
            para_index += 1

    return new_document


# --- Saving Document (No changes needed here) ---

def save_doc_to_bytes(document):
    """Saves the DOCX document object to a byte stream."""
    doc_io = io.BytesIO()
    document.save(doc_io)
    doc_io.seek(0) # Rewind the stream to the beginning
    return doc_io.getvalue()
