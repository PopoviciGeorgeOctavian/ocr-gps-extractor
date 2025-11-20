# server.py - OCR cu EasyOCR - Sistem Dual OCR Îmbunătățit cu Procesare Paralelă
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import csv
import io
from datetime import datetime
import shutil
import re
import easyocr
import cv2
import numpy as np
import unicodedata
from PIL import Image, ImageEnhance
import platform
import subprocess
import gc
from queue import Queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
app.config['PROCESSED_FOLDER'] = 'processed'
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 * 1024  # 8GB - foarte generos
MAX_WORKERS = 3  # Dublu față de configurația inițială
BATCH_SIZE = 100
# Creează folderul processed dacă nu există
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)
# Fraze/regex de watermark care trebuie ignorate din OCR
WATERMARK_PATTERNS = [
    r'\bgps\s*map\s*camera\b',
    r'\bgps\s*camera\b',
    r'\bgps\s*map\b',
    r'\bgoogle\b',
    r'\bgo[ao]gle\b',
    r'\bgo\s*gle\b',
    r'\bkitfit\b',
]

# Dicționar complet al localităților din județul Bihor (păstrat același)
BIHOR_LOCALITIES = {
    # Municipii și orașe
    'oradea': 'Oradea',
    'beiuș': 'Beiuș', 'beius': 'Beiuș',
    'marghita': 'Marghita',
    'salonta': 'Salonta',
    'aleșd': 'Aleșd', 'alesd': 'Aleșd',
    'nucet': 'Nucet',
    'săcueni': 'Săcueni', 'sacueni': 'Săcueni',
    'valea lui mihai': 'Valea lui Mihai',
    'vașcău': 'Vașcău', 'vascau': 'Vașcău',
    'ștei': 'Ștei', 'stei': 'Ștei',

    # Comune și sate
    'olcea': 'Olcea',
    'sânmartin': 'Sânmartin', 'sinmartin': 'Sânmartin', 'sînmartin': 'Sânmartin',
    'abram': 'Abram',
    'abramut': 'Abrămuț',
    'aușeu': 'Aușeu', 'auseu': 'Aușeu',
    'avram iancu': 'Avram Iancu',
    'aștileu': 'Aștileu', 'astileu': 'Aștileu',
    'balc': 'Balc',
    'batăr': 'Batăr', 'batar': 'Batăr',
    'biharia': 'Biharia',
    'boianu mare': 'Boianu Mare',
    'borod': 'Borod',
    'borș': 'Borș', 'bors': 'Borș',
    'bratca': 'Bratca',
    'brusturi': 'Brusturi',
    'budureasa': 'Budureasa',
    'buduslau': 'Buduslău',
    'bulz': 'Bulz',
    'buntești': 'Buntești', 'buntesti': 'Buntești',
    'cefa': 'Cefa',
    'ceica': 'Ceica',
    'cetariu': 'Cetariu',
    'cherechiu': 'Cherechiu',
    'chișlaz': 'Chișlaz', 'chislaz': 'Chișlaz',
    'ciumeghiu': 'Ciumeghiu',
    'cociuba mare': 'Cociuba Mare',
    'copăcel': 'Copăcel', 'copacel': 'Copăcel',
    'criștioru de jos': 'Criștioru de Jos',
    'curtuișeni': 'Curtuișeni', 'curtuiseni': 'Curtuișeni',
    'curățele': 'Curățele', 'curatele': 'Curățele',
    'câmpani': 'Câmpani', 'campani': 'Câmpani',
    'căbești': 'Căbești', 'cabesti': 'Căbești',
    'căpâlna': 'Căpâlna', 'capalna': 'Căpâlna',
    'cărpinet': 'Cărpinet', 'carpinet': 'Cărpinet',
    'derna': 'Derna',
    'diosig': 'Diosig',
    'dobrești': 'Dobrești', 'dobresti': 'Dobrești',
    'drăgești': 'Drăgești', 'dragesti': 'Drăgești',
    'drăgănești': 'Drăgănești', 'draganesti': 'Drăgănești',
    'finiș': 'Finiș', 'finis': 'Finiș',
    'gepiu': 'Gepiu',
    'girisu de cris': 'Girișu de Criș',
    'girișu de criș': 'Girișu de Criș',
    'girisu de criș': 'Girișu de Criș',
    'girișu de cris': 'Girișu de Criș',
    'hidișelu de sus': 'Hidișelu de Sus',
    'holod': 'Holod',
    'husasău de tinca': 'Husasău de Tinca',
    'ineu': 'Ineu',
    'lazuri de beiuș': 'Lazuri de Beiuș',
    'lugașu de jos': 'Lugașu de Jos',
    'lunca': 'Lunca',
    'lăzăreni': 'Lăzăreni', 'lazareni': 'Lăzăreni',
    'mădăras': 'Mădăras', 'madaras': 'Mădăras',
    'măgești': 'Măgești', 'magesti': 'Măgești',
    'nojorid': 'Nojorid',
    'oșorhei': 'Oșorhei', 'osorhei': 'Oșorhei',
    'paleu': 'Paleu',
    'petreu': 'Petreu',
    'pietroasa': 'Pietroasa',
    'pocola': 'Pocola',
    'pomezeu': 'Pomezeu',
    'popești': 'Popești', 'popesti': 'Popești',
    'remetea': 'Remetea',
    'rieni': 'Rieni',
    'roșia': 'Roșia', 'rosia': 'Roșia',
    'roșiori': 'Roșiori', 'rosiori': 'Roșiori',
    'răbăgani': 'Răbăgani', 'rabagani': 'Răbăgani',
    'spinuș': 'Spinuș', 'spinus': 'Spinuș',
    'suplacu de barcău': 'Suplacu de Barcău',
    'sâmbăta': 'Sâmbăta', 'sambata': 'Sâmbăta',
    'sâniob': 'Sâniob', 'saniob': 'Sâniob',
    'sânmartin': 'Sânmartin', 'sannicolau roman': 'Sânnicolau Român',
    'sântandrei': 'Sântandrei', 'santandrei': 'Sântandrei',
    'sârbi': 'Sârbi', 'sarbi': 'Sârbi',
    'săcădat': 'Săcădat', 'sacadat': 'Săcădat',
    'sălacea': 'Sălacea', 'salacea': 'Sălacea',
    'sălard': 'Sălard', 'salard': 'Sălard',
    'tarcea': 'Tarcea',
    'tileagd': 'Tileagd',
    'tinca': 'Tinca',
    'toboliu': 'Toboliu',
    'tulca': 'Tulca',
    'tămășeu': 'Tămășeu', 'tamaseu': 'Tămășeu',
    'tărcaia': 'Tărcaia', 'tarcaia': 'Tărcaia',
    'tăuteu': 'Tăuteu', 'tauteu': 'Tăuteu',
    'uileacu de beiuș': 'Uileacu de Beiuș',
    'vadu crișului': 'Vadu Crișului',
    'viișoara': 'Viișoara', 'viisoara': 'Viișoara',
    'vârciorog': 'Vârciorog', 'varciorog': 'Vârciorog',
    'șimian': 'Șimian', 'simian': 'Șimian',
    'șinteu': 'Șinteu', 'sinteu': 'Șinteu',
    'șoimi': 'Șoimi', 'soimi': 'Șoimi',
    'șuncuiuș': 'Șuncuiuș', 'suncuius': 'Șuncuiuș',
    'țețchea': 'Țețchea', 'tetchea': 'Țețchea',

    # Sate importante
    'băile felix': 'Băile Felix',
    'betfia': 'Betfia',
    'cihei': 'Cihei',
    'cordău': 'Cordău',
    'haieu': 'Haieu',
    'rontău': 'Rontău',
    'palota': 'Palota',
    'bicaci': 'Bicaci',
    'tărian': 'Tărian',
    'albiș': 'Albiș',
    'sântimreu': 'Sântimreu',
    'adoni': 'Adoni',
    'galoșpetreu': 'Galoșpetreu',
    'bălaia': 'Bălaia',
    'călătani': 'Călătani',
    'poșoloaca': 'Poșoloaca',
    'tilecuș': 'Tilecuș',
    'uileacu de criș': 'Uileacu de Criș',
    'belfir': 'Belfir',
    'girișu negru': 'Girișu Negru',
    'gurbediu': 'Gurbediu',
    'râpa': 'Râpa',
    'cheresig': 'Cheresig',
    'căuașd': 'Căuașd',
    'niuved': 'Niuved',
    'parhida': 'Parhida',
    'satu nou': 'Satu Nou',
    'mierag': 'Mierag',
    'totoreni': 'Totoreni',
    'tărcăița': 'Tărcăița',
    'bogei': 'Bogei',
    'chiribiș': 'Chiribiș',
    'ciutelec': 'Ciutelec',
    'poiana': 'Poiana',
    'forău': 'Forău',
    'prisaca': 'Prisaca',
    'vălanii de beiuș': 'Vălanii de Beiuș',
    'birtin': 'Birtin',
    'tomnatic': 'Tomnatic',
    'topa de criș': 'Topa de Criș',
    'izvoarele': 'Izvoarele',
    'pădureni': 'Pădureni',
    'reghea': 'Reghea',
    'fâșca': 'Fâșca',
    'surducel': 'Surducel',
    'șerghiș': 'Șerghiș',
    'voivozi': 'Voivozi',
    'șilindru': 'Șilindru',
    'huta voivozi': 'Huta Voivozi',
    'socet': 'Socet',
    'valea târnei': 'Valea Târnei',
    'borz': 'Borz',
    'codru': 'Codru',
    'dumbrăvița de codru': 'Dumbrăvița de Codru',
    'poclușa de beiuș': 'Poclușa de Beiuș',
    'sânnicolau de beiuș': 'Sânnicolau de Beiuș',
    'ursad': 'Ursad',
    'urviș de beiuș': 'Urviș de Beiuș',
    'bălnaca': 'Bălnaca',
    'bălnaca-groși': 'Bălnaca-Groși',
    'zece hotare': 'Zece Hotare',
    'hotar': 'Hotar',
    'subpiatră': 'Subpiatră',
    'telechiu': 'Telechiu'
}


