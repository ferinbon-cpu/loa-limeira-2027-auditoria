import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pilot_camara import classify_observed_url, extract_links, HOST  # noqa: E402

SOURCE = "https://consulta.limeira.sp.leg.br/Documentos/Documento/439497"


class TestOfficialMetadataPilot(unittest.TestCase):
    def test_file_link_exact_id(self):
        value = classify_observed_url("/arquivo?Id=601648", SOURCE)
        self.assertEqual(value[0], "arquivo")
        self.assertEqual(value[1], "601648")

    def test_document_link(self):
        value = classify_observed_url("/Documentos/Documento/439564", SOURCE)
        self.assertEqual(value[:2], ("documento", "439564"))

    def test_external_domain_rejected(self):
        self.assertIsNone(classify_observed_url("https://example.org/arquivo?Id=601648", SOURCE))
        self.assertIsNone(classify_observed_url("javascript:alert(1)", SOURCE))
        self.assertIsNone(classify_observed_url("http://" + HOST + "/arquivo?Id=1", SOURCE))

    def test_missing_or_ambiguous_id_rejected(self):
        self.assertIsNone(classify_observed_url("/arquivo?Id=notnumeric", SOURCE))
        self.assertIsNone(classify_observed_url("/arquivo?Id=1&Id=2", SOURCE))
        self.assertIsNone(classify_observed_url("/arquivo", SOURCE))

    def test_extraction_dedup_and_no_invented_urls(self):
        html = """
        <html><body>
          <a href="/arquivo?Id=601648">Plano de Trabalho</a>
          <a href="/arquivo?Id=601648">Duplicado</a>
          <a href="/Documentos/Documento/439564">Emenda 110</a>
          <span>Id: 9999999999</span>
          <a href="https://evil.example/arquivo?Id=4">Externo</a>
        </body></html>
        """
        rows = extract_links(html, SOURCE)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["id"] for r in rows}, {"601648", "439564"})
        self.assertIn("Plano de Trabalho", rows[0]["nome_exibido"])


if __name__ == "__main__":
    unittest.main()
