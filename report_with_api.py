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

# .env dosyasından ortam değişkenlerini yükle
load_dotenv()

# --- FastAPI Uygulama Başlatma ---
app = FastAPI(
    title="Mülakat Raporu Oluşturucu API",
    description="CSV verilerinden tutarlı ve görsel olarak zenginleştirilmiş PDF mülakat raporları oluşturur.",
    version="1.4.0" # Sürüm, PDF oluşturma kütüphanesi WeasyPrint olarak güncellendi
)

# --- Gemini API Yapılandırması ---
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
    )
except KeyError:
    raise RuntimeError("GEMINI_API_KEY ortam değişkeni bulunamadı. Lütfen .env dosyasında ayarlayın.")

# --- Yardımcı Fonksiyonlar ---

def get_image_base64(image_name: str) -> str:
    """
    Belirtilen resim dosyasını (script ile aynı dizinde olduğu varsayılarak) okur ve Base64 kodlu bir dize olarak döndürür.
    """
    script_dir = os.path.dirname(__file__)
    image_path = os.path.join(script_dir, image_name)
    
    print(f"Deniyor: Resim dosyasının yolu: {image_path}")
    
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string
    except FileNotFoundError:
        print(f"Hata: Resim dosyası bulunamadı: {image_path}")
        return ""
    except Exception as e:
        print(f"Resim okunurken hata oluştu: {e}")
        return ""

def create_emotion_charts_html(emotion_data: dict) -> str:
    """
    Her duygu için ayrı, minimalist pasta grafikler oluşturur ve bunları
    HTML tablosu ızgarasında düzenlenmiş olarak döndürür.
    Tasarım, soluk, rahat bir renk paleti kullanır.

    Args:
        emotion_data: Duygu adlarını ve yüzde değerlerini içeren bir sözlük.

    Returns:
        Base64 kodlu PNG grafikleri içeren bir HTML string'i veya veri yoksa bir mesaj.
    """
    labels_map = {
        'duygu_mutlu_%': 'Mutlu', 'duygu_kizgin_%': 'Kızgın', 'duygu_igrenme_%': 'İğrenme',
        'duygu_korku_%': 'Korku', 'duygu_uzgun_%': 'Üzgün', 'duygu_saskin_%': 'Şaşkın',
        'duygu_dogal_%': 'Doğal'
    }
    
    # Soluk, rahat ve sönük bir renk paleti
    colors = {
        'Mutlu': '#d4eac8', 'Kızgın': '#e5b9b5', 'İğrenme': '#d3cdd7',
        'Korku': '#a9b4c2', 'Üzgün': '#b7d0e2', 'Şaşkın': '#fdeac9',
        'Doğal': '#d8d8d8'
    }
    remainder_color = '#f5f5f5' # Grafiğin geri kalanı için çok açık bir gri
    border_color = '#e0e0e0'     # Soluk kenarlık rengi
    
    charts_content_list = []

    emotion_keys_ordered = [
        'duygu_mutlu_%', 'duygu_kizgin_%', 'duygu_igrenme_%', 'duygu_korku_%',
        'duygu_uzgun_%', 'duygu_saskin_%', 'duygu_dogal_%'
    ]

    for key in emotion_keys_ordered:
        if key not in emotion_data:
            continue
            
        emotion_name = labels_map.get(key, "Bilinmeyen")
        value = emotion_data.get(key, 0)
        
        sizes = [value, 100 - value]
        pie_colors = [colors.get(emotion_name, "#cccccc"), remainder_color]

        fig, ax = plt.subplots(figsize=(2.5, 2.5)) 
        
        ax.pie(sizes, colors=pie_colors, startangle=90, 
                         wedgeprops={'edgecolor': border_color, 'linewidth': 0.7})
        
        ax.axis('equal')

        plt.text(0, 0, f'{value:.1f}%', ha='center', va='center', fontsize=12, color='#333')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
        buf.seek(0)
        
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)

        chart_content = f"""
            <img src="data:image/png;base64,{img_base64}" style="width: 140px; height: 140px;" />
            <p style="margin-top: 0px; font-size: 13px; color: #555; font-weight: bold;">{emotion_name}</p>
        """
        charts_content_list.append(chart_content)

    if not charts_content_list:
        return "<p>Görselleştirilecek duygu verisi bulunamadı.</p>"
        
    table_html = '<table style="width: 100%; border-collapse: collapse; margin-top: 0px; margin-bottom: 0px;">'
    columns_per_row = 4
    
    for i in range(0, len(charts_content_list), columns_per_row):
        table_html += '<tr>'
        for j in range(columns_per_row):
            chart_index = i + j
            if chart_index < len(charts_content_list):
                table_html += f'<td style="width: {100/columns_per_row}%; text-align: center; padding: 10px; vertical-align: top;">'
                table_html += charts_content_list[chart_index]
                table_html += '</td>'
            else:
                table_html += f'<td style="width: {100/columns_per_row}%;"></td>'
        table_html += '</tr>'

    table_html += '</table>'
    
    return table_html


