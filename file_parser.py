import io
import PyPDF2
from docx import Document


def extract_text(content, filename):
    """
    ფაილიდან ტექსტის ამოღება
    """
    fname = filename.lower()
    try:
        if fname.endswith('.pdf'):
            text = _pdf(content)
        elif fname.endswith('.docx'):
            text = _docx(content)
        else:
            text = content.decode('utf-8', errors='ignore')
        
        return text.strip() if text else None
        
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


def is_english_cv(text):
    """
    შემოწმება არის თუ არა CV ინგლისურად დაწერილი.
    
    აბრუნებს: (is_english: bool, detected_language: str)
    """
    if not text or len(text) < 50:
        return True, "unknown"  # ძალიან მოკლე ტექსტი - გავატაროთ
    
    # სხვადასხვა ენის სიმბოლოები
    
    # ქართული
    georgian = sum(1 for c in text if '\u10A0' <= c <= '\u10FF' or '\u2D00' <= c <= '\u2D2F')
    
    # კირილიცა (რუსული, უკრაინული, ბულგარული და ა.შ.)
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    
    # არაბული
    arabic = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    
    # ჩინური
    chinese = sum(1 for c in text if '\u4E00' <= c <= '\u9FFF')
    
    # იაპონური (ჰირაგანა + კატაკანა)
    japanese = sum(1 for c in text if '\u3040' <= c <= '\u30FF')
    
    # კორეული
    korean = sum(1 for c in text if '\uAC00' <= c <= '\uD7AF')
    
    # ებრაული
    hebrew = sum(1 for c in text if '\u0590' <= c <= '\u05FF')
    
    # თაილანდური
    thai = sum(1 for c in text if '\u0E00' <= c <= '\u0E7F')
    
    # ბერძნული
    greek = sum(1 for c in text if '\u0370' <= c <= '\u03FF')
    
    # ლათინური (ინგლისური და დასავლეთ ევროპული)
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    
    # სულ ასოები
    total_alpha = georgian + cyrillic + arabic + chinese + japanese + korean + hebrew + thai + greek + latin
    
    if total_alpha == 0:
        return True, "unknown"  # ტექსტი არ შეიცავს ასოებს
    
    # პროცენტები
    non_latin = georgian + cyrillic + arabic + chinese + japanese + korean + hebrew + thai + greek
    non_latin_ratio = non_latin / total_alpha
    latin_ratio = latin / total_alpha
    
    print(f"[Parser] Language check: Latin={latin_ratio:.1%}, Non-Latin={non_latin_ratio:.1%}")
    
    # თუ >20% არა-ლათინური სიმბოლოებია - არ არის ინგლისური
    if non_latin_ratio > 0.2:
        # დავადგინოთ რომელი ენაა
        if georgian > 0:
            detected = "Georgian"
        elif cyrillic > 0:
            detected = "Russian/Cyrillic"
        elif arabic > 0:
            detected = "Arabic"
        elif chinese > 0:
            detected = "Chinese"
        elif japanese > 0:
            detected = "Japanese"
        elif korean > 0:
            detected = "Korean"
        elif hebrew > 0:
            detected = "Hebrew"
        elif thai > 0:
            detected = "Thai"
        elif greek > 0:
            detected = "Greek"
        else:
            detected = "Non-English"
        
        print(f"[Parser] ❌ Detected language: {detected}")
        return False, detected
    
    # >70% ლათინური = ინგლისური (ან ევროპული, რაც მისაღებია)
    if latin_ratio > 0.7:
        print(f"[Parser] ✅ CV is in English/Latin script")
        return True, "English"
    
    print(f"[Parser] ⚠️ Uncertain language, allowing...")
    return True, "uncertain"
