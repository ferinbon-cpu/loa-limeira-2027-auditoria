# R12 — triagem de acesso aos candidatos R09 ainda não preservados

Fonte nominal: matriz R11 no Drive SME, aba R09_LISTA_336 (336 IDs atuais).
Retirado da fila: **602298**, já preservado no Drive e verificado por SHA-256 na R11.
Fila restante: **335 IDs**, ordenados conforme a matriz R09/R11.

O workflow roda quatro vezes ao dia (melhor esforço do GitHub) e examina no máximo 15 URLs oficiais por execução, com 2 segundos de intervalo, timeout 20 segundos e leitura de até 8.192 bytes por URL. A assinatura inicial da resposta permite sinalizar PDF, ZIP/OOXML, JPEG, PNG, GIF e OLE. Os arquivos não são guardados nem publicados; ficam apenas IDs, status HTTP, tipo MIME observado e assinaturas de prefixo.

**Esses 335 IDs NÃO são comprovadamente os 335 itens históricos remanescentes.** A correspondência com os 1.343 arquivos históricos e a lista das 56 páginas auxiliares permanece aberta. Resultados de assinatura de arquivo indicam apenas que um arquivo foi servido no prefixo consultado; não comprovam integridade integral do documento.

Para HTTP 401/403 não há novas tentativas. HTTP 429 pausa toda a execução por 24 horas. Erros temporários são limitados a duas tentativas com intervalo mínimo de 24 horas. Redirects a domínios externos não são permitidos. O estado da fila é persistido em data/r12 e o progresso é cumulativo.

Não há TinyFish, autenticação da Câmara, nem re-download dos 977 originais. O repositório é público: nenhum documento original, dado pessoal ou cookie é inserido no Git.