def format_qa_section(qa_list: list) -> str:
    """
    Soru-cevap listesini okunabilir bir HTML formatına dönüştürür.
    """
    html = ""
    for item in qa_list:
        html += f"""
        <div class="qa-item" style="margin-bottom: 15px; padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9;">
            <p style="font-weight: bold; color: #34495e;">Soru: {item['soru']}</p>
            <p style="color: #555; margin-top: 5px;">Cevap: {item['cevap']}</p>
        </div>
        """
    return html


def generate_llm_prompt(row_data: dict, formatted_qa_html: str) -> str:
    """
    Verilen tek bir satır verisine ve HTML şablonuna dayanarak Gemini LLM için prompt oluşturur.
    Filigran resmi LLM'e gönderilmez, sonradan eklenecektir.
    """
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
        }}
        h1 {{ 
            color: #2c3e50; 
            text-align: center; 
            border-bottom: 2px solid #3498db; 
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

        /* Filigran Resim Konteyneri */
        .watermark-image-container {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: -1;
            pointer-events: none;
            opacity: 0.08;
            width: 60%;
            max-width: 500px;
            height: auto;
            text-align: center;
        }}
        .watermark-image-container img {{
            width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }}

        /* WeasyPrint için sayfa alt bilgisi */
        @page {{
            margin: 40px 12.5px 70px 12.5px;

            @bottom-center {{
                content: element(footer_content);
                vertical-align: bottom;
                padding-bottom: 10px;
            }}
        }}

        /* Yeni alt bilgi stili */
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
    </style>
</head>
<body>
    <div class="page-footer">
        <div class="footer-divider"></div>
        <div class="footer-company-name">DeepWork Bilişim Teknolojileri A.Ş.</div>
        <div class="footer-contact-info">
            <span>info@hrai.com.tr</span>
            <span>-</span>
            <span>İstanbul Medeniyet Üniversitesi Kuzey Kampüsü Medeniyet Teknopark Kuluçka Merkezi Üsküdar/İstanbul</span>
            <span>-</span>
            <span>+90 216 206 03 10</span>
        </div>
    </div>

    <div class="watermark-image-container" id="watermark-placeholder">
    </div>
    
    <h1>{row_data['kisi_adi']} - Mülakat Değerlendirme Raporu</h1>
    
    <div class="section">
        <h2>1) Genel Bakış</h2>
        <p>{{{{genel_bakis_icerik}}}}</p>
    </div>
    
    <div class="section">
        <h2>2) Analiz</h2>
        <h3>Duygu Analizi:</h3>
        <div id="pie-chart-placeholder">
        </div>
        <p>{{{{duygu_analizi_yorumu}}}}</p>
        
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
</body>
</html>
"""

    if row_data['tip'] == 0:
        prompt_instructions = f"""
