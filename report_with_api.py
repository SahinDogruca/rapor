import os
import io
import urllib.parse
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
import google.generativeai as genai
from bs4 import BeautifulSoup
from weasyprint import HTML
from dotenv import load_dotenv
import matplotlib.pyplot as plt

# Load environment variables from .env file
load_dotenv()

# --- FastAPI Application Initialization ---
app = FastAPI(
    title="Mülakat Raporu Oluşturucu API",
    description="CSV verilerinden tutarlı ve görsel olarak zenginleştirilmiş PDF mülakat raporları oluşturur.",
    version="1.4.0",  # Version updated to WeasyPrint for PDF generation
)

# --- Gemini API Configuration ---
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
    )
except KeyError:
    raise RuntimeError(
        "GEMINI_API_KEY ortam değişkeni bulunamadı. Lütfen .env dosyasında ayarlayın."
    )

# --- Helper Functions ---


def get_image_base64(image_name: str) -> str:
    """
    Reads the specified image file (assuming it's in the same directory as the script)
    and returns it as a Base64 encoded string.
    """
    script_dir = os.path.dirname(__file__)
    image_path = os.path.join(script_dir, image_name)

    print(f"Trying: Image file path: {image_path}")

    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        return encoded_string
    except FileNotFoundError:
        print(f"Error: Image file not found: {image_path}")
        return ""
    except Exception as e:
        print(f"Error reading image: {e}")
        return ""


def create_emotion_charts_html(emotion_data: dict) -> str:
    """
    Generates a modern and stylish SVG bar chart from emotion data.

    Args:
        emotion_data: A dictionary containing emotion names and percentage values.

    Returns:
        An HTML string containing the SVG bar chart or a message if no data is available.
    """
    labels_map = {
        "duygu_mutlu_%": "Mutlu",
        "duygu_kizgin_%": "Kızgın",
        "duygu_igrenme_%": "İğrenme",
        "duygu_korku_%": "Korku",
        "duygu_uzgun_%": "Üzgün",
        "duygu_saskin_%": "Şaşkın",
        "duygu_dogal_%": "Doğal",
    }

    colors = {
        "Mutlu": "#d4eac8",
        "Kızgın": "#e5b9b5",
        "İğrenme": "#d3cdd7",
        "Korku": "#a9b4c2",
        "Üzgün": "#b7d0e2",
        "Şaşkın": "#fdeac9",
        "Doğal": "#d8d8d8",
    }

    emotion_values = []
    emotion_keys_ordered = [
        "duygu_mutlu_%",
        "duygu_kizgin_%",
        "duygu_igrenme_%",
        "duygu_korku_%",
        "duygu_uzgun_%",
        "duygu_saskin_%",
        "duygu_dogal_%",
    ]

    for key in emotion_keys_ordered:
        if key in emotion_data:
            emotion_name = labels_map.get(key, "Bilinmeyen")
            value = emotion_data.get(key, 0)
            emotion_values.append({"name": emotion_name, "value": value})

    if not emotion_values:
        return "<p>Görselleştirilecek duygu verisi bulunamadı.</p>"

    # Calculate dynamic SVG height
    base_height = 250  # Height corresponding to 100% value
    max_value = max(e["value"] for e in emotion_values)
    if max_value < 5:
        max_value = 5  # Minimum limit to prevent very small values
    svg_height = int((max_value / 100) * base_height) + 80  # + padding

    svg_width = 600
    padding = 40
    bar_spacing = 15
    label_offset = 5

    num_bars = len(emotion_values)
    bar_width = (svg_width - 2 * padding - (num_bars - 1) * bar_spacing) / num_bars
    if bar_width <= 0:
        bar_width = 20

    svg_elements = []

    # Add title
    svg_elements.append(
        f'<text x="{svg_width / 2}" y="25" font-family="IBMPlexSans" font-size="12" text-anchor="middle" fill="#333" font-weight="400">Aday Duygu Analizi</text>'
    )

    # X-axis line
    svg_elements.append(
        f'<line x1="{padding}" y1="{svg_height - padding}" x2="{svg_width - padding}" y2="{svg_height - padding}" stroke="#ccc" stroke-width="1"/>'
    )

    # Y-axis labels (0%, 25%, 50%, 75%, 100%)
    for i in range(5):
        percent = i * 25
        y_val = (
            svg_height - padding - ((percent / max_value) * (svg_height - 2 * padding))
        )
        svg_elements.append(
            f'<text x="{padding - 10}" y="{y_val + 5}" font-family="IBMPlexSans" font-size="10" text-anchor="end" fill="#555">{percent}%</text>'
        )
        svg_elements.append(
            f'<line x1="{padding}" y1="{y_val}" x2="{padding + 5}" y2="{y_val}" stroke="#ccc" stroke-width="0.5"/>'
        )

    for i, emotion in enumerate(emotion_values):
        x = padding + i * (bar_width + bar_spacing)
        bar_height = (emotion["value"] / max_value) * (svg_height - 2 * padding)
        y = svg_height - padding - bar_height
        fill_color = colors.get(emotion["name"], "#cccccc")

        svg_elements.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" fill="{fill_color}" rx="3" ry="3"/>'
        )

        text_y = y - label_offset
        if text_y < 15:
            text_y = y + 15
            text_fill = "#333"
        else:
            text_fill = "#333"

        svg_elements.append(
            f'<text x="{x + bar_width / 2}" y="{text_y}" font-family="IBMPlexSans" font-size="12" text-anchor="middle" fill="{text_fill}" font-weight="bold">{emotion["value"]:.1f}%</text>'
        )

        svg_elements.append(
            f'<text x="{x + bar_width / 2}" y="{svg_height - padding + 20}" font-family="IBMPlexSans" font-size="11" text-anchor="middle" fill="#555">{emotion["name"]}</text>'
        )

    svg_content = f"""
    <div style="text-align: center; margin: 20px auto; opacity: 0.6;">
        <svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" style="background-color: #fcfcfc; border: 1px solid #eee; border-radius: 8px;">
            {''.join(svg_elements)}
        </svg>
    </div>
    """
    return svg_content


