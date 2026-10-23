#!/usr/bin/env python3
"""Coleta incremental de METADADOS PÚBLICOS, sem download de anexos.
O estado é preservado no próprio repositório por GitHub Actions.
"""
import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from pilot_camara import Anchors, HOST, PAGES, classify_observed_url, fetch_public_html

MAIN_ID = "437627"
MAX_QUEUE = 360
MAX_PER_RUN = 25
MIN_DELAY = 1.5


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat(timespec="seconds")


def new_state():
    return {"schema": 1, "pages": {}, "files": {}, "runs": 0, "created_utc": stamp()}


def load(path):
    if not path.exists():
        return new_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != 1 or not isinstance(state.get("pages"), dict) or not isinstance(state.get("files"), dict):
        raise ValueError("INVALID_STATE — não sobrescrever estado anterior")
    return state


def add_page(state, page_id, label, origin, kind):
    page_id = str(page_id)
    if not re.fullmatch(r"\d{1,12}", page_id) or page_id in state["pages"] or len(state["pages"]) >= MAX_QUEUE:
        return False
    state["pages"][page_id] = {
        "id": page_id, "url": f"https://{HOST}/Documentos/Documento/{page_id}",
        "rotulo": label[:150], "tipo": kind, "origem": origin, "tentativas": 0,
        "status": "PENDENTE", "proxima_tentativa": "", "http": "", "erro": "",
        "links_arquivo": 0, "ultima_consulta": ""
    }
    return True


