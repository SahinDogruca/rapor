import os
import io
import base64
from weasyprint import HTML

def get_image_base64(image_path: str) -> str:
    """
    Belirtilen resim dosyasını okur ve Base64 kodlu bir dize olarak döndürür.
    """
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

def create_watermarked_html(logo_base64: str) -> str:
    """
    Base64 kodlu logo ile filigranlı bir HTML sayfası oluşturur.
    """
    logo_src = f"data:image/png;base64,{logo_base64}" if logo_base64 else ""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Filigranlı Logo Sayfası</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            height: 100vh; /* Sayfanın tam yüksekliğini kaplaması için */
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden; /* Kaydırma çubuklarını gizle */
            position: relative;
        }}

        /* Filigran Resim Konteyneri */
        .watermark-image-container {{
            position: fixed; /* Sabit konumlandırma */
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-45deg); /* Ortala ve çapraz döndür */
            z-index: -1; /* İçeriğin arkasında kalması için */
            pointer-events: none; /* Metin seçimini engelle */
            opacity: 0.08; /* Çok soluk */
            width: 60%; /* Filigran genişliği sayfanın %60'ı */
            max-width: 500px; /* Maksimum genişlik */
            height: auto; /* Oranları koru */
            text-align: center; /* İçindeki resmi ortala */
        }}
        .watermark-image-container img {{
            width: 100%;
            height: auto;
            display: block; /* Resmi blok element yap */
            margin: 0 auto; /* Resmi yatayda ortala */
        }}
    </style>
</head>
<body>
    <div class="watermark-image-container">
        <img src="{logo_src}" alt="Filigran Logo" />
    </div>
    <!-- Buraya başka içerik eklenebilir, filigran arkasında kalacaktır -->
    <p style="font-size: 24px; color: #555; text-align: center;">Bu bir test sayfasıdır.</p>
</body>
</html>
"""
    return html_content

def create_pdf_from_html(html_content: str, output_path: str) -> None:
    """
    Bir HTML dizesinden WeasyPrint kullanarak bir PDF dosyası oluşturur.
    """
    try:
        HTML(string=html_content).write_pdf(output_path)
        print(f"PDF başarıyla oluşturuldu: {output_path}")
    except Exception as e:
        print(f"PDF oluşturulurken hata oluştu: {e}")

if __name__ == "__main__":
    logo_file_name = "logo.png" # logo.png dosyasının bu Python scripti ile aynı dizinde olduğunu varsayarız.
    output_pdf_name = "watermarked_logo_page.pdf"

    # Logo dosyasını Base64'e dönüştür
    logo_base64_string = get_image_base64(logo_file_name)

    if logo_base64_string:
        # Filigranlı HTML içeriğini oluştur
        html_output = create_watermarked_html(logo_base64_string)
        
        # HTML'i PDF'e dönüştür
        create_pdf_from_html(html_output, output_pdf_name)
    else:
        print("Filigran için logo resmi bulunamadı veya okunamadı. PDF oluşturulamadı.")