def create_emotion_charts_html_2(emotion_data: dict) -> str:
    """
    Draws the bar chart with (candidate value – average) difference instead of absolute percentages.
    Bars go downwards for negative differences.
    """
    labels_map = {
        "duygu_mutlu_%": "Mutlu",
        "duygu_kizgin_%": "Kızgın",
        "duygu_igrenme_%": "İğrenme",
        "duygu_korku_%": "Korku",
        "duygu_uzgun_%": "Üzgün",
        "duygu_saskin_%": "Şaşkın",
        "duygu_dogal_%": "Doğal",
    }

    colors = {
        "Mutlu": "#d4eac8",
        "Kızgın": "#e5b9b5",
        "İğrenme": "#d3cdd7",
        "Korku": "#a9b4c2",
        "Üzgün": "#b7d0e2",
        "Şaşkın": "#fdeac9",
        "Doğal": "#d8d8d8",
    }

    # Original order
    emotion_keys = [
        "duygu_mutlu_%",
        "duygu_kizgin_%",
        "duygu_igrenme_%",
        "duygu_korku_%",
        "duygu_uzgun_%",
        "duygu_saskin_%",
        "duygu_dogal_%",
    ]
    avg_keys = [
        "avg_duygu_mutlu_%",
        "avg_duygu_kizgin_%",
        "avg_duygu_igrenme_%",
        "avg_duygu_korku_%",
        "avg_duygu_uzgun_%",
        "avg_duygu_saskin_%",
        "avg_duygu_dogal_%",
    ]

    # Calculate differences
    diffs = []
    for key, avg_key in zip(emotion_keys, avg_keys):
        name = labels_map[key]
        val = emotion_data.get(key, 0)
        avg = emotion_data.get(avg_key, 0)
        diff = round(val - avg, 2)
        diffs.append({"name": name, "value": diff})

    if not diffs:
        return "<p>Görselleştirilecek duygu verisi bulunamadı.</p>"

    # Scale: largest absolute difference
    max_abs = max(abs(d["value"]) for d in diffs)
    if max_abs < 5:
        max_abs = 5

    # Chart dimensions (symmetric for top + bottom)
    base_height = 250
    padding = 40
    panel = (max_abs / 100) * base_height
    svg_height = int(panel * 2 + padding * 2)
    svg_width = 600
    bar_spacing = 15
    num_bars = len(diffs)
    bar_width = (svg_width - 2 * padding - (num_bars - 1) * bar_spacing) / num_bars

    # Zero line (baseline) at the midpoint
    baseline_y = padding + panel

    svg_elems = []

    # Add title
    svg_elems.append(
        f'<text x="{svg_width / 2}" y="25" font-family="IBMPlexSans" font-size="12" text-anchor="middle" fill="#333" font-weight="400">Aday Duygularının Ortalamadan Farkı</text>'
    )

    # Y=0 line
    svg_elems.append(
        f'<line x1="{padding}" y1="{baseline_y}" x2="{svg_width-padding}" '
        f'y2="{baseline_y}" stroke="#ccc" stroke-width="1"/>'
    )

    # Y-axis labels (from negative to positive)
    for perc in [-max_abs, 0, max_abs]:
        # We can place our percentage labels as -X%, -X/2%, 0%, +X/2%, +X%
        # relative scale instead of exact -100...100
        pos = baseline_y - (perc / max_abs) * panel
        label = f"{perc:.0f}%"
        svg_elems.append(
            f'<text x="{padding-10}" y="{pos+4}" font-family="IBMPlexSans" '
            f'font-size="10" text-anchor="end" fill="#555">{label}</text>'
        )
        svg_elems.append(
            f'<line x1="{padding}" y1="{pos}" x2="{padding+5}" y2="{pos}" '
            f'stroke="#ccc" stroke-width="0.5"/>'
        )

    # Bars
    for i, item in enumerate(diffs):
        x = padding + i * (bar_width + bar_spacing)
        val = item["value"]
        height = abs(val) / max_abs * panel
        if val >= 0:
            y = baseline_y - height
        else:
            y = baseline_y
        color = colors.get(item["name"], "#ccc")
        svg_elems.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{height}" '
            f'fill="{color}" rx="3" ry="3"/>'
        )
        # Value labels
        txt_y = y - 5 if val >= 0 else y + height + 15
        svg_elems.append(
            f'<text x="{x+bar_width/2}" y="{txt_y}" font-family="IBMPlexSans" '
            f'font-size="12" text-anchor="middle" fill="#333" font-weight="bold">'
            f"{val:+.1f}%</text>"
        )
        # Emotion name
        svg_elems.append(
            f'<text x="{x+bar_width/2}" y="{baseline_y + panel + 20}" '
            f'font-family="IBMPlexSans" font-size="11" text-anchor="middle" fill="#555">'
            f'{item["name"]}</text>'
        )

    svg = (
        f'<div style="text-align:center;margin:20px auto;opacity:0.6;">'
        f'<svg width="{svg_width}" height="{svg_height}" '
        f'viewBox="0 0 {svg_width} {svg_height}" '
        f'style="background-color:#fcfcfc;border:1px solid #eee;border-radius:8px;">'
        + "".join(svg_elems)
        + "</svg></div>"
    )
    return svg


