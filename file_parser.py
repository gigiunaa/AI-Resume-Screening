import io
import PyPDF2
from docx import Document


def extract_text(content, filename):
    fname = filename.lower()
    try:
        if fname.endswith('.pdf'):
            return _pdf(content)
        elif fname.endswith('.docx'):
            return _docx(content)
        else:
            return content.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[Parser] Error {filename}: {e}")
        return None


def _pdf(content):
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    text = ""
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
    return text.strip()


def _docx(content):
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
