# BigDanNS

Fork do [Banana Native](https://git.eden-emu.dev/moceure/BananaNative) focado em fazer **The Legend of Zelda: Ocarina of Time** (remake de Switch 2, `0400486024DEC000`) rodar bem no Android, mantendo os outros jogos funcionando. Primeiro aparelho de teste: AYANEO Pocket FIT ("Konkr"), Adreno 750, Android 14, driver Turnip.

O app instala **ao lado** do Banana Native oficial (pacote `dev.nxnative.android.bigdanns`, nome "BigDanNS"), com pastas, packs e saves próprios.

## O que este fork muda (sobre a v0.3.45)

| Mudança | Onde | Por quê |
|---|---|---|
| Ícone e logo com a foto do projeto | `android/app/src/main/res/drawable-nodpi/bdn_*.png`, `mipmap-anydpi-v26/ic_launcher*.xml`, `Ui.badge` | identidade do fork |
| Nome "BigDanNS" na tela do jogo e nos logs | `Signer.buildTag` | saber qual app gerou cada log |
| Trapaças ligadas por padrão | `Prefs.cheats` | o painel já lista as trapaças do jogo |
| Full vegetation sempre ligada (a menos que o jogador desligue) | `Prefs.fullVegetation` | a recomendação para Qualcomm tirava as folhas das árvores |
| PR #498 do upstream (cr1stian): um dispatch pede só o pipeline de compute que usa | `dm/gfx/vk_android/vka_pso.c` | menos compilações repetidas |
| PR #486 do upstream (loganrennick): um dispatch espera até 150 ms pelo pipeline em vez de ser pulado (`DM_VK_CS_WAIT_MS`) | `vka_pso.c`, `vka_draw.c` | céu, árvores e folhagem sumindo com o cache vazio |

As PRs #498 e #486 entram como commits dos autores originais.

## Compilar

Com Android SDK (plataforma 36, NDK 28.2.13676358, CMake 3.22.1), JDK 17+ e Git Bash:

1. Numa pasta de trabalho **fora** do repositório (por padrão, a pasta que contém este checkout), coloque o APK oficial da mesma versão em `official/banana-native-v0.3.45.apk`.
2. Crie `venv/` com Python 3 e `pip install fonttools`. No Windows, copie `venv/Scripts/python.exe` para `python3.exe`, porque o `python3` do Windows é o atalho da Microsoft Store.
3. Rode `bigdanns/build.sh`. Se faltar o `stage/`, o script monta a partir do APK oficial. O APK sai em `out/BigDanNS-<versão>.apk`.

No Windows, clone com `git config core.autocrlf false`. As ferramentas calculam hashes dos próprios arquivos byte a byte, e com CRLF os packs e as bibliotecas de shaders deixam de valer (ver `.gitattributes`).

## Colocar um jogo no BigDanNS sem preparar de novo

Não crie pastas dentro de `Android/data/dev.nxnative.android.bigdanns/` pelo `adb shell`: elas ficam com dono `shell`, e o jogo não consegue limpar o save (`[RED] save commit: cannot clear … errno=13`). Use o próprio app:

```sh
adb shell am start -n dev.nxnative.android.bigdanns/dev.nxnative.android.MainActivity --es game '<.nup>' --es pack '<pasta do pack em /sdcard>'
adb shell am start -n dev.nxnative.android.bigdanns/dev.nxnative.android.MainActivity --es pack_title 0400486024DEC000 --es pack_import '<pasta do pack em /sdcard>'
```

- **Save:** coloque em `<pasta do .nup>/saves-test/<title ID>`. Ele é copiado uma vez na primeira partida.
- **Driver custom:** descompacte em `files/gpu_drivers/<nome>` com `run-as`, passando o zip por `/data/local/tmp`.
- **Configurações por jogo:** `config/env-0400486024DEC000.txt` vai em `Android/data/dev.nxnative.android.bigdanns/files/`.

## Ferramentas (`bigdanns/tools`)

- `villa_test.sh <rótulo> <segundos> ["env CHAVE=valor" ...]`: muda opções com o jogo aberto (pelo `ctl.txt`) e resume fps, GPU, CPU e draws. Exemplos: `"env DM_VK_GPUPROF=30"` dá o raio-X da GPU, `"env DM_VK_GPUPROF_SPLIT=1"` cronometra cada desenho.
- `lib_extract.py <dmsh_vk.lib> <chave> <pasta>`: extrai o SPIR-V de um shader da biblioteca do pack.
- `spv_dis.sh <pasta>`: `spirv-dis` e `spirv-val` (WSL, spirv-tools).
- `recache.py <in.spv> <out.spv>`: roda o `cache_raw_loads` num módulo, para testar com `DM_VK_SPV_OVERRIDE=<original.spv>:<novo.spv>` sem preparar o jogo de novo.

## O que já medimos (Konkr, Turnip TotK Native, Mesa 27)

Na cidade do castelo o jogo fica entre 10 e 15 fps, com 58 a 96 ms de GPU por quadro. A medição varia entre reinícios por causa da quantidade de gente na praça e do aquecimento.

- **Não é configuração:** sombra 500→200 e distância 300→150 não mudaram nada (A/B com o jogo aberto).
- **Não é resolução:** a cena 3D em 640x360 com upscaling não ajudou.
- **As opções do driver pioram:** `TU_DEBUG=sysmem` e `TU_DEBUG=forcecb` deixaram o jogo mais lento. A opção "fp16" da PR #83 não existe nesse driver.
- **O gargalo** é o vertex shader dos personagens, `b1f06157308e3b22` (`Model.Product` var1908): ~50 ms do quadro. Ele faz 253 leituras de memória por ponteiro (`docs/reference/shaders.md`, "Raw global memory loads one block each on Turnip"), e o Turnip gera código enorme com spills: 53 ms no Turnip contra 1,4 ms no driver da Qualcomm, e 17 ms se as leituras fossem diretas.

### Experimentos

- `experiments/01-wide-raw-loads.patch`: estende o `cache_raw_loads` para as 61 leituras de 128 bits desse shader, que o passe original não reconhecia. Funciona e passa no `spirv-val`, mas **não ganhou desempenho**:
  - original: 0,170 µs por vértice;
  - versão 1 (quatro buscas): 0,282 µs;
  - versão 2 (uma busca e leitura de 16 bytes): 0,157 µs, com a cena toda também mais leve.

  Conclusão: o custo é o tamanho do código (61 cópias da rotina de busca, inlinadas), não o tempo das buscas. Fica fora do build.

### Próximo passo

Ler essas memórias por um buffer fixo, sem procurar o endereço a cada leitura: o replay descobre antes de desenhar em qual pool estão os ossos e passa isso ao shader, e o shader lê direto, sem a rotina de busca. É o caso de 17 ms medido pelos autores.

## Licença

nxnative é MIT. O APK com o frame generation do Lossless Scaling (o padrão) é GPL-3.0-or-later como um todo (`android/NOTICE.md`). O repositório não contém jogos, chaves nem nada extraído dos jogos.