Lütfen aşağıdaki HTML şablonunu verilen mülakat verilerine göre doldurarak eksiksiz bir HTML raporu oluştur.
Veriler:
- Aday Adı: {row_data['kisi_adi']}
- Mülakat Adı: {row_data['mulakat_adi']}
- LLM Skoru: {row_data['llm_skoru']}
- Duygu Analizi (%): Mutlu {row_data['duygu_mutlu_%']}, Kızgın {row_data['duygu_kizgin_%']}, İğrenme {row_data['duygu_igrenme_%']}, Korku {row_data['duygu_korku_%']}, Üzgün {row_data['duygu_uzgun_%']}, Şaşkın {row_data['duygu_saskin_%']}, Doğal {row_data['duygu_dogal_%']}
- Dikkat Analizi: Ekran Dışı Süre {row_data['ekran_disi_sure_sn']} sn, Ekran Dışı Bakış Sayısı {row_data['ekran_disi_sayisi']}

Doldurulacak Alanlar İçin Talimatlar:
1.  `{{{{genel_bakis_icerik}}}}`: Adayın genel performansını, iletişim becerilerini ve mülakatın genel seyrini özetleyen, en az iki paragraftan oluşan detaylı bir giriş yaz.
2.  `{{{{duygu_analizi_yorumu}}}}`: Yukarıda verilen sayısal duygu analizi verilerini yorumla. Hangi duyguların baskın olduğunu ve bunun mülakat bağlamında ne anlama gelebileceğini analiz et. Bu yorum en az iki detaylı paragraf olmalıdır.
3.  `{{{{dikkat_analizi_yorumu}}}}`: Ekran dışı süre ve bakış sayısı verilerini yorumla. Bu verilerin adayın dikkat seviyesi veya odaklanması hakkında ne gibi ipuçları verdiğini açıkla. Bu yorum en az bir detaylı paragraf olmalıdır.
4.  `{{{{genel_degerlendirme_icerik}}}}`: Adayın verdiği cevapları, genel tavrını ve analiz sonuçlarını birleştirerek kapsamlı bir değerlendirme yap. Adayın güçlü ve gelişime açık yönlerini belirt. Bu bölüm en az üç paragraf olmalıdır.
5.  `{{{{sonuclar_oneriler_icerik}}}}`: Bu bölümü **sadece İnsan Kaynakları profesyonellerine yönelik** olarak yaz. Adayın pozisyona uygunluğu hakkında net bir sonuca var. İşe alım kararı için somut önerilerde bulun. Adaya yönelik bir dil kullanma. Bu bölüm en az iki paragraf olmalıdır.

Önemli Kurallar:
- Üretilen tüm metin **sadece Türkçe** olmalıdır.
- Raporun tonu profesyonel, resmi ve veri odaklı olmalıdır.
- Kullanıcıya yönelik hiçbir not, açıklama veya meta-yorum ekleme.
- Sadece ve sadece aşağıdaki HTML şablonunu doldurarak yanıt ver. Başka hiçbir metin ekleme.

İşte doldurman gereken şablon:
{html_template}
"""

    elif row_data['tip'] == 1:
        prompt_instructions = f"""
Lütfen aşağıdaki HTML şablonunu, sağlanan müşteri röportajı verilerini kullanarak eksiksiz ve profesyonel bir rapora dönüştür. Bu rapor, müşterinin röportajdaki performansını objektif ve veri odaklı bir şekilde analiz etmelidir.

