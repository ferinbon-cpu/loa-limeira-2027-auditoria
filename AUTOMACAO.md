# R06 — Automação autônoma da consulta documental

Este repositório é PÚBLICO. O coletor registra somente metadados de links que o portal da Câmara publica explicitamente em páginas sem autenticação.

## Funcionamento

- O workflow **LOA Limeira - coleta autonoma de metadados** dispara na publicação do código na branch main e quatro vezes ao dia, no cron 17 2,8,14,20 * * * (UTC).
- Cada rodada consulta até 25 páginas HTML, com intervalo de 1,5 s, timeout de 15 s, limite de 2 MB por página e nenhum download de PDF ou DOCX.
- O ponto de entrada é https://consulta.limeira.sp.leg.br/Documentos/Documento/437627 e quatro páginas fixas de piloto. A fila cresce exclusivamente a partir de links oficiais observados no HTML.
- O estado e os links são gravados automaticamente no diretório data/publico no próprio GitHub, com CSV, JSON e Markdown. Também há artefato compactado em cada execução.
- A persistência usa o GITHUB_TOKEN do próprio repositório; não demanda segredos adicionais, credenciais da Câmara nem acionamento manual.

## Limites
- HTTP 401, 403 ou 429 bloqueiam novas tentativas da página, sem bypass.
- Outros erros são submetidos a intervalo de espera de 24 horas ou sete dias; não há repetição imediata.
- Não são copiados originais do Drive SME, conteúdo de anexos, senhas, cookies autenticados, CPF nem dados pessoais intencionalmente.
- O coletor NÃO faz cotejo automático com o Drive SME. Um ID observado pode já estar entre os 977 originais preservados ou 30 anexos conhecidos; a coluna 'e_novo_dentre_336' permanece 'NAO_AFERIDO' até comparação documental.
- O cron do GitHub é de melhor esforço e pode atrasar ou ser desativado em repositórios públicos inativos. Configuração agendada não equivale a execução confirmada.
- Pode-se suspender a automação em GitHub → Actions → Disable workflow.

## Base e controle
- Checkpoint R04: https://docs.google.com/document/d/1fPhQ3ldMh9mIB7aBUxNRt6utKuyxQQdespXH9t4RciY/edit
- Matriz SME: https://docs.google.com/spreadsheets/d/1BOGgrc5G1p-FtIIff6smU5Y1GWZluu6r6_N8x_ixNLo/edit

O checkpoint R04 tem 977 originais preservados, 366 anexos não preservados, 30 ausentes conhecidos e 336 sem identidade nominal. O repositório publica novas observações SEM presumir que sejam esses 336.
