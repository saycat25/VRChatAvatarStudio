# Qualidade visual e modelos com acabamento de VRChat

## O que mudou no gerador procedural

- Perfil de cabeça anime com maxilar mais estreito e bochechas suaves.
- Olhos em camadas, linha superior dos cílios, sobrancelhas curvas, brilho ocular, ponte nasal, boca e blush.
- Franja em mechas 3D curvas, achatadas e afiladas, evitando a faixa grossa que parecia capacete; cabelo longo com laterais e massa traseira.
- Pose de descanso em A em vez de braços perfeitamente horizontais.
- Moletom com capuz, gola, punhos, zíper, saia com pregas e tênis com cadarços.
- Qualidade padrão elevada para `3` (Alto) e opção `4` (Ultra).
- Iluminação da prévia e miniaturas com luz principal, preenchimento e brilho sutil.
- Presets Anime VRChat, Kawaii, Streetwear, Fantasia e Cyberpunk. O padrão agora usa orelhas humanas e sem cauda; opções de criatura continuam disponíveis.

## Limite honesto do modo procedural

Este gerador continua sendo uma base estilizada construída por código. Ele não produz, sozinho, o nível de acabamento de um avatar premium modelado por artista: cabelo sculptado em mechas complexas, malha facial cuidadosamente retopologizada, texturas pintadas à mão, shaders toon específicos, roupas com costuras e acessórios autorais. O modo `Ultra` aumenta a resolução da geometria, mas não substitui esses recursos artísticos.

## Fluxo recomendado para avatares realmente detalhados

1. Crie ou customize uma base no [VRoid Studio](https://vroid.com/en/studio). A página oficial do VRChat descreve o VRoid como criador de personagens anime com muitos controles e pintura manual.
2. Para usar o fluxo de dress-up do VRoid no VRChat, exporte o modelo em formato `XAvatar` e use o `XWear Packager` no Unity com o VRChat Creator Companion e o VRChat SDK. Consulte o [guia oficial de uso do VRoid no VRChat](https://vroid.pixiv.help/hc/en-us/articles/38723570104729-Purpose-Specific-Help-Guide).
3. Alternativamente, o VRoid Studio permite exportar `VRM 1.0` para aplicações compatíveis; isso não significa que o Unity ou este Studio importem VRM nativamente. Consulte [Como exportar um modelo como VRM](https://vroid.pixiv.help/hc/en-us/articles/38726063278233-How-do-I-export-a-model-as-VRM).
4. Faça a validação final no Unity/VRChat SDK, incluindo rig Humanoid, expressões, PhysBones, desempenho e Build & Publish.
5. Confirme a licença de uso de cada modelo, roupa, textura e acessório antes de publicar ou redistribuir.

## O que este projeto ainda não faz

- Não importa `VRM`, `XAvatar`, `FBX` ou `GLB` como corpo-base skinned dentro do editor web.
- Não converte automaticamente modelos externos em rig Humanoid.
- Não preserva shaders proprietários ou texturas de modelos externos.

Essas capacidades exigem uma etapa de integração de modelos-base com preservação de malha, UV, materiais, armature, pesos, blendshapes e licença. Não devem ser simuladas por um botão que apenas renomeie ou copie arquivos.

## Pré-visualizações incluídas

As imagens em `examples/previews/` mostram a saída atual do gerador procedural nos estilos Anime VRChat, Streetwear e Kawaii. Elas são amostras de geometria gerada pelo código, não modelos de referência de terceiros.