def add_file(state, file_id, url, label, page_id):
    if not re.fullmatch(r"\d{1,12}", file_id):
        return False
    # Não republicar possíveis dados pessoais que apareçam nos nomes dos anexos.
    label = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "[email_ocultado]", label)
    label = re.sub(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b", "[numero_ocultado]", label)
    if file_id in state["files"]:
        refs = state["files"][file_id]["fontes"]
        if page_id not in refs and len(refs) < 20:
            refs.append(page_id)
        return False
    state["files"][file_id] = {
        "id": file_id, "url_oficial": url, "rotulo_publico": label[:150],
        "fontes": [page_id], "primeiro_registro_utc": stamp(),
        "e_novo_dentre_336": "NAO_AFERIDO",
        "preservado_no_drive": "NAO_AFERIDO",
        "prova": "URL_EXPLICITA_NO_HTML_PUBLICO"
    }
    return True


def extract(state, markup, page):
    parser = Anchors()
    parser.feed(markup)
    files = set()
    new_ids = 0
    new_pages = 0
    for anchor in parser.anchors:
        item = classify_observed_url(anchor.get("href", ""), page["url"])
        if not item:
            continue
        kind, ident, url = item
        label = re.sub(r"\s+", " ", anchor.get("text") or anchor.get("title") or "").strip()
        if kind == "arquivo":
            files.add(ident)
            new_ids += int(add_file(state, ident, url, label, page["id"]))
        elif kind == "documento" and ident != page["id"]:
            if page["tipo"] == "PRINCIPAL":
                if not re.search(r"\bEmenda\s+N[ºo°.]?\s*\d+", label, re.I):
                    continue
                target_kind = "EMENDA"
            else:
                if not re.search(r"\bDocumento\s+do\s+Vereador\b|\bEmenda\s+N[ºo°.]?\s*\d+", label, re.I):
                    continue
                target_kind = "AUXILIAR"
            new_pages += int(add_page(state, ident, label, page["id"], target_kind))
    return len(files), new_ids, new_pages


def due(page, instant):
    if page["status"] == "BLOQUEADO_401_403_429":
        return False
    if page["status"] == "HTML_LIDO" and page["tipo"] != "PRINCIPAL":
        return False
    next_time = page.get("proxima_tentativa", "")
    if next_time:
        try:
            if datetime.fromisoformat(next_time) > instant:
                return False
        except ValueError:
            pass
    # Página-mãe pode ser revista diariamente para anexos/emendas novos.
    if page["status"] == "HTML_LIDO" and page["tipo"] == "PRINCIPAL":
        previous = page.get("ultima_consulta", "")
        if previous:
            try:
                return datetime.fromisoformat(previous) + timedelta(days=1) <= instant
            except ValueError:
                pass
    return True


def page_error(page, why, status=None):
    page["http"] = status or ""
    page["erro"] = str(why).replace("\n", " ")[:170]
    if status in (401, 403, 429):
        page["status"] = "BLOQUEADO_401_403_429"
        page["proxima_tentativa"] = ""
    else:
        page["status"] = "FALHA_TEMPORARIA"
        hours = 24 if page["tentativas"] < 3 else 168
        page["proxima_tentativa"] = (now() + timedelta(hours=hours)).isoformat()


def crawl(state, limit=MAX_PER_RUN, delay=MIN_DELAY):
    if not 1 <= limit <= MAX_PER_RUN:
        raise ValueError("LIMITE_INVALIDO: máximo 25 páginas por execução")
    instant = now()
    priority = {"PRINCIPAL": 0, "PILOTO": 1, "EMENDA": 2, "AUXILIAR": 3}
    queue = sorted((p for p in state["pages"].values() if due(p, instant)),
                   key=lambda p: (priority.get(p["tipo"], 9), p["tentativas"] > 0, int(p["id"])))
    selected = queue[:limit]
    outcomes = []
    for index, page in enumerate(selected):
        if index:
            time.sleep(delay)
        page["tentativas"] += 1
        page["ultima_consulta"] = stamp()
        try:
            status, markup, size = fetch_public_html(page["url"])
            count, added, pages_added = extract(state, markup, page)
            page["http"] = status
            page["erro"] = ""
            page["status"] = "HTML_LIDO"
            page["links_arquivo"] = count
            page["html_sha256"] = hashlib.sha256(markup.encode("utf-8")).hexdigest()
            page["html_bytes"] = size
            page["proxima_tentativa"] = ""
            outcomes.append({"pagina": page["id"], "status": "HTML_LIDO", "links_arquivo": count,
                             "ids_novos_observados": added, "paginas_novas": pages_added})
        except HTTPError as error:
            page_error(page, f"HTTP_{error.code}", error.code)
            outcomes.append({"pagina": page["id"], "status": page["status"], "erro": page["erro"]})
        except (URLError, TimeoutError, OSError, ValueError) as error:
            page_error(page, type(error).__name__ + ": " + str(error))
            outcomes.append({"pagina": page["id"], "status": page["status"], "erro": page["erro"]})
    return outcomes


def csv_file(path, data, headers):
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


def publish(state, out, outcomes):
    out.mkdir(parents=True, exist_ok=True)
    state["runs"] += 1
    state["updated_utc"] = stamp()
    (out / "estado.json").write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pages = sorted(state["pages"].values(), key=lambda p: (p["tipo"], int(p["id"])))
    files = sorted(state["files"].values(), key=lambda f: int(f["id"]))
    csv_file(out / "paginas.csv", pages,
             ["id", "url", "rotulo", "tipo", "origem", "status", "http", "erro",
              "tentativas", "ultima_consulta", "proxima_tentativa", "links_arquivo", "html_sha256"])
    rows = [{**f, "fontes": ";".join(f["fontes"])} for f in files]
    csv_file(out / "links_publicos.csv", rows,
             ["id", "url_oficial", "rotulo_publico", "fontes", "primeiro_registro_utc",
              "prova", "e_novo_dentre_336", "preservado_no_drive"])
    success = sum(p["status"] == "HTML_LIDO" for p in pages)
    report = [
        "# Coleta automática pública — PL 144/2026",
        "", "Data (UTC): " + stamp(), "",
        f"**Páginas indexadas:** {len(pages)}",
        f"**Páginas lidas:** {success}",
        f"**IDs de arquivos explicitamente observados:** {len(files)}",
        "**Novos IDs dos 336 pendentes do R04: NÃO AFERIDO** — exige cruzamento com a custódia SME.",
        "**Downloads de PDF/DOCX:** 0. **Autenticação/bypass:** nenhum.",
        "", "## Última execução", ""
    ]
    for r in outcomes:
        report.append("- Página " + r["pagina"] + ": " + r["status"] +
                      (f"; novos IDs observados: {r.get('ids_novos_observados', 0)}" if r["status"] == "HTML_LIDO"
                       else "; " + r.get("erro", "")))
    if not outcomes:
        report.append("- Nenhuma página elegível neste ciclo (concluída, protegida ou em intervalo de espera).")
    (out / "STATUS.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (out / "ULTIMA_RODADA.json").write_text(json.dumps({
        "data_utc": stamp(), "paginas_total": len(pages), "paginas_lidas": success,
        "ids_observados": len(files), "novos_ids_entre_336": "NAO_AFERIDO",
        "acessos_realizados": len(outcomes), "resultados": outcomes
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(pages), len(files), success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="data/publico")
    parser.add_argument("--limit", type=int, default=MAX_PER_RUN)
    opts = parser.parse_args()
    destination = Path(opts.outdir)
    state = load(destination / "estado.json")
    add_page(state, MAIN_ID, "PL nº 144/2026", "processo oficial", "PRINCIPAL")
    for label, url in PAGES[1:]:
        page_id = urlparse(url).path.rsplit("/", 1)[-1]
        add_page(state, page_id, label, MAIN_ID, "PILOTO")
    outcomes = crawl(state, opts.limit)
    pages, files, success = publish(state, destination, outcomes)
    print(json.dumps({"paginas": pages, "arquivos_observados": files,
                      "paginas_lidas": success, "consultas_neste_ciclo": len(outcomes)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