def format_qa_section(qa_list: list) -> str:
    """
    Converts a list of questions and answers into a readable HTML format.
    """
    html = ""
    for item in qa_list:
        html += f"""
        <div class="qa-item" style="margin-bottom: 15px; padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <p style="font-weight: bold; color: #34495e;">Soru: {item['soru']}</p>
            <p style="color: #555; margin-top: 5px;">Cevap: {item['cevap']}</p>
        </div>
        """
    return html


def get_suitability_color(score: float, avg_score: float) -> str:
    """
    Determines the color based on the suitability score relative to the average score.
    Green: score >= avg_score + 5
    Light Green: avg_score + 2.5 <= score < avg_score + 5
    Yellow: avg_score - 2.5 <= score < avg_score + 2.5
    Orange: avg_score - 5 <= score < avg_score - 2.5
    Red: score < avg_score - 5
    """
    if score >= avg_score + 5:
        return "#27ae60"  # Green
    elif score >= avg_score + 2.5:
        return "#8bc34a"  # Light Green
    elif score >= avg_score - 2.5:
        return "#ffc107"  # Yellow
    elif score >= avg_score - 5:
        return "#ff9800"  # Orange
    else:
        return "#f44336"  # Red


def generate_llm_prompt(row_data: dict, formatted_qa_html: str) -> str:
    """
    Generates the prompt for Gemini LLM based on the given aggregated data row
    and a new, cleaner HTML template.
    The watermark image is not sent to the LLM, it will be added later.
    """

    # Determine the color for the suitability score based on avg_llm_skoru
    suitability_color = get_suitability_color(row_data['llm_skoru'], row_data['avg_llm_skoru'])

    html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @font-face {{
            font-family: "IBMPlexSans";
            src: url("fonts/IBMPlexSans-Regular.ttf");
            font-weight: normal;
            font-style: normal;
        }}
        @font-face {{
            font-family: "IBMPlexSans";
            src: url("fonts/IBMPlexSans-Medium.ttf");
            font-weight: 500;
            font-style: normal;
        }}
        @font-face {{
            font-family: "IBMPlexSans";
            src: url("fonts/IBMPlexSans-Bold.ttf");
            font-weight: bold;
            font-style: normal;
        }}
        body {{
            font-family: "IBMPlexSans", sans-serif;
            line-height: 1.7;
            margin: 25px;
            color: #333;
            background-color: #ffffff;
            font-size: 10pt;
            position: relative;
            margin-bottom: 40px;
            width: 100vw;
        }}
        h1 {{ 
            color: #2c3e50; 
            text-align: center; 
            border-bottom: 2px solid #2b3d4f; 
            padding-bottom: 10px; 
            font-size: 24px; 
            font-weight: bold;
        }}
        h2 {{ 
            color: #34495e; 
            margin-top: 35px; 
            border-bottom: 1px solid #bdc3c7; 
            padding-bottom: 8px; 
            font-size: 20px;
            font-weight: 500;
        }}
        h3 {{ 
            color: #7f8c8d; 
            font-size: 16px; 
            margin-bottom: 15px; 
            font-weight: 500;
        }}
        .section {{ margin-bottom: 30px; }}
        #pie-chart-placeholder {{ width: 100%; height: auto; margin: 20px auto; text-align: center; }}

        /* Watermark Image Container */
        .watermark-image-container {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: -1;
            pointer-events: none;
            opacity: 0.05;
            width: 70%;
            max-width: 600px;
            height: auto;
            text-align: center;
        }}
        .watermark-image-container img {{
            width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }}

        /* Page layout for WeasyPrint - EDITED PART */
        @page {{
            margin: 70px 12.5px 70px 12.5px;
            @top-left {{
                content: element(header_logo);
                vertical-align: top;
            }}
            @top-right {{
                content: element(header_info);
                vertical-align: top;
            }}
            @bottom-center {{
                content: element(footer_content);
                vertical-align: bottom;
                padding-bottom: 10px;
            }}
        }}

        /* Footer style */
        .page-footer {{
            display: block;
            position: running(footer_content);
            width: 100%;
            background-color: #ffffff;
            padding: 10px 10px;
            text-align: center;
            font-size: 8px;
            color: #555;
            box-sizing: border-box;
        }}
        .footer-divider {{
            border-top: 0.5px solid #ccc;
            margin: 0 auto 5px auto;
            width: 90%;
        }}
        .footer-company-name {{
            font-weight: bold;
            margin-bottom: 2px;
        }}
        .footer-contact-info {{
            font-size: 7px;
            line-height: 1.2;
            white-space: nowrap;
            display: flex;
            justify-content: center;
            gap: 10px;
        }}

        /* LOGO HEADER - EDITED PART */
        .page-header-logo {{
            margin-top: 20px;
            margin-left: 20px;
            position: running(header_logo);
            text-align: left;
        }}
        .page-header-logo img {{
            width: 40px;
            height: auto;
            display: inline-block;
        }}

        /* TOP RIGHT INFO BOX - REINTRODUCED AND MODIFIED */
        .page-header-info {{
            margin-top: 30px;
            margin-right: 20px;
            position: running(header_info);
            text-align: right; /* Align right */
            font-size: 15px; /* Slightly larger font */
            color: #223;
            line-height: 1.2;
            min-width: 150px;
            font-weight: bold; /* Make it bold */
        }}
        .suitability-score {{
            color: {suitability_color}; /* Dynamic color based on score */
        }}
        .suitability-label {{
            color: #2b3d4f; /* Fixed color for "Pozisyona Uygunluk:" */
        }}
    </style>
