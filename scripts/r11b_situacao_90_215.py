#!/usr/bin/env python3
"""R11B - Conferir situacao cadastrada atual de duas emendas via paginas HTML publicas.
Não extrai ou salva textos integrais; apenas marcador 'Situação' e carimbo da consulta.
"""
import html
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from pilot_camara import fetch_public_html, HOST

PAGES={"90":"439538","215":"439747"}
KNOWN={
  "Encaminhado","Retirada","Retirado","Arquivado","Aprovado","Rejeitado",
  "Aguardando Parecer","Em Tramitação","Tramitando","Reprovado"
}
class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.ignored=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in ("script","style","svg"):
            self.ignored+=1
        elif tag.lower() in ("p","span","div","td","tr","li","h1","h2","br"):
            self.parts.append(" ")
    def handle_endtag(self,tag):
        if tag.lower() in ("script","style","svg") and self.ignored:
            self.ignored-=1
        else:
            self.parts.append(" ")
    def handle_data(self,value):
        if not self.ignored:
            self.parts.append(value)

def extract_status(markup):
    parser=Visible()
    parser.feed(markup)
    visible=re.sub(r"\s+"," "," ".join(parser.parts))
    exact=re.search(r"(?:Situação|Situacao)\s*:\s*(.{1,100})",visible,re.I)
    if not exact:
        return ("NAO_LOCALIZADA", "NAO_LOCALIZADO")
    snippet=exact.group(1).strip()
    for status in sorted(KNOWN,key=len,reverse=True):
        if re.match(re.escape(status)+r"\b",snippet,re.I):
            return (status,"ROTULO_VISIVEL_NA_PAGINA")
    return ("NAO_CLASSIFICADA","CAMPO_PRESENTE_VALOR_NAO_RECONHECIDO")

def main():
    out=Path("r11b_output")
    out.mkdir(exist_ok=True)
    rows=[]
    for ix,(emenda,page) in enumerate(PAGES.items()):
        if ix: time.sleep(2)
        url=f"https://{HOST}/Documentos/Documento/{page}"
        row={"emenda":emenda,"pagina":page,"url":url,"situacao":"NAO_CONSULTADA",
             "prova":"", "http":None, "erro":None}
        try:
            http,markup,size=fetch_public_html(url)
            row["http"]=http
            row["html_bytes"]=size
            row["situacao"],row["prova"]=extract_status(markup)
        except HTTPError as e:
            row["http"]=e.code
            row["erro"]=f"HTTP_{e.code}"
            row["situacao"]="SEM_ACESSO"
        except (URLError,TimeoutError,ValueError,OSError) as e:
            row["erro"]=type(e).__name__
            row["situacao"]="SEM_ACESSO"
        rows.append(row)
        print("EMENDA",emenda,"HTTP",row["http"],"SITUACAO",row["situacao"])
        if row["http"]==429: break
    data={"coleta_utc":datetime.now(timezone.utc).isoformat(),
          "criterio":"Rotulo Situação legivel na página HTML pública, não ato legislativo",
          "resultados":rows,
          "limite":"Ainda conferir documentos decisorios para comprovar retirada efetivada"}
    (out/"situacoes.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"STATUS.md").write_text("# R11B - emendas 90 e 215\n\n"+
      "\n".join(f"- Emenda {x['emenda']}: HTTP {x['http']}; campo Situação: {x['situacao']}; prova {x['prova']}"
      for x in rows)+"\n\nA consulta não comprova votação, deferimento nem execução orçamentária.\n",encoding="utf-8")
if __name__=="__main__":
    main()
