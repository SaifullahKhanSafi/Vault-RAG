import io,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pypdf import PdfReader,PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject
from test_support import fixture_pdf
from pdf_extract import extract_pages
from history_access import evidence_visible,redact_messages

class EnterpriseTests(unittest.TestCase):
    def test_table_structure_and_page_provenance(self):
        reader=PdfReader(io.BytesIO(fixture_pdf()));writer=PdfWriter();writer.add_page(reader.pages[0])
        content=DecodedStreamObject()
        content.set_data(b'0 0 0 RG 1 w 40 300 m 300 300 l S 40 330 m 300 330 l S 40 360 m 300 360 l S 40 300 m 40 360 l S 170 300 m 170 360 l S 300 300 m 300 360 l S BT /F1 11 Tf 50 340 Td (Item) Tj 130 0 Td (Value) Tj ET BT /F1 11 Tf 50 310 Td (Retention) Tj 130 0 Td (90 days) Tj ET')
        writer.pages[0][NameObject('/Contents')]=writer._add_object(content)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'table.pdf'
            with path.open('wb') as stream:writer.write(stream)
            pages=extract_pages(path)
            self.assertEqual(pages[0].metadata['page'],1)
            self.assertIn('Retention | 90 days',pages[0].page_content)
            self.assertIn('Table:',pages[0].page_content)

    def test_revoked_evidence_is_redacted(self):
        conn=Mock();conn.execute.return_value.fetchall.return_value=[]
        messages=[{'role':'assistant','content':'Sensitive fact','sources':[{'document_id':'00000000-0000-0000-0000-000000000001'}]}]
        result=redact_messages(conn,messages)
        self.assertNotIn('Sensitive fact',result[0]['content']);self.assertEqual(result[0]['sources'],[])
        self.assertTrue(evidence_visible(conn,[]))

if __name__=='__main__':unittest.main()