</head>
<body>
    <!-- Logo header element -->
    <div class="page-header-logo" id="header_logo">
        <img src="{{{{logo_src}}}}" alt="Logo" />
    </div>
    
    <!-- Top right info box element - Now displays suitability score -->
    <div class="page-header-info" id="header_info">
        <span class="suitability-label">Pozisyona Uygunluk:</span> <span class="suitability-score">%{{{{llm_score}}}}</span>
    </div>
    
    <!-- Footer element -->
    <div class="page-footer">
        <div class="footer-divider"></div>
        <div class="footer-company-name">DeepWork Bilişim Teknolojileri A.Ş.</div>
        <div class="footer-contact-info">
            <span>info@hrai.com.tr</span>
            <span>-</span>
            <span>İstanbul Medeniyet Üniversitesi Kuzey Kampüsü Medeniyet Teknopark Kuluçka Merkezi Üsküdar/İstanbul</span>
            <span>-</span>
            <span>+90 553 808 32 77</span>
        </div>
    </div>
    
    <!-- Watermark Image Container -->
    <div class="watermark-image-container" id="watermark-placeholder">
        <!-- Image will be added here dynamically -->
    </div>
    
    <h1>{row_data['kisi_adi']} - Mülakat Değerlendirme Raporu</h1>
    
    <div class="section">
        <h2>1) Genel Bakış</h2>
        <p>{{{{genel_bakis_icerik}}}}</p>
    </div>
    
    <div class="section">
        <h2>2) Analiz</h2>
        <h3>Duygu Analizi:</h3>
        <div id="bar-chart-placeholder"></div> <p>{{{{duygu_analizi_yorumu}}}}</p>

        <h3>Dikkat Analizi</h3>
        <p>{{{{dikkat_analizi_yorumu}}}}</p>
    </div>
    
    <div class="section">
        <h2>3) Genel Değerlendirme</h2>
        <p>{{{{genel_degerlendirme_icerik}}}}</p>
    </div>

    <div class="section">
        <h2>4) Sorular ve Cevaplar</h2>
        {formatted_qa_html}
    </div>
    
    <div class="section">
        <h2>5) Sonuçlar ve Öneriler</h2>
        <p>{{{{sonuclar_oneriler_icerik}}}}</p>
    </div>

    {{{{uygunluk_degerlendirmesi_bolumu}}}}
