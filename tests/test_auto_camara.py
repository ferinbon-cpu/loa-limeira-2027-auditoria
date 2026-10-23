import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import auto_camara as a  # noqa


class TestAutonomousCrawler(unittest.TestCase):
    def test_discover_official_emendas_and_files(self):
        state = a.new_state()
        a.add_page(state, "437627", "PL", "official", "PRINCIPAL")
        main = state["pages"]["437627"]
        html = (
            '<a href="/Documentos/Documento/439497">Emenda Nº 65 ao Projeto de Lei</a>'
            '<a href="/Documentos/Documento/439498">Emenda Nº 66 ao Projeto de Lei</a>'
            '<a href="/Documentos/Documento/1">Início</a>'
            '<a href="https://elsewhere.example/arquivo?Id=123">Outro domínio</a>'
            '<a href="/arquivo?Id=601648">Anexo</a>'
        )
        count, found, newpages = a.extract(state, html, main)
        self.assertEqual((count, found, newpages), (1, 1, 2))
        self.assertEqual(set(state["pages"]), {"437627", "439497", "439498"})
        self.assertEqual(set(state["files"]), {"601648"})
        self.assertEqual(state["files"]["601648"]["e_novo_dentre_336"], "NAO_AFERIDO")

    def test_dedup_sources_and_sanitize_public_label(self):
        state = a.new_state()
        page = {"url": a.MAIN_ID and f"https://{a.HOST}/Documentos/Documento/439497",
                "id": "439497", "tipo": "EMENDA"}
        markup = '<a href="/arquivo?Id=602278">cpf: 123.456.789-09 a@b.com</a>'
        a.extract(state, markup, page)
        page["id"] = "439498"
        a.extract(state, markup, page)
        self.assertEqual(len(state["files"]), 1)
        f = state["files"]["602278"]
        self.assertNotIn("123.456.789-09", f["rotulo_publico"])
        self.assertNotIn("a@b.com", f["rotulo_publico"])
        self.assertEqual(f["fontes"], ["439497", "439498"])

    def test_restricted_status_stops(self):
        page = {"status": "PENDENTE", "tentativas": 1, "tipo": "EMENDA", "proxima_tentativa": ""}
        a.page_error(page, "HTTP_403", 403)
        self.assertFalse(a.due(page, datetime.now(timezone.utc)))

    def test_http_429_sets_global_pause_and_stops_requests(self):
        from urllib.error import HTTPError
        state = a.new_state()
        a.add_page(state, "437627", "PL", "official", "PRINCIPAL")
        a.add_page(state, "439497", "Emenda", "437627", "PILOTO")
        with patch.object(a, "fetch_public_html", side_effect=HTTPError(
                "https://consulta.limeira.sp.leg.br/Documentos/Documento/437627",
                429, "Rate Limit", {}, None)) as mock_get:
            result = a.crawl(state, limit=2, delay=0)
            self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "PAUSA_HTTP_429")
        self.assertIn("pause_until", state)
        self.assertEqual(a.crawl(state, limit=2, delay=0), [])

    def test_transient_status_has_cooldown(self):
        page = {"status": "PENDENTE", "tentativas": 1, "tipo": "EMENDA", "proxima_tentativa": ""}
        a.page_error(page, "HTTP_502", 502)
        self.assertFalse(a.due(page, datetime.now(timezone.utc)))
        self.assertTrue(a.due(page, datetime.now(timezone.utc) + timedelta(days=2)))

    def test_incremental_state_serialization(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            state = a.new_state()
            a.add_page(state, "437627", "PL", "source", "PRINCIPAL")
            a.publish(state, p, [])
            reloaded = a.load(p / "estado.json")
            self.assertEqual(set(reloaded["pages"]), {"437627"})
            self.assertEqual(reloaded["runs"], 1)
            self.assertTrue((p / "links_publicos.csv").exists())

    def test_maximum_bounded(self):
        with self.assertRaises(ValueError):
            a.crawl(a.new_state(), 26, delay=0)

    def test_crawl_mocked_html_no_http(self):
        state = a.new_state()
        a.add_page(state, "437627", "PL", "official", "PRINCIPAL")
        sample = '<a href="/Documentos/Documento/439497">Emenda Nº 65 ao Projeto de Lei</a>'
        with patch.object(a, "fetch_public_html", return_value=(200, sample, len(sample))):
            outcomes = a.crawl(state, limit=1, delay=0)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["status"], "HTML_LIDO")
        self.assertIn("439497", state["pages"])


if __name__ == "__main__":
    unittest.main()