def remove_watermarks(text: str) -> str:
    t = text
    for pat in WATERMARK_PATTERNS:
        t = re.sub(pat, ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def normalize_quotes(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    table = str.maketrans({
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "˝": '"',
        "´": "'", "`": "'",
    })
    return s.translate(table)

model_dir = os.path.join(os.path.dirname(__file__), 'easyocr_models')
print("🔄 Inițializare EasyOCR...")
reader = easyocr.Reader(
    ['ro'],
    gpu=False,
    download_enabled=False,
    model_storage_directory=model_dir,
    detector=True,
    recognizer=True,
    verbose=False
)
print("✅ EasyOCR gata!\n")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ... (păstrează toate funcțiile de preprocesare OCR existente)
def preprocess_image_method1(image_path):
    """Preprocesare 1: SUPER AGRESIVĂ - Contrast maxim + eliminare umbre totale."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"❌ Eroare citire imagine")
            return cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

        # Convert to LAB color space - mai bun pentru luminozitate
        img = resize_for_ocr(img)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # CONTRAST MAXIM - SUPER AGRESIV
        clahe = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(4, 4))
        l_contrast = clahe.apply(l)

        # ELIMINARE UMBRE TOTALĂ - gamma extrem de jos
        gamma = 0.3
        l_no_shadows = np.power(l_contrast / 255.0, gamma) * 255.0
        l_no_shadows = np.uint8(np.clip(l_no_shadows, 0, 255))

        # STRETCHING HISTOGRAM
        l_stretched = cv2.normalize(l_no_shadows, None, 0, 255, cv2.NORM_MINMAX)

        # Recombină canalele
        lab_enhanced = cv2.merge([l_stretched, a, b])
        img_enhanced = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

        # Convert to grayscale
        gray = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2GRAY)

        # SHARPENING EXTREM
        kernel = np.array([[-2, -2, -2],
                           [-2, 32, -2],
                           [-2, -2, -2]]) / 16.0
        enhanced = cv2.filter2D(gray, -1, kernel)

        # CONTRAST FINAL
        enhanced = cv2.equalizeHist(enhanced)

        print("   → 🔥 CONTRAST MAXIM | 🚫 UMBRE ELIMINATE | 📈 SHARPENING EXTREM")
        return enhanced

    except Exception as e:
        print(f"⚠️ Eroare preprocesare method1: {e}")
        return cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)


def preprocess_pil_aggressive(image_path):
    """PIL SUPER AGRESIV - Contrast nuclear + zero umbre."""
    try:
        print(f"📸 PIL PREPROCESARE NUCLEARĂ: {os.path.basename(image_path)}")

        img = Image.open(image_path)

        # 1) CONTRAST - NUCLEAR (+300%)
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(4.0)
        print("   → Contrast +300% (NUCLEAR)")

        # 2) BRIGHTNESS - maxim pentru umbre
        brightness = ImageEnhance.Brightness(img)
        img = brightness.enhance(1.8)
        print("   → Brightness +80%")

        # 3) SHARPNESS - EXTREM
        sharpness = ImageEnhance.Sharpness(img)
        img = sharpness.enhance(5.0)
        print("   → Sharpness +400%")

        # Convert to numpy pentru procesare extremă
        img_array = np.array(img)
        img_array = resize_for_ocr(img_array)
        # 4) ELIMINARE UMBRE TOTALĂ - gamma hyper
        gamma = 0.2
        img_array = np.power(img_array / 255.0, gamma) * 255.0
        img_array = np.uint8(np.clip(img_array, 0, 255))

        # 5) CONTRAST FINAL - stretching manual
        p2, p98 = np.percentile(img_array, (2, 98))
        img_array = np.uint8(np.clip((img_array - p2) * 255.0 / (p98 - p2), 0, 255))

        # Convert back to PIL
        img = Image.fromarray(img_array)
        print("   → 🚫 UMBRE ELIMINATE (gamma 0.2)")

        # 6) CURĂȚARE FINALĂ - grayscale
        img = img.convert('L')

        # 7) CONTRAST ULTIMAT în grayscale
        img_array = np.array(img)
        img_array = cv2.equalizeHist(img_array)

        print("   → ✅ PREPROCESARE NUCLEARĂ COMPLETĂ")
        return img_array

    except Exception as e:
        print(f"❌ Eroare preprocesare PIL nucleară: {e}")
        return cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)


def repair_concatenated_text(text):
    """Repară textul unde OCR-ul a lipit cuvintele și numerele."""
    # 1. Adaugă spații între litere și numere, DAR protejează formatele de tip "14B" sau "77A"
    # Logică: Adaugă spațiu doar dacă urmează mai mult de o literă (ex: "Etaj1" -> "Etaj 1", dar "14B" rămâne "14B")

    # Cazul: Text urmat de Cifră (ex: "Strada10") -> "Strada 10" (OK)
    text = re.sub(r'([a-zA-ZăâîșțĂÂÎȘȚ])(\d)', r'\1 \2', text)

    # Cazul: Cifră urmată de Text LUNG (ex: "2025Noiembrie") -> "2025 Noiembrie"
    text = re.sub(r'(\d)([a-zA-ZăâîșțĂÂÎȘȚ]{2,})', r'\1 \2', text)

    # Adaugă spații între coordonate și data: "21.971867004/11/2025" -> "21.9718670 04/11/2025"
    text = re.sub(r'(\d{2}\.\d+)(\d{2}/\d{2}/\d{4})', r'\1 \2', text)

    # Adaugă spații între data și ora: "04/11/202511:29" -> "04/11/2025 11:29"
    text = re.sub(r'(\d{2}/\d{2}/\d{4})(\d{1,2}[:.]\d{2})', r'\1 \2', text)

    # Adaugă spații între ora și unități: "11.290 m" -> "11.29 0 m"
    text = re.sub(r'(\d{1,2}[:.]\d{2})(\d)\s*([a-zA-Z])', r'\1 \2 \3', text)

    return text


def clean_and_combine_lines(lines):
    """Recombină liniile fragmentate și le curăță + scoate watermark/zgomot."""
    combined_text = ' '.join(lines)
    combined_text = normalize_quotes(combined_text)

    # REPARĂ textul concatenat înainte de orice altă procesare
    combined_text = repair_concatenated_text(combined_text)

    # Elimină pattern-uri zgomotoase specifice
    noise_patterns = [
        r'\bOgory\s*~\s*Str',
        r'\bTut\s+Sala\s+de\b',
        r'\bOvKD\b',
        r'\bGegMap\s+camara\b',
        r'\bogle\b',
        r'\bMap\b',
        r'\bcamara\b',
    ]

    for pattern in noise_patterns:
        combined_text = re.sub(pattern, '', combined_text, flags=re.IGNORECASE)

    # Scoate watermark-uri
    combined_text = remove_watermarks(combined_text)

    # Corectează erori comune OCR
    corrections = [
        (r'Judetul', 'Județul'),
        (r'Bibor', 'Bihor'),
        (r'(\d)\.\s*(\d)', r'\1.\2'),
    ]

    for wrong, correct in corrections:
        combined_text = re.sub(wrong, correct, combined_text, flags=re.IGNORECASE)

    # Curățări finale
    combined_text = re.sub(r'\s+', ' ', combined_text).strip()

    return combined_text


def combine_street_and_number(strada, numar):
    """Combină strada și numărul într-un singur câmp"""
    if strada and numar:
        return f"{strada} {numar}"
    elif strada:
        return strada
    elif numar:
        return numar
    else:
        return ""


def extract_address_info_improved(full_text, data):
    """ÎMBUNĂTĂȚIT v3: Suport pentru Bulevarde, Alei, Piețe și erori OCR."""
    try:
        text = clean_and_combine_lines(full_text.split(' '))
        text = normalize_coordinates_text(text)

        # Adresa = tot înainte de coordonate
        gps_match = re.search(r'\d{2}\.\d+\s*[,;]?\s*\d{2}\.\d+', text)
        address_text = text[:gps_match.start()].strip() if gps_match else text

        data['adresa_completa'] = address_text
        data['judet'] = 'Bihor'
        data['tara'] = 'România'

        # 1. LOCALITATE (Rămâne la fel, e ok)
        text_lower = text.lower()
        for locality_key, locality_value in BIHOR_LOCALITIES.items():
            if locality_key in text_lower:
                data['localitate'] = locality_value
                break

        # 2. STRADĂ ȘI NUMĂR (Aici e marea schimbare)
        # Definim toate tipurile posibile de artere + variante OCR greșite
        street_types = r'(?:Str\.|Strada|B-dul|Bulevardul|Bd\.|Aleea|Calea|P-ta|Piata|Piața|Intrarea|Fundatura|Sos\.|Soseaua)'

        # Pattern 1: Prefix (Str/Bdul) + Nume + Număr
        # Ex: "B-dul Dacia 10", "Aleea Rozelor 4"
        p1 = re.search(rf'{street_types}\s+([A-Za-zăâîșțĂÂÎȘȚ\s\-\.]+?)\s+(\d+\s*[A-Z]?)', address_text, re.IGNORECASE)

        # Pattern 2: Doar Prefix + Nume (fără număr)
        p2 = re.search(rf'{street_types}\s+([A-Za-zăâîșțĂÂÎȘȚ\s\-\.]+)', address_text, re.IGNORECASE)

        # Pattern 3: Nume + Număr (fără prefix - Risky dar necesar)
        # Căutăm un cuvânt mare urmat de un număr la final de text sau înainte de virgulă
        p3 = re.search(r'\b([A-Z][a-zărîșț]+\s+[A-Z][a-zărîșț]+)\s+(\d+)', address_text)

        if p1:
            data['strada'] = p1.group(1).strip()
            data['numar'] = p1.group(2).strip()
            print(f"✅ Stradă (Tip 1): {data['strada']} #{data['numar']}")
        elif p2:
            data['strada'] = p2.group(1).strip()
            data['numar'] = ""
            print(f"✅ Stradă (Tip 2 - Fără nr): {data['strada']}")
        elif p3 and not data.get('strada'):
            # Fallback doar dacă pare nume propriu
            data['strada'] = p3.group(1).strip()
            data['numar'] = p3.group(2).strip()
            print(f"✅ Stradă (Tip 3 - Implicită): {data['strada']}")

        # Curățăm strada de prefixe duplicate dacă au fost prinse în grup
        if data['strada']:
            clean_str = re.sub(rf'^{street_types}\s+', '', data['strada'], flags=re.IGNORECASE)
            data['strada'] = clean_str.strip()

        # 3. COD POȘTAL
        cod_postal_match = re.search(r'\b\d{6}\b', text)
        if cod_postal_match:
            data['cod_postal'] = cod_postal_match.group(0)

        data['strada_si_numar'] = combine_street_and_number(data.get('strada', ''), data.get('numar', ''))

    except Exception as e:
        print(f"⚠️ Eroare adresă: {e}")
        data['strada_si_numar'] = combine_street_and_number(data.get('strada', ''), data.get('numar', ''))

    return data


def normalize_coordinates_text(text: str) -> str:
    """PREPROCES: Normalizează formatul coordonatelor înainte de regex."""
    # PROBLEMA #1: Spații în coordonate - "Lat 471 222" → "Lat 47.1222"
    text = re.sub(r'Lat\s+(\d{2})\s+(\d+)', r'Lat \1.\2', text)

    # PROBLEMA #1: "Long 21,9557930" → "Long 21.955793"
    text = re.sub(r'(Long|Longitude)\s+(\d+),(\d+)', r'\1 \2.\3', text)

    # PROBLEMA #6: Cod poștal cu spații - "410 155" → "410155"
    text = re.sub(r'(\d{3})\s+(\d{3})\b', r'\1\2', text)

    return text


def extract_accuracy(text, data):
    """Extrage precizia GPS chiar dacă simbolul ± este citit greșit."""
    try:
        text = normalize_all_text(text)

        # Pattern 1: Cuvântul "accuracy" sau "acc" prezent
        # Prinde: "4m accuracy", "3.5 m acc", "accuracy: 10m"
        m1 = re.search(r'(\d+(?:\.\d+)?)\s*m\s*(?:accuracy|acc)', text, re.IGNORECASE)
        if m1:
            data['accuracy'] = f"± {m1.group(1)} m"
            return data

        # Pattern 2: Simboluri dubioase urmate de 'm' la început/final de rând sau în paranteze
        # OCR vede ± ca: +, t, f, z, 4, *, ?
        m2 = re.search(r'[±\+tTfFzZ\?]\s*(\d+(?:\.\d+)?)\s*m\b', text)
        if m2:
            val = float(m2.group(1))
            # Filtru de bun simț: precizia e de obicei mică (sub 100m)
            if val < 500:
                data['accuracy'] = f"± {val} m"
                return data

    except Exception as e:
        print(f"⚠️ Eroare acuratețe: {e}")
    return data


def resize_for_ocr(image, max_width=1600):
    """Redimensionează imaginea pentru viteză maximă OCR, păstrând aspect ratio."""
    h, w = image.shape[:2]
    if w > max_width:
        ratio = max_width / w
        new_h = int(h * ratio)
        image = cv2.resize(image, (max_width, new_h), interpolation=cv2.INTER_AREA)
    return image


def normalize_all_text(text: str) -> str:
    """Normalizează inteligent: puncte pentru GPS, dar păstrează virgula în rest."""

    # 1. Numere GPS (Lat/Long) scrise cu virgulă (ex: 47,123456)
    # Le schimbăm în punct DOAR dacă au cel puțin 3 zecimale (ca să nu stricăm "ap. 2, scara 3")
    text = re.sub(r'(\d{1,3}),(\d{3,})', r'\1.\2', text)

    # 2. Spații în numere GPS (ex: 21 7599 → 21.7599) - Asta e ok
    text = re.sub(r'Lat\s+(\d{2})\s+(\d+)', r'Lat \1.\2', text)
    text = re.sub(r'Long\s+(\d+)\s+(\d+)', r'Long \1.\2', text)

    # 3. Numere lipite de text "Lat47..."
    text = re.sub(r'Lat(\d)', r'Lat \1', text, flags=re.IGNORECASE)
    text = re.sub(r'Long(\d)', r'Long \1', text, flags=re.IGNORECASE)

    return text


def extract_datetime_universal(text, data):
    """
    v9 FINALĂ: Reparare Fallback Numeric.
    Păstrează separatorii (/, ., -) la curățare pentru a detecta '13/11/2025'.
    """
    try:
        # 1. Curățare LOCALĂ INTELIGENTĂ
        # Păstrăm litere, cifre, DAR ȘI separatorii importanți: . , / - :
        # Asta permite ca '13/11/2025' să rămână '13/11/2025' nu '13 11 2025'
        clean_text = re.sub(r'[^a-zA-Z0-9\s\.\,\/\-:]', ' ', text)

        # Normalizăm spațiile multiple
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        # Text curat pentru oră (fără coordonate GPS lungi)
        text_for_time = re.sub(r'\d{2}[\.,]\d{4,}', ' ', clean_text)

        print(f"🔍 Caut data/ora în: '{clean_text[:100]}...'")

        current_year = datetime.now().year
        valid_years = list(range(current_year - 2, current_year + 3))

        months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
            'ian': '01', 'mai': '05', 'iun': '06', 'iul': '07', 'noi': '11',
            'sept': '09', 'octom': '10', 'noiem': '11', 'decem': '12'
        }

        found_date = None

        # ========== PARTEA 1: DATA CU NUME DE LUNĂ (Nov 12 / 12 Nov) ==========

        month_matches = list(re.finditer(r'(?i)\b([a-zA-Z]{3,})\b', clean_text))

        for m in month_matches:
            word = m.group(1).lower()
            month_key = word[:3]

            if month_key in months:
                mon_num = months[month_key]

                # Împărțim textul în stânga și dreapta lunii
                left_side = clean_text[:m.start()]
                right_side = clean_text[m.end():]

                day = None
                year = None

                # CAZUL 1: "Nov 12, 2025" (Ziua în DREAPTA)
                # Căutăm un număr imediat în dreapta (ignorant virgule/puncte)
                day_right_match = re.search(r'^[\s,\.]*(\d{1,2})\b', right_side)
                if day_right_match:
                    d_cand = int(day_right_match.group(1))
                    if 1 <= d_cand <= 31:
                        day = d_cand
                        # Anul e mai departe în dreapta
                        year_match = re.search(r'\b(20\d{2})\b', right_side)
                        if year_match:
                            year = int(year_match.group(1))

                # CAZUL 2: "12 Nov 2025" (Ziua în STÂNGA)
                if not day:
                    # Căutăm un număr imediat în stânga
                    day_left_match = re.search(r'\b(\d{1,2})[\s,\.\-]*$', left_side)
                    if day_left_match:
                        d_cand = int(day_left_match.group(1))
                        if 1 <= d_cand <= 31:
                            day = d_cand
                            # Anul e tot în dreapta lunii de obicei
                            year_match = re.search(r'\b(20\d{2})\b', right_side)
                            if year_match:
                                year = int(year_match.group(1))

                if day and year and year in valid_years:
                    found_date = f"{day}.{mon_num}.{year}"
                    break

        # ========== PARTEA 2: DATA NUMERICĂ (13/11/2025) - FALLBACK ==========
        if not found_date:
            # Acum regex-ul va funcționa pentru că am păstrat / . - în clean_text
            # Suportă: 13/11/2025, 13.11.2025, 13-11-2025
            match_num = re.search(r'\b(\d{1,2})[\s\.\/\-]+(\d{1,2})[\s\.\/\-]+(20\d{2})\b', clean_text)

            if match_num:
                d, m, y = map(int, match_num.groups())
                # Validare matematică
                if 1 <= d <= 31 and 1 <= m <= 12 and y in valid_years:
                    found_date = f"{d}.{m}.{y}"

        if found_date:
            data['data'] = found_date
            print(f"✅ Data găsită: {found_date}")
        else:
            print("⚠️ Data nu s-a găsit.")

        # ========== PARTEA 3: ORA (Ignoră coordonate) ==========
        found_time = None

        # Căutăm perechi HH:MM sau HH.MM, ignorând coordonatele
        time_matches = re.finditer(r'\b(\d{1,2})[:\.\,](\d{2})(?::\d{2})?\b', text_for_time)

        for tm in time_matches:
            h_val = int(tm.group(1))
            m_val = int(tm.group(2))

            if 0 <= h_val <= 23 and 0 <= m_val <= 59:
                # FILTRE ANTI-GPS (România)
                # Latitudine (~44-48)
                if 44 <= h_val <= 48: continue

                # Longitudine (~20-29) cu punct (21.95 e GPS, 21:45 e ceas)
                if 20 <= h_val <= 29 and '.' in tm.group(0): continue

                # Filtru pentru coordonate GPS cu virgulă
                if 20 <= h_val <= 29 and ',' in tm.group(0): continue

                found_time = f"{h_val:02d}:{m_val:02d}"
                break

        if found_time:
            data['ora'] = found_time
            print(f"✅ Ora găsită: {found_time}")
        else:
            print("⚠️ Ora nu s-a găsit.")

    except Exception as e:
        print(f"⚠️ Eroare critică data/ora: {e}")

    return data

import re


def extract_coordinates_universal(text, data):
    """
    v3 UNIVERSAL: Extrage orice pereche de numere care se încadrează
    geografic în România, ignorând formatarea (ghilimele, text, etc).
    """
    try:
        # 1. Curățare minimală (eliminăm caractere invizibile ciudate)
        text = text.replace('\n', ' ').replace('\r', ' ').strip()

        print(f"🔍 Scanare text pentru coordonate...")

        # 2. REGEX UNIVERSAL
        # Explicatie:
        # (\d{2}[\.,]\d{2,})  -> Primul număr: 2 cifre (ex: 47), punct/virgula, minim 2 zecimale
        # [^0-9\-]{1,20}      -> Separator: orice (spațiu, text, virgulă) lungime 1-20, dar nu cifre
        # (\d{2}[\.,]\d{2,})  -> Al doilea număr
        pattern = r'(\d{2}[\.,]\d{2,})[^0-9\-]{1,20}(\d{2}[\.,]\d{2,})'

        # Găsim TOATE posibilele perechi din text
        matches = list(re.finditer(pattern, text))

        for m in matches:
            try:
                raw_lat = m.group(1).replace(',', '.')  # Normalizăm virgula în punct
                raw_lon = m.group(2).replace(',', '.')

                lat = float(raw_lat)
                lon = float(raw_lon)

                # 3. LOGICA DE INVERSARE (Auto-detectare Lat vs Long)
                # Uneori coordonatele sunt scrise invers (Longitudine, Latitudine)
                # În România: Lat este ~44-48, Long este ~20-29.

                final_lat, final_lon = None, None

                # Cazul 1: Ordine normală (Lat, Long)
                if (43.0 <= lat <= 49.0) and (20.0 <= lon <= 30.0):
                    final_lat, final_lon = lat, lon

                # Cazul 2: Ordine inversată (Long, Lat) sau format (X, Y)
                elif (43.0 <= lon <= 49.0) and (20.0 <= lat <= 30.0):
                    print("🔄 Am detectat coordonate inversate, le corectez...")
                    final_lat, final_lon = lon, lat

                # Dacă am găsit o pereche validă geografic
                if final_lat and final_lon:
                    final_lat = round(final_lat, 6)
                    final_lon = round(final_lon, 6)

                    data['latitudine'] = str(final_lat)
                    data['longitudine'] = str(final_lon)

                    print(f"✅ GĂSIT ȘI VALIDAT: {final_lat}, {final_lon}")
                    return data  # Ne oprim la prima pereche validă găsită

            except ValueError:
                continue

        print("❌ Nu s-au găsit coordonate care să fie în România.")
        data['latitudine'] = "Fără coordonate poza"
        data['longitudine'] = "Fără coordonate poza"

    except Exception as e:
        print(f"⚠️ Eroare critică la extragere: {e}")
        data['latitudine'] = "Fără coordonate poza"
        data['longitudine'] = "Fără coordonate poza"

    return data


def extract_altitude_improved_v2(text, data):
    """ÎMBUNĂTĂȚIT v2: Cauta altitudine de la FINAL înapoi, nu de la început."""
    try:
        text = normalize_all_text(text)

        patterns = [
            r'(\d+(?:\.\d+)?)\s*m\s+(?:Legal|Lec|Lega|Tag)',
            r'(\d+(?:\.\d+)?)\s*m\s+(?:above|elevation)',
            r'(\d+(?:\.\d+)?)\s*m\b',
        ]

        for pattern in patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                m = matches[-1]

                try:
                    altitude_val = float(m.group(1))
                    if 0 <= altitude_val <= 2000:
                        data['altitudine'] = f"{m.group(1)} m"
                        print(f"✅ Altitudine: {m.group(1)} m")
                        return data
                except ValueError:
                    continue

    except Exception as e:
        print(f"⚠️ Eroare altitudine: {e}")

    return data


def calculate_text_quality_score_improved(text):
    """IMPROVED: Scor de calitate cu bonus pentru format corect și penalități."""
    if not text:
        return 0

    score = 0

    if re.search(r'\bLat\b.*\bLong\b', text, re.IGNORECASE):
        score += 40
    elif re.search(r'Laț|laț', text):
        score -= 10

    if re.search(r'\d{2}\.\d{4,}', text):
        score += 30

    if re.search(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}', text):
        score += 20

    if re.search(r'(?:str\.|strada)\s+', text, re.IGNORECASE):
        score += 15

    if re.search(r'\d+\s*m\s+(?:above|Legal|Lec)', text, re.IGNORECASE):
        score += 10

    noise_count = len(re.findall(r'[#@%&\*\$]{2,}', text))
    score -= noise_count * 5

    word_count = len([w for w in text.split() if len(w) > 2 and w not in ['km', 'h', 'uT', 'AM', 'PM']])
    score += min(word_count, 20)

    return max(score, 0)


def extract_date_from_whatsapp_filename(filename):
    """Extrage data și ora din numele fișierului WhatsApp și le formatează corect."""
    # Pattern pentru: WhatsApp Image 2025-10-20 at 14.12.53
    pattern = r'WhatsApp Image (\d{4})-(\d{2})-(\d{2}) at (\d{1,2})\.(\d{2})\.(\d{2})'
    match = re.search(pattern, filename)

    if match:
        year, month, day, hour, minute, second = match.groups()

        # Formatează data ca DD.MM.YYYY
        data_str = f"{day}.{month}.{year}"
        # Formatează ora ca HH:MM (fără secunde pentru compatibilitate)
        ora_str = f"{hour}:{minute}"

        print(f"📅 Data extrasă din nume WhatsApp: {data_str} {ora_str}:{second}")
        return data_str, ora_str

    # Fallback pentru alte formate WhatsApp
    pattern_fallback = r'WhatsApp Image (\d{4})-(\d{2})-(\d{2}) at (\d{1,2})\.(\d{2})'
    match_fallback = re.search(pattern_fallback, filename)

    if match_fallback:
        year, month, day, hour, minute = match_fallback.groups()
        data_str = f"{day}.{month}.{year}"
        ora_str = f"{hour}:{minute}"
        print(f"📅 Data extrasă din nume WhatsApp (fallback): {data_str} {ora_str}")
        return data_str, ora_str

    return None, None


def generate_new_filename(original_name, data):
    """Generează un nume nou bazat pe WhatsApp sau Data OCR. Fără duplicate _1."""
    try:
        extension = os.path.splitext(original_name)[1].lower()
        new_name = original_name  # Default rămâne numele original

        # 1. ÎNCEARCĂ SĂ EXTRAGI DATA DIN NUMELE WHATSAPP
        pattern = r'WhatsApp[ _]Image[ _](\d{4})-(\d{2})-(\d{2})[ _]at[ _](\d{1,2})[\._](\d{2})[\._](\d{2})'
        match = re.search(pattern, original_name)

        if match:
            year, month, day, hour, minute, second = match.groups()

            data_noua = f"{year}{month}{day}"
            ora_noua = f"{hour.zfill(2)}{minute.zfill(2)}{second.zfill(2)}"

            new_name = f"{data_noua}_{ora_noua}{extension}"
            print(f"✅ Redenumire WhatsApp: {new_name}")

        # 2. FALLBACK: Dacă nu e WhatsApp, încearcă data din OCR
        elif data.get('data') and data.get('ora'):
            try:
                data_str = data['data']
                ora_str = data['ora']

                parts = data_str.split('.')
                if len(parts) == 3:
                    day, month, year = parts
                    data_noua = f"{year}{month.zfill(2)}{day.zfill(2)}"

                    ora_parts = ora_str.split(':')
                    if len(ora_parts) >= 2:
                        hour, minute = ora_parts[:2]
                        ora_noua = f"{hour.zfill(2)}{minute.zfill(2)}00"

                        new_name = f"{data_noua}_{ora_noua}{extension}"
            except Exception as e:
                print(f"⚠️ Eroare generare nume din OCR: {e}")

        # 3. RETURNARE DIRECTĂ (Fără verificare _1)
        # Returnăm numele calculat. Dacă există deja pe disc, sistemul de operare îl va suprascrie.
        return new_name

    except Exception as e:
        print(f"❌ Eroare generare nume fișier: {e}")
        return original_name


def open_processed_folder():
    """Deschide folderul processed în explorer/finder."""
    try:
        processed_path = os.path.abspath(app.config['PROCESSED_FOLDER'])

        if platform.system() == "Windows":
            os.startfile(processed_path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", processed_path])
        else:
            subprocess.run(["xdg-open", processed_path])

        print(f"📁 Folder deschis: {processed_path}")
        return True
    except Exception as e:
        print(f"❌ Eroare deschidere folder: {e}")
        return False


def clear_processed_folder():
    """Șterge toate fișierele din folderul processed."""
    try:
        processed_path = app.config['PROCESSED_FOLDER']
        deleted_count = 0

        for filename in os.listdir(processed_path):
            file_path = os.path.join(processed_path, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    deleted_count += 1
                    print(f"🗑️  Șters: {filename}")
            except Exception as e:
                print(f"❌ Eroare ștergere {filename}: {e}")

        print(f"✅ Folderul processed a fost golit: {deleted_count} fișiere șterse")
        return True, f"Șterse {deleted_count} fișiere"
    except Exception as e:
        print(f"❌ Eroare golire folder: {e}")
        return False, str(e)


def process_single_file_dual_ocr(filepath, filename, original_filename_display):
    """Procesează un singur fișier cu DUAL OCR PARALEL."""
    try:
        print(f"\n📄 Procesez: {filename}")

        if not os.path.exists(filepath):
            print(f"❌ Fișierul nu există: {filepath}")
            return {
                'nume_fisier': filename,
                'status': 'error',
                'error': 'Fișierul nu există pe server',
                'text_extras': '',
                'ocr1_text': '',
                'ocr2_text': '',
                'ocr1_score': 0,
                'ocr2_score': 0,
                'strada_si_numar': '',
                'fisier_redenumit': filename
            }

        # 🔥 PARALELIZARE INTERNĂ pentru cele 2 OCR-uri
        def run_ocr1():
            """OCR cu preprocesare method1"""
            try:
                processed_img1 = preprocess_image_method1(filepath)
                if processed_img1 is not None:
                    results1 = reader.readtext(processed_img1, detail=0)
                    return clean_and_combine_lines(results1)
                return ""
            except Exception as e:
                print(f"❌ OCR 1 a eșuat: {e}")
                return ""

        def run_ocr2():
            """OCR cu preprocesare agresivă PIL"""
            try:
                processed_img3 = preprocess_pil_aggressive(filepath)
                if processed_img3 is not None:
                    results3 = reader.readtext(processed_img3, detail=0)
                    return clean_and_combine_lines(results3)
                return ""
            except Exception as e:
                print(f"❌ OCR 2 a eșuat: {e}")
                return ""

        # 🔥 LANSEAZĂ AMBELE OCR-URI ÎN PARALEL
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_ocr1 = executor.submit(run_ocr1)
            future_ocr2 = executor.submit(run_ocr2)

            # Așteaptă rezultatele ambelor OCR-uri
            text1 = future_ocr1.result()
            text3 = future_ocr2.result()

        # Afișează rezultatele
        print("🔍 OCR 1 (Contrast crescut):")
        print(f"   {text1[:150]}..." if len(text1) > 150 else f"   {text1}")

        print("🔍 OCR 2 (AGRESIV PIL):")
        print(f"   {text3[:150]}..." if len(text3) > 150 else f"   {text3}")

        # ... restul codului rămâne la fel ...
        score1 = calculate_text_quality_score_improved(text1)
        score3 = calculate_text_quality_score_improved(text3)

        print(f"📊 Scoruri: OCR1={score1} | OCR2={score3}")

        # Alege textul cu scorul mai mare
        texts = [text1, text3]
        scores = [score1, score3]
        max_score = max(scores) if scores else 0

        # LOGICA ÎMBUNĂTĂȚITĂ PENTRU STATUSURI
        if max_score < 10:
            print("⚠️ Scor OCR foarte mic - poate fi o poză fără text relevant")
            final_text = ""
            data_status = 'warning'
            error_msg = 'Text limitat sau inexistent'
            coords_value = "Fără coordonate poza"
        elif not texts or max_score == 0:
            print("❌ Niciun OCR nu a produs text valid")
            final_text = ""
            data_status = 'warning'
            error_msg = 'Text OCR negăsit'
            coords_value = "Fără coordonate poza"
        else:
            best_indices = [i for i, score in enumerate(scores) if score == max_score]
            if len(best_indices) > 1:
                best_index = 1
            else:
                best_index = best_indices[0]

            method_names = ["Contrast crescut", "AGRESIV PIL"]
            final_text = texts[best_index]
            print(f"✅ Folosesc OCR {best_index + 1} ({method_names[best_index]}) - scor: {scores[best_index]}")
            data_status = 'success'
            error_msg = ''
            coords_value = ''

        # Procesează textul extras
        data = {
            'nume_fisier': original_filename_display,
            'latitudine': coords_value,
            'longitudine': coords_value,
            'altitudine': '',
            'accuracy': '',
            'data': '',
            'ora': '',
            'strada': '',
            'numar': '',
            'strada_si_numar': '',
            'localitate': '',
            'judet': 'Bihor',
            'cod_postal': '',
            'adresa_completa': '',
            'location_provider': 'GPS',
            'status': data_status,
            'text_extras': final_text,
            'ocr1_text': text1,
            'ocr2_text': text3,
            'ocr1_score': score1,
            'ocr2_score': score3,
            'fisier_redenumit': '',
            'error': error_msg
        }

        # Dacă avem text relevant (scor > 10), încercăm să extragem coordonatele
        if final_text and max_score >= 10:
            data = extract_address_info_improved(final_text, data)
            data = extract_coordinates_universal(final_text, data)
            data = extract_datetime_universal(final_text, data)
            data = extract_altitude_improved_v2(final_text, data)
            data = extract_accuracy(final_text, data)

            if data['latitudine'] == "Fără coordonate poza" or not data['latitudine']:
                data['status'] = 'error'
                data['error'] = 'Coordonate GPS negăsite în text'
                print("❌ Eroare: Text OCR bun dar coordonate negăsite")
            elif not data['data']:
                data['status'] = 'warning'
                data['error'] = 'Data incompletă'
                print("⚠️ Avertisment: Data lipsă")
            else:
                print("✅ Validare OK")

        new_filename_raw = generate_new_filename(original_filename_display, data)

        # Numele pe disc trebuie să fie totuși "safe"
        new_filename_secure = secure_filename(new_filename_raw)

        # Dacă secure_filename a schimbat formatul (ex: a scos puncte), ne asigurăm că păstrăm extensia
        if not new_filename_secure.lower().endswith(os.path.splitext(original_filename_display)[1].lower()):
            base, ext = os.path.splitext(new_filename_raw)
            new_filename_secure = secure_filename(base) + ext

        data['fisier_redenumit'] = new_filename_raw  # În Excel arătăm numele frumos

        # Returnăm și numele securizat pentru sistemul de fișiere
        data['fisier_system_name'] = new_filename_secure

        # Afișează rezultatul final
        print(f"📊 Status final: {data['status']}")
        if data['status'] == 'success':
            print(f"   🗺️  X (Lat): {data['latitudine']} | Y (Long): {data['longitudine']}")
            print(f"   📍 {data['strada_si_numar']}, {data['localitate']}")
            print(f"   📅 {data['data']} {data['ora']}")
            print(f"   ⛰️  {data['altitudine']}")
            print(f"   🎯  {data['accuracy']}")
            print(f"   📁 Nume nou: {new_filename_raw}")

        return data

    except Exception as e:
        print(f"❌ Eroare procesare DUAL OCR: {str(e)}")
        return {
            'nume_fisier': filename,
            'status': 'error',
            'error': str(e),
            'text_extras': '',
            'ocr1_text': '',
            'ocr2_text': '',
            'ocr1_score': 0,
            'ocr2_score': 0,
            'strada_si_numar': '',
            'fisier_redenumit': filename,
            'latitudine': "Fără coordonate poza",
            'longitudine': "Fără coordonate poza"
        }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    try:
        if 'files[]' not in request.files:
            return jsonify({'error': 'Nu au fost selectate fișiere'}), 400

        files = request.files.getlist('files[]')
        results = []

        print(f"🚀 Procesez {len(files)} imagini - mod optimizat")

        for file in files:
            if file and allowed_file(file.filename):
                # 1. Capturăm numele original (cu spații)
                raw_filename = file.filename

                # 2. Creăm numele sigur pentru salvare pe disc
                safe_filename = secure_filename(raw_filename)

                filepath = os.path.join(app.config['PROCESSED_FOLDER'], safe_filename)
                file.save(filepath)

                # 3. Trimitem AMBELE nume către procesare
                data = process_single_file_dual_ocr(filepath, safe_filename, raw_filename)

                # 4. Redenumire fizică pe disc
                # Luăm numele de sistem calculat (cel safe)
                new_system_name = data.get('fisier_system_name', safe_filename)

                if new_system_name != safe_filename:
                    new_filepath = os.path.join(app.config['PROCESSED_FOLDER'], new_system_name)
                    shutil.move(filepath, new_filepath)

                # Curățăm câmpul intern înainte de a trimite la frontend
                if 'fisier_system_name' in data:
                    del data['fisier_system_name']

                results.append(data)

        print(f"🎉 Procesare completă: {len(results)} imagini")
        return jsonify({'results': results})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download-csv', methods=['POST'])
def download_csv():
    data = request.json.get('data', [])
    if not data:
        return jsonify({'error': 'Nu există date'}), 400

    output = io.StringIO()
    # AM SCOS 'adresa_completa' și 'location_provider'
    fieldnames = [
        'nume_fisier',
        'fisier_redenumit',
        'strada_si_numar',
        'localitate',
        'judet',
        'cod_postal',
        'latitudine',
        'longitudine',
        'altitudine',
        'accuracy',       # Asta a rămas, e utilă
        'data',
        'ora',
        'status',
        'text_extras',
        'ocr1_score',
        'ocr2_score'
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        # Filtrăm doar cheies care sunt în fieldnames pentru a evita erori
        clean_row = {k: row.get(k, '') for k in fieldnames}
        writer.writerow(clean_row)

    output.seek(0)
    bytes_out = io.BytesIO()
    bytes_out.write(output.getvalue().encode('utf-8-sig'))
    bytes_out.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'coordonate_gps_{timestamp}.csv'
    return send_file(bytes_out, mimetype='text/csv', as_attachment=True, download_name=filename)


@app.route('/open-processed-folder', methods=['POST'])
def open_processed_folder_route():
    """Endpoint pentru deschiderea folderului processed."""
    try:
        success = open_processed_folder()
        if success:
            return jsonify({'message': 'Folderul processed a fost deschis'})
        else:
            return jsonify({'error': 'Nu s-a putut deschide folderul'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/clear-processed-folder', methods=['POST'])
def clear_processed_folder_route():
    """Endpoint pentru golirea folderului processed."""
    try:
        success, message = clear_processed_folder()
        if success:
            return jsonify({'message': f'Folderul processed a fost golit: {message}'})
        else:
            return jsonify({'error': f'Eroare la golirea folderului: {message}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