</body>
</html>
"""

    if row_data["tip"] == 0:
        # MODIFIED PART: Candidate Suitability Section Added
        prompt_instructions = f"""
Lütfen aşağıdaki HTML şablonunu verilen mülakat verilerine göre doldurarak eksiksiz bir HTML raporu oluştur.
Veriler:
- Aday Adı: {row_data['kisi_adi']}
- Mülakat Adı: {row_data['mulakat_adi']}
- LLM Skoru: {row_data['llm_skoru']}, Ortalama LLM Skoru: {row_data['avg_llm_skoru']}
- Duygu Analizi (%): Mutlu {row_data['duygu_mutlu_%']}, Kızgın {row_data['duygu_kizgin_%']}, İğrenme {row_data['duygu_igrenme_%']}, Korku {row_data['duygu_korku_%']}, Üzgün {row_data['duygu_uzgun_%']}, Şaşkın {row_data['duygu_saskin_%']}, Doğal {row_data['duygu_dogal_%']}
- Dikkat Analizi: Ekran Dışı Süre {row_data['ekran_disi_sure_sn']} sn, Ekran Dışı Bakış Sayısı {row_data['ekran_disi_sayisi']}, Ortalama Ekran Dışı Süre {row_data['avg_ekran_disi_sure_sn']} sn, Ortalama Ekran Dışı Bakış Sayısı {row_data['avg_ekran_disi_sayisi']}

Doldurulacak Alanlar İçin Talimatlar:
1.  `{{{{genel_bakis_icerik}}}}`: Adayın genel performansını, iletişim becerilerini ve mülakatın genel seyrini özetleyen, en az iki paragraftan oluşan detaylı bir giriş yaz.
2.  `{{{{duygu_analizi_yorumu}}}}`: Yukarıda verilen sayısal duygu analizi verilerini yorumla. Hangi duyguların baskın olduğunu ve bunun mülakat bağlamında ne anlama gelebileceğini analiz et. Bu yorum en az iki detaylı paragraf olmalıdır. Giriş cümlesi tam olarak şu olmalı: "Görüntü ve ses analiz edilerek adayın duygu analizi yapılmıştır."
3.  `{{{{dikkat_analizi_yorumu}}}}`: Ekran dışı süre ve bakış sayısı verilerini yorumla. Bu verilerin adayın dikkat seviyesi veya odaklanması hakkında ne gibi ipuçları verdiğini açıkla. Bu yorum en az bir detaylı paragraf olmalıdır.
4.  `{{{{genel_degerlendirme_icerik}}}}`: Adayın verdiği cevapları, genel tavrını ve analiz sonuçlarını birleştirerek kapsamlı bir değerlendirme yap. Adayın güçlü ve gelişime açık yönlerini belirt. Bu bölüm en az üç paragraf olmalıdır.
5.  `{{{{sonuclar_oneriler_icerik}}}}`: Bu bölümü **sadece İnsan Kaynakları profesyonellerine yönelik** olarak yaz. Adayın pozisyona uygunluğu hakkında net bir sonuca var. İşe alım kararı için somut önerilerde bulun. Adaya yönelik bir dil kullanma. Bu bölüm en az iki paragraf olmalıdır.
6.  **YENİ TALİMAT**: `{{{{uygunluk_degerlendirmesi_bolumu}}}}`: Adayın pozisyona uygunluk yüzdesini (0-100 arası bir tam sayı) ve bu yüzdeyi destekleyen kısa bir açıklamayı HTML formatında oluştur. Yüzdeyi `{row_data['llm_skoru']}` değerini dikkate alarak belirle. Örnek format:
    ```html
    <div class="section">
        <h2>6) Pozisyona Uygunluk Değerlendirmesi</h2>
        <p style="font-size: 24px; font-weight: bold; color: {suitability_color}; text-align: left;">Pozisyona Uygunluk: %{{{{llm_score}}}}</p>
        <p>Adayın genel mülakat performansı, teknik bilgi ve iletişim becerileri, pozisyonun gerektirdiği yetkinliklerle yüksek düzeyde örtüşmektedir. Duygu analizi ve dikkat seviyesi de olumlu bir tablo çizmektedir.</p>
    </div>
    ```
    Yüzdeyi ve açıklamayı doldururken, verilen LLM Skoru'nu doğrudan uygunluk yüzdesi olarak kullanabilir veya bu skora dayanarak mantıklı bir uygunluk yüzdesi türetebilirsin. Açıklama 1-2 paragraf uzunluğunda olmalıdır. Pozisyona uygunluk yüzdesi metni büyük ve kalın olmalıdır.

