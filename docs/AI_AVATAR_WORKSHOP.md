# AI Avatar Workshop — versão 1.4.0

## O que existe na interface

A aba **IA & Modelos** fornece dois modos persistidos localmente no navegador:

### Preservar meu modelo

- Mantém a base, o rosto, o corpo e o esqueleto como originais.
- Gera cabelo, roupas, calçados e acessórios como assets separados por texto ou imagem.
- O servidor rejeita operações de retextura/remesh sobre a base. Um acessório separado pode ser retexturizado/remalhado sem tocar na base.
- O resultado de cada geração é salvo como arquivo novo; nada substitui o arquivo-base.

### Personalizar meu modelo

- Permite criar uma cópia de trabalho derivada do arquivo-base.
- A operação **Retexturizar** usa a API Meshy para gerar novos materiais/texturas.
- A operação **Remalhar** usa a API Meshy para reconstruir a topologia e ajustar contagem de faces.
- Cada saída permanece em um novo GLB associado ao hash SHA-256 do arquivo de origem.
- O modo não altera automaticamente formato de rosto, proporções corporais ou estrutura do esqueleto. Para isso, use um editor 3D (por exemplo, Blender), com edição da malha, weight transfer e retarget validados manualmente.

## Formatos e limites locais

| Tipo | Formatos aceitos | Limite |
|---|---|---:|
| Modelo-base e acessórios | GLB, glTF, FBX, OBJ, STL, VRM | 25 MB |
| Referências e texturas | PNG, JPG, JPEG, WebP | 20 MB |

GLB autocontido é preferido. Um `.gltf` pode apontar para buffers `.bin` e texturas externos, que devem ser mantidos junto ao arquivo quando for aberto no Blender. VRM é armazenado como original, mas precisa ser convertido para GLB/FBX/OBJ antes de ser enviado às operações Meshy usadas pelo Workshop.

Os assets ficam no diretório `workspace/assets/`; o catálogo e tarefas ficam em `workspace/assets.json` e `workspace/ai_tasks.json`. A pasta `workspace/` é ignorada pelo Git e não deve ser incluída no pacote de distribuição, pois contém arquivos privados do usuário.

## Configuração da API Meshy

1. Crie/obtenha uma chave de API na plataforma de desenvolvedor Meshy.
2. Inicie o VRChat Avatar Studio.
3. Abra **IA & Modelos**, cole a chave no campo **Conectar IA (Meshy)** e clique em **Conectar**.
4. Escolha modo, modelo/arquivo, tipo de asset e descrição/referência. Para Image to 3D de cabelo/roupa/acessório, recorte a referência para mostrar preferencialmente apenas a peça; o endpoint Image to 3D usa a imagem como condicionamento visual.
5. Confirme o aviso de créditos e compartilhamento com o provedor antes de criar a tarefa.
6. Acompanhe a tarefa em **Tarefas e resultados**. Prévia de Texto para 3D pode ser refinada para gerar texturas PBR.

A chave é guardada apenas numa variável do processo Python em memória. Não é escrita em disco, no navegador, em presets ou nos exports. Ao reiniciar o programa, conecte novamente ou defina `MESHY_API_KEY` no ambiente antes de iniciar. Quando uma tarefa é criada, os arquivos escolhidos para aquela operação e a descrição são enviados à API Meshy. Não envie arquivos confidenciais ou sem os direitos de compartilhamento necessários.

### Operações da integração

| Operação | API Meshy | Efeito declarado |
|---|---|---|
| Gerar por descrição | Text to 3D v2 `mode=preview` | Prévia de malha 3D sem textura; refine cria texturas |
| Gerar por imagem | Image to 3D | Gera uma malha 3D a partir de uma imagem |
| Retexturizar cópia | Retexture | Gera materiais/texturas para a malha informada |
| Remalhar cópia | Remesh | Reconstrói topologia e contagem de faces |

Documentação do provedor:

- https://docs.meshy.ai/en/api/text-to-3d
- https://docs.meshy.ai/en/api/image-to-3d
- https://docs.meshy.ai/en/api/retexture
- https://docs.meshy.ai/en/api/remesh
- https://docs.meshy.ai/en/api/task-lifecycle

## O que não é automatizado nesta versão

- A IA não veste automaticamente um acessório em qualquer armature.
- A IA não faz weight transfer/skin binding de roupa de forma genérica.
- A IA não remodela seletivamente nariz, olhos, mandíbula, altura ou membros do arquivo-base. Retexture altera aparência de superfície; Remesh altera topologia.
- A geração a partir de uma imagem é uma geração 3D condicionada pela referência; não garante reconstrução fiel de todos os ângulos ou identidade topológica.
- O preview 3D atual do Studio ainda não carrega arbitrariamente GLB/FBX enviados na cena. Os arquivos gerados/guardados podem ser baixados e abertos no Blender/Unity.
- O resultado ainda precisa ser revisado em Blender/Unity e validado no VRChat SDK antes de Build & Publish.

## Proteções de dados

- Cada upload recebe identificador aleatório e nome interno que não depende do nome enviado pelo usuário.
- Extensões permitidas e assinaturas de arquivos são verificadas.
- SHA-256 é calculado no upload e verificado novamente antes da API usar o arquivo.
- Os caminhos persistidos não são recebidos diretamente da interface.
- O modelo original nunca é substituído por uma resposta do provedor.
- A API key fica apenas na memória do servidor local.
- A URL de download do resultado precisa usar HTTPS e domínio `*.meshy.ai`.
- Cada tarefa que pode consumir créditos requer ação/confirmacão explícita do usuário na interface.

## Próxima etapa recomendada

Implementar um pipeline Blender para abrir a base e assets gerados em uma cópia, fazer alinhamento/pivô/escala, parent/armature binding ou weight transfer conforme o caso, preview no mesmo viewer e exportação FBX/GLB para Unity. Esse passo exige automação 3D e casos de teste por rig; não deve ser declarado como automático antes de ser validado com modelos reais diversos.
