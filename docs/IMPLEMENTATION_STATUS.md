# Status da auditoria e do plano de melhorias

## Implementado neste ciclo

- Validação estrutural prévia do JSON: formato/versão, ossos, pais, humanoid mapping, olhos, PhysBones, meshes, posições, normais, UVs, triângulos, bone indices/weights, blendshapes, valores não finitos e limites de tamanho.
- Validação do nome do PNG, canonicalização do caminho para a pasta de origem, rejeição de links simbólicos/reparse points, assinatura PNG e dimensões antes de criar assets; limites de carga para triângulos e PhysBones.
- Importação Unity com escolha entre substituir com backup, criar cópia ou cancelar; rollback remove apenas a pasta criada na operação e tenta restaurar o backup.
- Nomes de textura mantidos conforme o JSON, inclusive com caracteres Unicode no nome de avatar.
- Menus de expressão/itens em árvore paginada; cada menu gravado valida o máximo de oito controles. Itens acima do limite local são listados no log.
- Ranking do programa rotulado como estimativa heurística; corrigidos renderers desativados e duplicação global de transforms de PhysBones.
- Exportação em diretório staging, validação básica dos resultados, substituição atômica por rename, rollback, manifesto e SHA-256.
- Bloqueio de exportações simultâneas no servidor para evitar colisões para o mesmo destino.
- Logs rotativos locais, versões separadas do aplicativo/formato/pacote, changelog e documentação da arquitetura.
- Editor: undo/redo, recuperação automática via localStorage, estilos iniciais, paletas, busca, duplicação, ocultação e bloqueio de peças, tema manual, botão de recentrar, pinça touch e aviso de WebGL indisponível.
- OBJ: diagnósticos, limites de tamanho/vértices/triângulos, índices negativos e faces poligonais trianguladas em leque; preservação opcional da proporção.
- Testes: 31 testes Python, incluindo endpoint de exportação/manifesto e testes estáticos de regressão para as fontes C#.
- Workflow CI para testes Python e sintaxe JavaScript.

## Parcial ou pendente de implementação

- Unity/VRChat ponta a ponta: o código C# ainda precisa ser aberto e compilado em um projeto real com Unity e VRChat SDK Avatars instalados.
- Importação/reimportação real, validade Humanoid, Descriptor, FX, parâmetros, menus, visemas, eye tracking e PhysBones ainda precisam de validação dentro do Editor e em um avatar de teste.
- Build & Publish de teste e comparação do ranking com o SDK Control Panel ainda não foram executados.
- GLB tem testes estruturais, mas ainda precisa ser aberto no Blender e em um validador glTF externo para conferir skinning, materiais, morph targets e orientação.
- OBJ não importa MTL, imagens, UVs ou normais de origem. A triangulação em leque não é apropriada para todo polígono côncavo; nesses casos, pré-triangule no Blender.
- Ainda não existe importação GLB/glTF para dentro do Studio, edição visual de menus/expressões, seletor de attachment por clique no esqueleto, gizmos/seleção direta de malha, wireframe/normais, comparação lado a lado, projetos/versionamento de avatares, biblioteca compartilhada com licenças, integração com Blender ou relatório HTML/PDF.
- Não há migração automática do formato de preset/avatar v1 para versões futuras.

## Verificação necessária para aceite público

| Item | Situação | Observação |
|---|---|---|
| Testes Python | Aprovado no ambiente atual | 31 testes |
| Sintaxe JavaScript | Aprovado no ambiente atual | `node --check` em app.js e viewer.js |
| Compilação C# no Unity | Pendente | Requer Editor Unity instalado |
| Importação JSON/PNG no Unity | Pendente | Código de validação implementado, sem execução no Editor |
| Proteção contra caminhos externos | Implementada no código; pendente de teste Unity | PNG limitado à pasta de origem e a um nome de arquivo |
| Substituição não destrutiva | Implementada no código; pendente de teste Unity | Backup/cópia/cancelar e rollback |
| Humanoid/Descriptor/FX/menus | Pendente de validação Unity | Não inferir compatibilidade apenas por inspeção estática |
| PhysBones/visemas/eye tracking | Pendente de validação Unity/VRChat | Conferir visualmente e em build de teste |
| GLB no Blender/validador glTF | Pendente | Testes atuais verificam estrutura binária |
| Ranking oficial | Não implementado | O programa exibe somente estimativa local |
| Build & Publish SDK | Pendente | Deve ser feito em projeto real e conta de teste apropriada |

> Nota: este arquivo é o relatório original incluído no pacote. O teste atualizado executado durante a preparação desta publicação passou em 43 testes; a validação Unity continua pendente.