Önemli Kurallar:
- Üretilen tüm metin **sadece Türkçe** olmalıdır.
- Raporun tonu profesyonel, resmi ve veri odaklı olmalıdır.
- Kullanıcıya yönelik hiçbir not, açıklama veya meta-yorum ekleme.
- Sadece ve sadece aşağıdaki HTML şablonunu doldurarak yanıt ver. Başka hiçbir metin ekleme.

İşte doldurman gereken şablon:
{html_template}
"""

    elif row_data["tip"] == 1:
        # For customer report, leave the suitability section empty
        prompt_instructions = f"""
Lütfen aşağıdaki HTML şablonunu verilen mülakat verilerine göre doldurarak eksiksiz bir HTML raporu oluştur.
Veriler:
- Müşteri Adı: {row_data['kisi_adi']}
- Görüşme Adı: {row_data['mulakat_adi']}
- Duygu Analizi (%): Mutlu {row_data['duygu_mutlu_%']}, Kızgın {row_data['duygu_kizgin_%']}, İğrenme {row_data['duygu_igrenme_%']}, Korku {row_data['duygu_korku_%']}, Üzgün {row_data['duygu_uzgun_%']}, Şaşkın {row_data['duygu_saskin_%']}, Doğal {row_data['duygu_dogal_%']}
- Dikkat Analizi: Ekran Dışı Süre {row_data['ekran_disi_sure_sn']} sn, Ekran Dışı Bakış Sayısı {row_data['ekran_disi_sayisi']}, Ortalama Ekran Dışı Süre {row_data['avg_ekran_disi_sure_sn']} sn, Ortalama Ekran Dışı Bakış Sayısı {row_data['avg_ekran_disi_sayisi']}

Doldurulacak Alanlar İçin Talimatlar:
1.  `{{{{genel_bakis_icerik}}}}`: Müşterinin genel performansını, iletişim becerilerini ve görüşmenin genel seyrini özetleyen, en az iki paragraftan oluşan detaylı bir giriş yaz.
2.  `{{{{duygu_analizi_yorumu}}}}`: Yukarıda verilen sayısal duygu analizi verilerini yorumla. Hangi duyguların baskın olduğunu ve bunun görüşme bağlamında ne anlama gelebileceğini analiz et. Bu yorum en az iki detaylı paragraf olmalıdır. Giriş cümlesi tam olarak şu olmalı: "Görüntü ve ses analiz edilerek kişinin duygu analizi yapılmıştır."
3.  `{{{{dikkat_analizi_yorumu}}}}`: Ekran dışı süre ve bakış sayısı verilerini yorumla. Bu verilerin müşterinin dikkat seviyesi veya odaklanması hakkında ne gibi ipuçları verdiğini açıkla. Bu yorum en az bir detaylı paragraf olmalıdır.
4.  `{{{{genel_degerlendirme_icerik}}}}`: Müşterinin verdiği cevapları, genel tavrını ve analiz sonuçlarını birleştirerek kapsamlı bir değerlendirme yap. Müşterinin güçlü ve gelişime açık yönlerini belirt. Bu bölüm en az üç paragraf olmalıdır.
5.  `{{{{sonuclar_oneriler_icerik}}}}`: Bu bölümü müşteri hakkında genel bir değerlendirme olarak yaz. 1 paragraf kadar olmalı