Verilen Röportaj Verileri:
- Müşteri Adı: {row_data['kisi_adi']}
- Röportaj Adı: {row_data['mulakat_adi']}
- Duygu Analizi Yüzdeleri: Mutlu %{row_data['duygu_mutlu_%']}, Kızgın %{row_data['duygu_kizgin_%']}, İğrenme %{row_data['duygu_igrenme_%']}, Korku %{row_data['duygu_korku_%']}, Üzgün %{row_data['duygu_uzgun_%']}, Şaşkın %{row_data['duygu_saskin_%']}, Doğal %{row_data['duygu_dogal_%']}
- Dikkat Analizi Verileri: Toplam Ekran Dışı Süre {row_data['ekran_disi_sure_sn']} saniye, Toplam Ekran Dışı Bakış Sayısı {row_data['ekran_disi_sayisi']}

HTML Şablonundaki Yer Tutucuların Doldurulması İçin Detaylı Talimatlar:

1.  `{{{{genel_bakis_icerik}}}}`: Müşterinin röportaj sırasındaki genel davranışını, sergilediği iletişim becerilerini ve röportajın genel akışını özetleyen **en az iki paragraftan** oluşan kapsamlı bir giriş yazısı oluştur. Bu bölümde, müşterinin mülakat sürecindeki etkileşimi ve duruşu hakkında genel bir perspektif sunulmalıdır.

2.  `{{{{duygu_analizi_yorumu}}}}`: Yukarıda belirtilen sayısal duygu analizi yüzdelerini detaylı bir şekilde yorumla. Hangi duyguların röportaj boyunca **baskın olduğunu** belirle ve bu baskın duyguların röportajın bağlamı ve müşterinin yanıtları üzerindeki potansiyel etkilerini analiz et. Örneğin, yüksek bir 'Mutlu' yüzdesinin olumlu bir tutuma işaret edebileceği veya yüksek 'Kızgın' yüzdesinin stresli bir soruya tepki olabileceği gibi çıkarımlar yap. Bu yorum **en az iki detaylı paragraf** olmalıdır.

3.  `{{{{dikkat_analizi_yorumu}}}}`: Sağlanan ekran dışı süre ve bakış sayısı verilerini analiz et. Bu metriklerin müşterinin röportaj sırasındaki **dikkat seviyesi**, odaklanma yeteneği veya olası dağılmalar hakkında ne gibi göstergeler sunduğunu açıkla. Verilerin müşterinin ilgi düzeyini veya konsantrasyonunu nasıl yansıttığına dair çıkarımlar yap. Bu yorum **en az bir detaylı paragraf** olmalıdır.

4.  `{{{{genel_degerlendirme_icerik}}}}`: Müşterinin röportajda verdiği cevapları, genel tavrını, duygu analizi ve dikkat analizi sonuçlarını **entegre ederek** kapsamlı bir genel değerlendirme sun. Müşterinin **güçlü yönlerini** ve **gelişime açık alanlarını** açıkça belirt. Bu değerlendirme, mülakatın bütünsel bir resmini sunmalı ve müşterinin genel uygunluğunu veya performansını özetlemelidir. Bu bölüm **en az üç paragraf** olmalıdır.

5.  `{{{{sonuclar_oneriler_icerik}}}}`: Bu bölümü, röportajın genel bir özeti ve gelecekteki olası adımlar veya dikkate alınması gereken noktalar hakkında bir değerlendirme olarak yaz. Müşteri hakkında **genel bir sonuç ifadesi** içermeli ve **yaklaşık 1 paragraf** uzunluğunda olmalıdır.

**Rapor Oluşturma Kuralları:**

* Üretilen tüm metin **sadece Türkçe** olmalıdır.
* Raporun genel tonu **profesyonel, objektif, resmi ve veri odaklı** olmalıdır. Duygusal veya öznel ifadelerden kaçınılmalıdır.
* Rapor, bir insana veya kullanıcıya yönelik **hiçbir doğrudan not, açıklama, meta-yorum veya giriş/kapanış cümlesi** içermemelidir. Sadece HTML şablonunun içindeki içerik doldurulmalıdır.
* Yalnızca ve yalnızca yukarıdaki HTML şablonunu doldurarak yanıt ver. Başka hiçbir ek metin, başlık veya açıklama ekleme.
* HTML içeriği, okunabilirliği ve ayrıştırmayı kolaylaştırmak için temiz ve düzenli olmalıdır.
* Kesinlikle Mülakat dan aday dan bahsetme bu rapor müşteri için hazırlanıyor.

