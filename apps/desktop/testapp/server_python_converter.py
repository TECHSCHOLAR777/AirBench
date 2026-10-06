"""
AirBench Sovereign Deliverable Python Conversion Engine
Provides high-fidelity format parsing and extraction for:
- PDF (via PyMuPDF/fitz & pypdf)
- PPTX (via python-pptx)
- DOCX (via python-docx)
- XLSX (via openpyxl)
"""

import sys
import os
import json

def extract_pdf(file_path):
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    pages_data = []
    
    for i, page in enumerate(doc):
        page_text = page.get_text()
        tables_data = []
        try:
            tabs = page.find_tables()
            for tab in tabs:
                df = tab.extract()
                if df and len(df) > 0:
                    headers = [str(c or "").strip() for c in df[0]]
                    rows = [[str(c or "").strip() for c in r] for r in df[1:]]
                    tables_data.append({"headers": headers, "rows": rows})
        except Exception as e:
            pass
            
        pages_data.append({
            "pageNumber": i + 1,
            "text": page_text,
            "tables": tables_data
        })
    doc.close()
    return {"format": "pdf", "pages": pages_data}

def extract_pptx(file_path):
    from pptx import Presentation
    prs = Presentation(file_path)
    slides_data = []
    
    for i, slide in enumerate(prs.slides):
        title = ""
        paragraphs = []
        bullets = []
        tables_data = []
        
        for shape in slide.shapes:
            if shape.has_table:
                table = shape.table
                table_rows = []
                for row in table.rows:
                    table_rows.append([cell.text.strip() for cell in row.cells])
                if len(table_rows) > 0:
                    tables_data.append({
                        "headers": table_rows[0],
                        "rows": table_rows[1:] if len(table_rows) > 1 else []
                    })
            elif shape.has_text_frame:
                for p in shape.text_frame.paragraphs:
                    p_text = p.text.strip()
                    if not p_text:
                        continue
                    if shape == slide.shapes.title or (not title and len(p_text) < 80):
                        if not title:
                            title = p_text
                            continue
                    if p.level > 0 or p_text.startswith(("-", "•", "*")):
                        bullets.append(p_text.lstrip("-•* "))
                    else:
                        paragraphs.append(p_text)
                        
        slides_data.append({
            "slideNumber": i + 1,
            "title": title or f"Slide {i + 1}",
            "paragraphs": paragraphs,
            "bullets": bullets,
            "tables": tables_data
        })
        
    return {"format": "pptx", "slides": slides_data}

def extract_docx(file_path):
    import docx
    doc = docx.Document(file_path)
    elements = []
    tables_data = []
    
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        style_name = (p.style.name or "").lower()
        if "heading 1" in style_name or "title" in style_name:
            elements.append({"type": "h1", "text": t})
        elif "heading 2" in style_name:
            elements.append({"type": "h2", "text": t})
        elif "heading 3" in style_name:
            elements.append({"type": "h3", "text": t})
        elif "list" in style_name or "bullet" in style_name:
            elements.append({"type": "bullet", "text": t})
        else:
            elements.append({"type": "paragraph", "text": t})
            
    for table in doc.tables:
        t_rows = []
        for row in table.rows:
            t_rows.append([cell.text.strip() for cell in row.cells])
        if len(t_rows) > 0:
            tables_data.append({
                "headers": t_rows[0],
                "rows": t_rows[1:] if len(t_rows) > 1 else []
            })
            elements.append({
                "type": "table",
                "headers": t_rows[0],
                "rows": t_rows[1:] if len(t_rows) > 1 else []
            })
            
    return {"format": "docx", "elements": elements, "tables": tables_data}

def extract_xlsx(file_path):
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheets_data = []
    
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows = []
        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                rows.append([str(c) if c is not None else "" for c in row])
        if rows:
            headers = rows[0]
            data_rows = rows[1:]
            sheets_data.append({
                "sheetName": sheet_name,
                "headers": headers,
                "rows": data_rows
            })
    return {"format": "xlsx", "sheets": sheets_data}

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python server_python_converter.py <command> <file_path>"}))
        sys.exit(1)
        
    cmd = sys.argv[1]
    file_path = sys.argv[2]
    
    if not os.path.exists(file_path):
        print(json.dumps({"error": f"File not found: {file_path}"}))
        sys.exit(1)
        
    try:
        if cmd == "extract-pdf":
            res = extract_pdf(file_path)
        elif cmd == "extract-pptx":
            res = extract_pptx(file_path)
        elif cmd == "extract-docx":
            res = extract_docx(file_path)
        elif cmd == "extract-xlsx":
            res = extract_xlsx(file_path)
        else:
            res = {"error": f"Unknown command: {cmd}"}
            
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
