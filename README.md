# LOA Limeira 2027 — auditoria documental

Projeto técnico independente de conferência de documentos públicos da Câmara Municipal de Limeira, associado ao PL nº 144/2026.

## Piloto de recuperação de metadados

O workflow manual `Camara Limeira - piloto de anexos` testa **cinco páginas oficiais fixas**, extrai exclusivamente links/IDs que aparecem explicitamente no HTML público e entrega CSV/JSON de conferência em **Actions → Artifacts**.

- Não baixa PDF, DOCX ou qualquer anexo.
- Não usa TinyFish, Cloud Browser, credenciais da Câmara nem contorno de acesso.
- Não reprocessa os 977 arquivos já preservados no Drive SME.
- Não faz scraping amplo nem considera ID sem URL oficial observada.
- Se houver erro HTTP, proteção ou restrição, registra o erro e encerra o respectivo acesso.

**Execute o workflow manualmente** em Actions, pelo botão **Run workflow**, no branch `main`. Confira o artefato `camara-piloto-metadados`. Nenhum novo ID será incorporado ao controle R04 antes de comparação com `Custodia977` e `R03_PENDENTES_30`.

Referências oficiais: https://consulta.limeira.sp.leg.br/Documentos/Documento/437627

Checkpoint R04 no Drive SME: https://docs.google.com/document/d/1fPhQ3ldMh9mIB7aBUxNRt6utKuyxQQdespXH9t4RciY/edit

**Atenção:** este repositório está atualmente **público**. Não envie dados pessoais, documentos privados, links autenticados, tokens ou arquivos internos do Drive.