İşte doldurman gereken şablon:
{html_template}
"""
    
    return prompt_instructions


def create_pdf_from_html(html_content: str) -> io.BytesIO:
    """
    Bir HTML dizesinden WeasyPrint kullanarak bir PDF dosyası oluşturur.
    Fontlar gibi yerel dosyalara erişim için bir base_url kullanır.
    """
    try:
        pdf_buffer = io.BytesIO()
        html = HTML(string=html_content, base_url='.') 
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        print(f"WeasyPrint PDF oluşturulurken hata: {e}")
        raise ValueError(f"PDF oluşturulurken WeasyPrint hatası oluştu: {e}")


# --- FastAPI Endpoint'i ---

@app.post("/generate-report", summary="PDF Mülakat Raporu Oluştur")
async def generate_report(file: UploadFile = File(..., description="Mülakat verilerini içeren CSV dosyası.")):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Hatalı dosya formatı. Lütfen bir .csv dosyası yükleyin.")

    try:
        file_content = await file.read()
        df = pd.read_csv(io.BytesIO(file_content))

        required_columns = [
            'kisi_adi', 'mulakat_adi', 'llm_skoru', 'duygu_mutlu_%', 'duygu_kizgin_%',
            'duygu_igrenme_%', 'duygu_korku_%', 'duygu_uzgun_%', 'duygu_saskin_%',
            'duygu_dogal_%', 'ekran_disi_sure_sn', 'ekran_disi_sayisi', 'soru', 'cevap', 'tip'
        ]
        if not all(col in df.columns for col in required_columns):
            missing_cols = [col for col in required_columns if col not in df.columns]
            raise HTTPException(status_code=400, detail=f"CSV dosyasında eksik sütunlar var: {', '.join(missing_cols)}")

        # --- DEĞİŞİKLİK BAŞLANGICI ---
        # CSV'deki her satır için bir rapor oluşturmak üzere DataFrame'i satır satır dolaşıyoruz
        # Ancak, mevcut yapı tek bir rapor oluşturuyor. Eğer birden fazla rapor oluşturulacaksa
        # bu endpoint'in yanıt mekanizması da değişmelidir (örneğin, bir zip dosyası döndürme).
        # Şimdilik, sadece ilk satırı işleyecek şekilde bırakıyorum, ancak kod her satırı
        # potansiyel olarak işleyebilir hale getirildi.
        
        # Eğer gerçekten her satır için ayrı PDF istiyorsanız, bu kısmı bir döngü içine alıp
        # her iterasyonda PDF oluşturmanız ve bunları bir liste veya zip dosyası olarak döndürmeniz gerekir.
        # Bu senaryoda, API yanıtı StreamingResponse ile tek bir PDF döndürdüğü için
        # şimdilik yalnızca ilk satırı işleyip tek bir PDF oluşturacak şekilde bırakıyoruz.
        
        if df.empty:
            raise HTTPException(status_code=400, detail="CSV dosyası veri içermiyor.")

        # Sadece ilk satırı alıyoruz, çünkü endpoint tek bir PDF döndürüyor.
        # Eğer her satır için ayrı rapor isteniyorsa, bu mantığın dışına çıkılır.
        row = df.iloc[1] # İlk satırı al

        # Satırdaki verileri doğrudan kullanıyoruz, gruplandırma yok
        current_row_data = {
            'kisi_adi': row['kisi_adi'],
            'mulakat_adi': row['mulakat_adi'],
            'llm_skoru': round(row['llm_skoru'], 2),
            'duygu_mutlu_%': round(row['duygu_mutlu_%'], 2),
            'duygu_kizgin_%': round(row['duygu_kizgin_%'], 2),
            'duygu_igrenme_%': round(row['duygu_igrenme_%'], 2),
            'duygu_korku_%': round(row['duygu_korku_%'], 2),
            'duygu_uzgun_%': round(row['duygu_uzgun_%'], 2),
            'duygu_saskin_%': round(row['duygu_saskin_%'], 2),
            'duygu_dogal_%': round(row['duygu_dogal_%'], 2),
            'ekran_disi_sure_sn': round(row['ekran_disi_sure_sn'], 2),
            'ekran_disi_sayisi': int(row['ekran_disi_sayisi']),
            'soru_cevap': [{'soru': row['soru'], 'cevap': row['cevap']}], # Soru-cevap tek bir satırdan geliyorsa
            'tip': int(row['tip'])
        }
        
        print(f"İşlenen satır tipi: {current_row_data['tip']}")
        
        # LLM prompt'u ve diğer fonksiyonlar artık 'current_row_data' ile çalışacak
        formatted_qa_html = format_qa_section(current_row_data['soru_cevap'])

        prompt = generate_llm_prompt(current_row_data, formatted_qa_html)
        
        response = gemini_model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.7))
        
        raw_html_content = response.text.strip().removeprefix("```html").removesuffix("```")
                        
        soup = BeautifulSoup(raw_html_content, "html.parser")
        
        placeholders_to_remove = [
            "{{genel_bakis_icerik}}",
            "{{duygu_analizi_yorumu}}",
            "{{dikkat_analizi_yorumu}}",
            "{{genel_degerlendirme_icerik}}",
            "{{sonuclar_oneriler_icerik}}"
        ]

        for p_tag in soup.find_all('p'):
            if p_tag.string:
                original_text = p_tag.string.strip()
                for placeholder in placeholders_to_remove:
                    if original_text.startswith(placeholder):
                        p_tag.string.replace_with(original_text[len(placeholder):].strip())
                        break
        
        pie_chart_placeholder = soup.find(id="pie-chart-placeholder")
        if pie_chart_placeholder:
            emotion_charts_grid_html = create_emotion_charts_html(current_row_data) # 'current_row_data' kullanıldı
            pie_chart_placeholder.clear()
            pie_chart_placeholder.append(BeautifulSoup(emotion_charts_grid_html, "html.parser"))
        
        logo_base64 = get_image_base64("logo.png") 
        if logo_base64:
            logo_src = f"data:image/png;base64,{logo_base64}"
            watermark_placeholder = soup.find(id="watermark-placeholder")
            if watermark_placeholder:
                img_tag = soup.new_tag("img", src=logo_src, alt="Deepwork Logo Filigranı")
                watermark_placeholder.append(img_tag)
        else:
            print("Uyarı: logo.png bulunamadı veya okunamadı. Filigran eklenemedi.")

        final_html = soup.prettify()

        html_debug_filename = f"{current_row_data['kisi_adi']}_{current_row_data['mulakat_adi']}_Rapor_Debug.html" # Dosya adı güncellendi
        try:
            with open(html_debug_filename, "w", encoding="utf-8") as f:
                f.write(final_html)
            print(f"HTML içeriği '{html_debug_filename}' dosyasına kaydedildi.")
        except IOError as io_err:
            print(f"HTML içeriği kaydedilirken hata oluştu: {io_err}")

        pdf_bytes = create_pdf_from_html(final_html)

        filename = f"{current_row_data['kisi_adi']}_{current_row_data['mulakat_adi']}_Rapor.pdf" # Dosya adı güncellendi
        encoded_filename = urllib.parse.quote(filename)

        return StreamingResponse(
            pdf_bytes, media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )

    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Yüklenen CSV dosyası boş.")
    except Exception as e:
        print(f"Beklenmedik bir hata oluştu: {e}")
        raise HTTPException(status_code=500, detail=f"Rapor oluşturulurken sunucuda bir hata oluştu: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)