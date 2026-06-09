import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from file_converter import extract_text_from_file, strip_tags

class TestFileConverter(unittest.TestCase):

    def test_text_and_md_decoding(self):
        text_content = "Hello World\n1. Run `ls`"
        # Test UTF-8 decoding
        res1 = extract_text_from_file(text_content.encode('utf-8'), 'runbook.md')
        self.assertEqual(res1, text_content)

        # Test latin-1 fallback
        res2 = extract_text_from_file(text_content.encode('latin-1'), 'runbook.txt')
        self.assertEqual(res2, text_content)

        # Test unknown extension fallback
        res3 = extract_text_from_file(text_content.encode('utf-8'), 'runbook.unknown')
        self.assertEqual(res3, text_content)

    def test_json_parsing(self):
        json_data = {"name": "Test Runbook", "steps": [1, 2, 3]}
        raw_bytes = json_data_bytes = b'{"name": "Test Runbook", "steps": [1, 2, 3]}'
        res = extract_text_from_file(raw_bytes, 'runbook.json')
        self.assertIn("Test Runbook", res)
        self.assertIn('"steps": [', res)

    def test_yaml_parsing(self):
        yaml_content = "name: Test Runbook\nsteps:\n  - 1\n  - 2"
        res = extract_text_from_file(yaml_content.encode('utf-8'), 'runbook.yaml')
        self.assertIn("Test Runbook", res)
        
        res_yml = extract_text_from_file(yaml_content.encode('utf-8'), 'runbook.yml')
        self.assertIn("Test Runbook", res_yml)

    def test_csv_parsing(self):
        csv_content = "step,command\n1,df -h\n2,free -m"
        res = extract_text_from_file(csv_content.encode('utf-8'), 'runbook.csv')
        self.assertIn("step | command", res)
        self.assertIn("1 | df -h", res)
        self.assertIn("2 | free -m", res)

    def test_html_parsing(self):
        html_content = "<html><body><h1>Runbook</h1><p>1. Check space: `df -h`</p></body></html>"
        res = extract_text_from_file(html_content.encode('utf-8'), 'runbook.html')
        self.assertEqual(res.strip(), "Runbook1. Check space: `df -h`")

    @patch('file_converter.pypdf')
    def test_pdf_parsing_mocked(self, mock_pypdf):
        # Configure mock_pypdf
        mock_reader = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PDF Page Text"
        mock_reader.pages = [mock_page]

        res = extract_text_from_file(b"dummy pdf bytes", 'runbook.pdf')
        self.assertEqual(res, "PDF Page Text")
        mock_pypdf.PdfReader.assert_called_once()

    @patch('file_converter.docx')
    def test_docx_parsing_mocked(self, mock_docx):
        mock_doc = MagicMock()
        mock_docx.Document.return_value = mock_doc
        
        mock_paragraph = MagicMock()
        mock_paragraph.text = "Docx Paragraph Text"
        mock_doc.paragraphs = [mock_paragraph]

        mock_table = MagicMock()
        mock_cell = MagicMock()
        mock_cell.text = "Cell Text"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell]
        mock_table.rows = [mock_row]
        mock_doc.tables = [mock_table]

        res = extract_text_from_file(b"dummy docx bytes", 'runbook.docx')
        self.assertEqual(res, "Docx Paragraph Text\nCell Text")
        mock_docx.Document.assert_called_once()

    @patch('file_converter.openpyxl')
    def test_xlsx_parsing_mocked(self, mock_openpyxl):
        mock_wb = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        
        mock_sheet = MagicMock()
        mock_sheet.title = "Sheet1"
        mock_sheet.iter_rows.return_value = [("Step 1", "df -h", None)]
        mock_wb.worksheets = [mock_sheet]

        res = extract_text_from_file(b"dummy xlsx bytes", 'runbook.xlsx')
        self.assertIn("--- Sheet: Sheet1 ---", res)
        self.assertIn("Step 1 | df -h | ", res)
        mock_openpyxl.load_workbook.assert_called_once()


if __name__ == '__main__':
    unittest.main()
