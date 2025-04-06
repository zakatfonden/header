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
    Parses a DOCX file to extract Q&A pairs based on specific markers.
    Assumes questions start with 'س:' or 'Q:' and answers start with 'ج:' or 'A:'.
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

    try:
        document = docx.Document(docx_file)
        all_paragraphs = document.paragraphs

        # Define regex patterns for flexibility (handles whitespace)
        # Case-insensitive matching for Q/A if needed using re.IGNORECASE
        # Using r'\s*' to match zero or more whitespace characters
        q_pattern = re.compile(r"^\s*(?:س|Q)\s*[:.)]", re.IGNORECASE) # Starts with س: or Q: or Q. or س. etc.
        a_pattern = re.compile(r"^\s*(?:ج|A)\s*[:.)]", re.IGNORECASE) # Starts with ج: or A: or A. or ج. etc.

        for i, para in enumerate(all_paragraphs):
            text = para.text.strip()

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
                    current_a = [] # Reset answer

                # Start the new question
                # Remove the marker (e.g., "س:") from the question text itself
                current_q = q_pattern.sub('', text).strip()
                q_start_index = i
                current_a = [] # Ensure answer list is reset even if previous one was empty

            elif is_answer_start and current_q:
                # Start or continue the answer only if we have a current question
                # Remove the marker (e.g., "ج:") from the answer text
                answer_text = a_pattern.sub('', text).strip()
                if answer_text: # Only add non-empty answer parts
                    current_a.append(answer_text)

            elif current_q and not is_question_start:
                 # If we are in a Q&A block (current_q is not None)
                 # and it's not a new question start, append to the current part
                 # (either continuation of Q or A)
                 # This simplistic approach assumes multi-paragraph answers follow directly
                 # If question could be multi-paragraph before answer starts, this needs refinement
                 if current_a: # If we've already started the answer, append to answer
                    if text: current_a.append(text)
                 else: # Otherwise, assume it's part of the question (needs careful review of format)
                    # Check if the line seems like a continuation or just unrelated text
                    # For now, appending to question if answer hasn't started
                     if text: current_q += "\n" + text


        # Add the last Q&A pair if it exists
        if current_q and current_a:
            qna_pairs.append({
                "question": current_q.strip(),
                "answer": "\n".join(current_a).strip(),
                "q_para_index": q_start_index
            })

        return qna_pairs, all_paragraphs

    except Exception as e:
        print(f"Error parsing DOCX: {e}")
        # Consider raising the error or returning a specific error indicator
        return [], [] # Return empty lists on error


# --- Headline Generation ---

def generate_headline(question, answer, model_name="gemini-1.5-flash"): # Or use a different model like gemini-pro
    """
    Generates a headline for a given Q&A pair using the Gemini API.

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
        # Basic check if response has text
        if response.text:
             # Clean up potential markdown or extra formatting from the model
            headline = response.text.strip().replace('*', '').replace('#', '')
            return headline
        else:
             # Handle cases where the response might be blocked or empty
            print(f"Warning: Received empty or blocked response for Q: {question[:50]}...")
            # Consider checking response.prompt_feedback for block reasons
            return f"خطأ في إنشاء عنوان للسؤال: {question[:30]}..." # Placeholder error headline

    except Exception as e:
        print(f"Error generating headline with Gemini: {e}")
        # Consider more specific error handling based on potential API errors
        return f"خطأ في إنشاء عنوان للسؤال: {question[:30]}..." # Placeholder error headline

# --- Document Creation ---

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
    # Set default paragraph direction to RTL for Arabic
    style = new_document.styles['Normal']
    font = style.font
    # Consider setting an Arabic font if default isn't suitable
    # font.name = 'Arial' # Example, choose appropriate Arabic font if needed
    paragraph_format = style.paragraph_format
    paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT # Right align paragraphs

    # Create a lookup for quick access to headlines by question index
    headlines_map = {item['q_para_index']: item['headline'] for item in qna_pairs_with_headlines}

    # Keep track of which paragraphs belong to processed Q&A pairs to avoid duplicating them
    processed_para_indices = set()
    for item in qna_pairs_with_headlines:
        q_index = item['q_para_index']
        # Find the end of the answer (approximate by finding the next Q or end of doc)
        next_q_index = len(original_paragraphs) # Default to end of doc
        for next_item in qna_pairs_with_headlines:
             if next_item['q_para_index'] > q_index:
                 next_q_index = min(next_q_index, next_item['q_para_index'])
                 break
        # Mark all paragraphs from the start of Q to just before the next Q as processed
        for i in range(q_index, next_q_index):
            processed_para_indices.add(i)


    # Iterate through original paragraphs and build the new document
    para_index = 0
    while para_index < len(original_paragraphs):
        if para_index in headlines_map:
            # Insert headline
            headline_text = headlines_map[para_index]
            headline_para = new_document.add_paragraph()
            # Set alignment specifically for headline if needed, otherwise uses default
            headline_para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
            runner = headline_para.add_run(headline_text)
            runner.bold = True
            runner.font.size = Pt(14) # Optional: make headline slightly larger

            # Find the end index for this Q&A pair (as calculated before)
            next_q_index = len(original_paragraphs)
            for item in qna_pairs_with_headlines:
                 # Find the item corresponding to the current headline
                 if item['q_para_index'] == para_index:
                     # Now find the start index of the *next* Q&A pair
                     temp_next_q = len(original_paragraphs)
                     for next_item in qna_pairs_with_headlines:
                         if next_item['q_para_index'] > para_index:
                             temp_next_q = min(temp_next_q, next_item['q_para_index'])
                             break
                     next_q_index = temp_next_q
                     break # Found the correct range


            # Copy the original Q&A paragraphs
            for i in range(para_index, next_q_index):
                 original_para = original_paragraphs[i]
                 new_para = new_document.add_paragraph(original_para.text)
                 # Attempt to copy basic formatting (alignment) - more complex formatting needs more code
                 new_para.alignment = original_para.alignment
                 # Note: Copying detailed formatting (bold, italics within paragraph, etc.)
                 # requires iterating through runs, which is more complex.

            # Skip the original paragraphs that were just copied
            para_index = next_q_index

        elif para_index not in processed_para_indices:
             # Copy paragraphs that are not part of any detected Q&A
             original_para = original_paragraphs[para_index]
             new_para = new_document.add_paragraph(original_para.text)
             new_para.alignment = original_para.alignment # Copy basic alignment
             para_index += 1
        else:
            # This index was part of a processed Q&A but wasn't the start,
            # so just increment to skip it (already handled).
            para_index += 1


    return new_document


# --- Saving Document ---

def save_doc_to_bytes(document):
    """Saves the DOCX document object to a byte stream."""
    doc_io = io.BytesIO()
    document.save(doc_io)
    doc_io.seek(0) # Rewind the stream to the beginning
    return doc_io.getvalue()
