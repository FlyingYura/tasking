from docx import Document
import sys

doc = Document(r'c:\Users\proko\Downloads\Telegram Desktop\нак272.docx')
with open('reprimand_content.txt', 'w', encoding='utf-8') as f:
    for i, p in enumerate(doc.paragraphs[:50]):
        f.write(f"{i}: {p.text}\n")
    for table in doc.tables:
        f.write("\n--- TABLE ---\n")
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            f.write(" | ".join(cells) + "\n")
print("Content written to reprimand_content.txt")