Önemli Kurallar:
- Üretilen tüm metin **sadece Türkçe** olmalıdır.
- Raporun tonu profesyonel, resmi ve veri odaklı olmalıdır.
- Kullanıcıya yönelik hiçbir not, açıklama veya meta-yorum ekleme.
- Sadece ve sadece aşağıdaki HTML şablonunu doldurarak yanıt ver. Başka hiçbir metin ekleme.

İşte doldurman gereken şablon:
{html_template}
"""

    return prompt_instructions


def create_pdf_from_html(html_content: str) -> io.BytesIO:
    """
    Creates a PDF file from an HTML string using WeasyPrint.
    Uses a base_url to access local files like fonts.
    """
    try:
        pdf_buffer = io.BytesIO()
        html = HTML(string=html_content, base_url=".")
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        print(f"Error creating WeasyPrint PDF: {e}")
        raise ValueError(f"WeasyPrint error occurred while creating PDF: {e}")


# --- FastAPI Endpoint ---


@app.post("/generate-report", summary="PDF Mülakat Raporu Oluştur")
async def generate_report(
    file: UploadFile = File(..., description="Mülakat verilerini içeren CSV dosyası.")
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Hatalı dosya formatı. Lütfen bir .csv dosyası yükleyin.",
        )

    try:
        file_content = await file.read()
        df = pd.read_csv(io.BytesIO(file_content))

        required_columns = [
            "kisi_adi",
            "mulakat_adi",
            "llm_skoru",
            "duygu_mutlu_%",
            "duygu_kizgin_%",
            "duygu_igrenme_%",
            "duygu_korku_%",
            "duygu_uzgun_%",
            "duygu_saskin_%",
            "duygu_dogal_%",
            "ekran_disi_sure_sn",
            "ekran_disi_sayisi",
            "soru",
            "cevap",
            "tip",
            "avg_llm_skoru", # Added avg_llm_skoru to required columns
        ]
        if not all(col in df.columns for col in required_columns):
            missing_cols = [col for col in required_columns if col not in df.columns]
            raise HTTPException(
                status_code=400,
                detail=f"CSV dosyasında eksik sütunlar var: {', '.join(missing_cols)}",
            )

        if df.empty:
            raise HTTPException(status_code=400, detail="CSV dosyası veri içermiyor.")

        row = df.iloc[0]

        current_row_data = {
            "kisi_adi": row["kisi_adi"],
            "mulakat_adi": row["mulakat_adi"],
            "llm_skoru": round(row["llm_skoru"], 2),
            "duygu_mutlu_%": round(row["duygu_mutlu_%"], 2),
            "avg_duygu_mutlu_%": round(row["avg_duygu_mutlu_%"], 2),
            "duygu_kizgin_%": round(row["duygu_kizgin_%"], 2),
            "avg_duygu_kizgin_%": round(row["avg_duygu_kizgin_%"], 2),
            "duygu_igrenme_%": round(row["duygu_igrenme_%"], 2),
            "avg_duygu_igrenme_%": round(row["avg_duygu_igrenme_%"], 2),
            "duygu_korku_%": round(row["duygu_korku_%"], 2),
            "avg_duygu_korku_%": round(row["avg_duygu_korku_%"], 2), 
            "duygu_uzgun_%": round(row["duygu_uzgun_%"], 2),
            "avg_duygu_uzgun_%": round(row["avg_duygu_uzgun_%"], 2),
            "duygu_saskin_%": round(row["duygu_saskin_%"], 2),
            "avg_duygu_saskin_%": round(row["avg_duygu_saskin_%"], 2),
            "duygu_dogal_%": round(row["duygu_dogal_%"], 2),
            "avg_duygu_dogal_%": round(row["avg_duygu_dogal_%"], 2),
            "ekran_disi_sure_sn": round(row["ekran_disi_sure_sn"], 2),
            "avg_ekran_disi_sure_sn": round(row["avg_ekran_disi_sure_sn"], 2),
            "ekran_disi_sayisi": int(row["ekran_disi_sayisi"]),
            "avg_ekran_disi_sayisi": int(row["avg_ekran_disi_sayisi"]),
            "soru_cevap": [{"soru": row["soru"], "cevap": row["cevap"]}],
            "tip": int(row["tip"]),
            "avg_llm_skoru": round(row["avg_llm_skoru"], 2),
        }

        print(f"İşlenen satır tipi: {current_row_data['tip']}")

        formatted_qa_html = format_qa_section(current_row_data["soru_cevap"])

        prompt = generate_llm_prompt(current_row_data, formatted_qa_html)

        response = gemini_model.generate_content(
            prompt, generation_config=genai.types.GenerationConfig(temperature=0.7)
        )

        raw_html_content = (
            response.text.strip().removeprefix("```html").removesuffix("```")
        )

        soup = BeautifulSoup(raw_html_content, "html.parser")

        # Update emotion analysis chart placeholder:
        #   1) Absolute values chart
        #   2) Average difference chart
        bar_chart_placeholder = soup.find(id="bar-chart-placeholder")
        if bar_chart_placeholder:
            # 1) Absolute emotion percentages
            abs_chart_html = create_emotion_charts_html(current_row_data)
            # 2) Candidate–average difference
            diff_chart_html = create_emotion_charts_html_2(current_row_data)

            bar_chart_placeholder.clear()
            bar_chart_placeholder.append(
                BeautifulSoup(abs_chart_html + diff_chart_html, "html.parser")
            )

        logo_base64 = get_image_base64("logo.png")
        if logo_base64:
            logo_src = f"data:image/png;base64,{logo_base64}" if logo_base64 else ""

            # 1) Set header logo
            header_img = soup.select_one("#header_logo img")
            if header_img and logo_src:
                header_img["src"] = logo_src

            # 2) Set watermark logo
            watermark_placeholder = soup.find(id="watermark-placeholder")
            if watermark_placeholder:
                img_tag = soup.new_tag(
                    "img", src=logo_src, alt="Deepwork Logo Filigranı"
                )
                watermark_placeholder.append(img_tag)
        else:
            print("Warning: logo.png not found or could not be read. Watermark not added.")

        # Populate the top-right header with the suitability score
        header_info_div = soup.find(id="header_info")
        if header_info_div:
            llm_score = current_row_data['llm_skoru']
            avg_llm_score = current_row_data['avg_llm_skoru']
            color = get_suitability_color(llm_score, avg_llm_score)
            
            # Directly insert the score and color into the HTML string
            header_info_div.clear()
            header_info_div.append(BeautifulSoup(
                f'<span class="suitability-label">Pozisyona Uygunluk:</span> <span style="color: {color};">%{llm_score:.0f}</span>',
                "html.parser"
            ))


        # If type is 1, completely remove the suitability section from HTML
        if current_row_data["tip"] == 1:
            uygunluk_placeholder = soup.find(text="{{uygunluk_degerlendirmesi_bolumu}}")
            if uygunluk_placeholder:
                uygunluk_placeholder.extract()  # Remove text associated with the placeholder
        else:
            # For type 0, update the suitability section with dynamic color
            uygunluk_placeholder = soup.find(text="{{uygunluk_degerlendirmesi_bolumu}}")
            if uygunluk_placeholder:
                llm_score = current_row_data['llm_skoru']
                avg_llm_score = current_row_data['avg_llm_skoru']
                color = get_suitability_color(llm_score, avg_llm_score)
                
                # Replace the placeholder with the actual suitability section HTML
                suitability_section_html = f"""
                <div class="section">
                    <h2>6) Pozisyona Uygunluk Değerlendirmesi</h2>
                    <p style="font-size: 24px; font-weight: bold; color: {color}; text-align: left;">Pozisyona Uygunluk: %{llm_score:.0f}</p>
                    <p>Adayın genel mülakat performansı, teknik bilgi ve iletişim becerileri, pozisyonun gerektirdiği yetkinliklerle yüksek düzeyde örtüşmektedir. Duygu analizi ve dikkat seviyesi de olumlu bir tablo çizmektedir.</p>
                </div>
                """
                uygunluk_placeholder.replace_with(BeautifulSoup(suitability_section_html, "html.parser"))


        final_html = soup.prettify()

        html_debug_filename = f"{current_row_data['kisi_adi']}_{current_row_data['mulakat_adi']}_Rapor_Debug.html"
        try:
            with open(html_debug_filename, "w", encoding="utf-8") as f:
                f.write(final_html)
            print(f"HTML içeriği '{html_debug_filename}' dosyasına kaydedildi.")
        except IOError as io_err:
            print(f"HTML içeriği kaydedilirken hata oluştu: {io_err}")

        pdf_bytes = create_pdf_from_html(final_html)

        filename = f"{current_row_data['kisi_adi']}_{current_row_data['mulakat_adi']}_Rapor.pdf"
        encoded_filename = urllib.parse.quote(filename)

        return StreamingResponse(
            pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            },
        )

    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Yüklenen CSV dosyası boş.")
    except Exception as e:
        print(f"Beklenmedik bir hata oluştu: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Rapor oluşturulurken sunucuda bir hata oluştu: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
