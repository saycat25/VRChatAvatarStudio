# Changelog

## 1.1.0 — 17/11/2026

### Segurança e estabilidade
- Validação profunda do `.vrcavatar.json` antes da criação de assets no Unity.
- Verificação de índices de malha/ossos, pesos, blendshapes, arrays e valores finitos.
- Validação do nome/caminho da textura PNG, dimensões e assinatura; preserva o nome exato referenciado no JSON.
- Importação repetida com opção de substituir preservando backup, criar cópia ou cancelar. Falhas removem somente a pasta criada na operação e tentam restaurar backup.
- Exportação em staging com rollback, manifesto de versões/opções e hashes SHA-256.
- Serialização dos exports no servidor para evitar colisões entre pedidos simultâneos.
- Logs rotativos locais.

### Unity / VRChat
- Menus de expressões e toggles paginados; cada menu limita-se a oito controles.
- Aviso explícito de toggles que excedem o limite local.
- Ranking descrito como estimativa heurística, sem alegação de equivalência ao SDK.
- Métricas corrigidas para ignorar renderers/componentes desativados e deduplicar transforms afetados por PhysBones.

### Editor e importação
- Desfazer/refazer, recuperação automática local, presets de estilo e paletas salvas.
- Busca de biblioteca/peças, duplicar, ocultar na exportação e bloquear edição.
- Importador OBJ com diagnósticos, índices negativos, polígonos triangulados e limites de vértices/triângulos.
- Recentrar câmera, zoom/foco, gesto multitouch de pinça e alternância de tema.
- Mensagem de erro útil quando WebGL não está disponível.

### Validação
- 31 testes automatizados Python na versão 1.1.0, incluindo verificações estáticas das proteções Unity.
- `node --check` para `app.js` e `viewer.js`; compilação sintática Python.
- Unity/VRChat Editor e Build & Publish permanecem pendentes de teste em ambiente real.


## 1.2.0 — Melhorias visuais (17/11/2026)

- Versão do aplicativo atualizada para `1.2.0`.

- Remodelado o rosto procedural com silhueta anime, olhos em camadas, cílios, sobrancelhas e detalhes faciais.
- Mechas de cabelo curvas e afiladas, A-pose, proporções de torso e membros refinadas.
- Adicionado moletom com capuz, detalhes de gola/zíper, pregas na saia e cadarços nos tênis.
- Qualidade padrão elevada para Alto e opção Ultra.
- Atualizados iluminação da prévia, miniaturas e presets de estilo.
- Documentado o limite do gerador procedural e o fluxo VRoid/XAvatar para bases de maior acabamento.


## 1.3.0 — Refinamento visual dos avatares

- Franja refeita como mechas curvas em lâminas 3D, com espessura e afilamento controlados.
- O penteado longo mantém cabelo traseiro e laterais; a franja não usa mais a faixa frontal que dava aspecto de capacete.
- Padrão de personagem mais versátil: orelhas humanas e sem cauda por padrão; orelhas/caudas de criatura continuam disponíveis nos controles e presets.
- Preset Anime VRChat ajustado para uma aparência humanoide; Kawaii preserva opções de orelhas e cauda de gato.
- Pré-visualizações atualizadas para Anime, Streetwear e Kawaii.
- Documentação ampliada sobre limites do modo procedural e fluxo de modelos VRoid/XAvatar.


## 1.4.0 — AI Avatar Workshop e biblioteca de assets

- Nova aba IA & Modelos com modos Preservar e Personalizar.
- Biblioteca local para modelo-base, acessórios, roupas, cabelos, imagens de referência e texturas.
- Upload com allowlist de extensões, validação de assinatura, limite de tamanho e SHA-256.
- Arquivos originais imutáveis; resultados de IA são salvos como novos GLBs derivados, nunca sobrescrevem a base.
- Integração opcional com Meshy: Texto para 3D (prévia + refinamento PBR), Imagem para 3D, Retexture e Remesh.
- Polling de tarefas, barra de progresso, tratamento de falhas e download dos modelos gerados.
- Chave API mantida somente na memória do servidor local; aviso e confirmação antes de tarefas que podem consumir créditos.
- Modo Preservar bloqueia remalhagem/retexturização do modelo-base e gera assets separados.
- Modo Personalizar permite retexturizar/remalhar uma cópia do modelo selecionado sem sobrescrever o original.
- Limitações de edição geométrica, montagem de roupas/acessórios e retarget documentadas explicitamente.
- 43 testes Python na suíte (incluindo política dos modos, armazenamento imutável, upload e tarefas simuladas); validação sintática Node/Python.
