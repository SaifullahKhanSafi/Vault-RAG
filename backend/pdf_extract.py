"""Bounded PDF extraction with ruled-table structure and per-page OCR fallback."""
import os
from pathlib import Path
import subprocess
import tempfile
from pypdf import PdfReader
from langchain_core.documents import Document

def ocr_page(path,number):
    with tempfile.TemporaryDirectory(prefix='rag-ocr-') as directory:
        prefix=str(Path(directory)/'page')
        subprocess.run(['pdftoppm','-f',str(number),'-l',str(number),'-scale-to','2400','-singlefile','-png',str(path),prefix],check=True,timeout=40,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        result=subprocess.run(['tesseract',prefix+'.png','stdout','-l',os.getenv('OCR_LANGUAGE','eng'),'--psm','3'],check=True,timeout=50,capture_output=True,text=True)
        return result.stdout

def extract_pages(path):
    import pdfplumber
    reader=PdfReader(path)
    if reader.is_encrypted:raise ValueError('Password-protected PDFs are not supported.')
    if len(reader.pages)>1000:raise ValueError('PDF exceeds the 1000-page limit.')
    pages=[];total=0;ocr_count=0
    with pdfplumber.open(path) as structured:
        for number,page in enumerate(reader.pages,1):
            text=page.extract_text() or ''
            method='native'
            # Blank vector pages remain blank; only raster pages need OCR.
            if len(text.strip())<30 and len(page.images)>0 and os.getenv('OCR_ENABLED','true').lower()=='true':
                ocr_count+=1
                if ocr_count>int(os.getenv('OCR_MAX_PAGES','50')):raise ValueError('PDF exceeds the OCR page limit. Split the document into smaller files.')
                text=ocr_page(path,number)
                method='ocr'
            body=text
            tables=structured.pages[number-1].extract_tables()
            for table in tables:
                rows=[' | '.join(str(cell or '').replace('\n',' ') for cell in row) for row in table]
                if rows:text+='\n\nTable:\n'+'\n'.join(rows)
            total+=len(text)
            if total>5_000_000:raise ValueError('PDF exceeds the extracted text limit.')
            pages.append(Document(page_content=text,metadata={'page':number,'page_label':reader.page_labels[number-1],
                          'extraction_method':method,'raw_text':body,'tables':tables}))
    return pages
