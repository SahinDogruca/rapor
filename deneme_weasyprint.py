from weasyprint import HTML
import io

simple_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test PDF</title>
    <style>
        body { font-family: sans-serif; }
        h1 { color: blue; }
    </style>
</head>
<body>
    <h1>Merhaba Dünya!</h1>
    <p>Bu bir WeasyPrint testidir.</p>
</body>
</html>
"""

try:
    pdf_buffer = io.BytesIO()
    HTML(string=simple_html).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)

    with open("test_output.pdf", "wb") as f:
        f.write(pdf_buffer.read())
    print("test_output.pdf başarıyla oluşturuldu.")
except Exception as e:
    print(f"Test PDF oluşturulurken hata: {e}")