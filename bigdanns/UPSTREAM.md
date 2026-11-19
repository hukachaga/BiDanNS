# O que o BigDanNS manda para o Banana Native

Este arquivo reúne o que fizemos no BigDanNS e que pode servir ao Banana Native de [moceure](https://git.eden-emu.dev/moceure/BananaNative): o plano de envio, em português, e os textos prontos para colar, em inglês. As regras do projeto estão em `CONTRIBUTING.md`:

- abrir uma issue antes de mudanças grandes ou de um caminho novo;
- uma mudança por PR, partindo do `android` atual;
- só código-fonte;
- testar no driver do sistema **e** num Turnip;
- valores de um jogo só ficam no perfil dele;
- a versão da cadeia de shaders é trocada por eles.

## Plano (em ordem)

| # | Tipo | Assunto | Situação |
|---|---|---|---|
| A | Issue (ideia / desenvolvimento) | Leitura direta com recálculo nos vertex shaders (Turnip): Zelda 9,8 → 18,8 fps na cidade do castelo; o `cache_raw_loads` não cobre o helper de 128 bits | **publicada: [#505](https://git.eden-emu.dev/moceure/BananaNative/issues/505)** (2026-11-19) |
| B | Issue (bug) | `[RED] save commit: cannot clear … errno=13` repetido a cada commit: 2,4 milhões de linhas, log de 457 MB, jogo travando | **publicada: [#506](https://git.eden-emu.dev/moceure/BananaNative/issues/506)** (2026-11-19) |
| C | Comentário na PR #83 | O Turnip Mesa 27 não tem a opção `fp16` no `TU_DEBUG` | texto pronto |
| D | PR (depois da resposta à A) | O próprio passe, em `vk_android_spv.py`, com teste e entrada em `docs/reference/shaders.md` | a #505 foi testada por eles no driver Qualcomm (ver abaixo); falta o PR |
| E | PR | Vida infinita do Zelda: segurar o handle de vida do Link | precisa virar uma linha do perfil (`game.tsv`) em vez de `#define` |

A e B foram publicadas. A D vem depois que eles responderem à A. Cada envio é público, com o nome da sua conta do git.eden-emu.dev.

### Resposta à #505 (2026-11-19)

Testaram no driver da Qualcomm, num AYN Odin 3 (Snapdragon 8 Elite, Adreno 830, Android 15, `V@0800.72`), com Banana Native v0.3.45 e Zelda v131072:

- a reescrita da biblioteca deu o mesmo que aqui: 734 de 802 shaders, 67 pulados por terem mais de um bloco e 1 pelo helper que grava; os 734 passam no `spirv-val`;
- na casa do Link, com o driver Qualcomm: 670 draws, GPU 16,32 ms contra 16,12, imagem idêntica pixel a pixel;
- na casa do Link, com o Turnip `Turnip_Gen8_V39_Patched`: 673 draws, GPU 16,80 ms contra 16,46, imagem idêntica.

A casa do Link não tem os moradores da cidade, então mostra que o passe é **correto** nos dois drivers e custa uns 2 % onde não ajuda; o ganho só aparece onde esse shader pesa (a cidade do castelo).

Concordam em limitar a vertex shaders em linha reta: `main` de um bloco, sem gravar fora de `Function`/`Private`/`Output` e **sem ler `Private` antes de gravar**. Os fragment shaders têm derivadas implícitas, os compute/mesh/task têm barreiras e operações de subgrupo, e os geometry shaders têm `EmitVertex`.

A terceira condição não estava escrita no passe. Os 734 já a cumpriam, e agora o passe a verifica (`Skip('a Private read before its write in main')`); o resultado continua 734.

Próximo: o PR D, com o passe em `vk_android_spv.py`, um teste no estilo de `test_vk_gmem_cache.py` e a entrada em `docs/reference/shaders.md`. Para o custo na casa do Link, o passe pode valer só para os shaders em que a busca na tabela pesa (por exemplo, muitas chamadas de leitura direta).

---

## A. Issue: speculate-and-replay raw global loads in straight-line vertex shaders (Turnip)

**Title:** Turnip: raw global loads in vertex shaders, read through kept pool entries and replayed on a miss (Ocarina of Time Castle Town 9.8 → 18.8 fps)

**Body:**

Phone: AYANEO Pocket FIT (Snapdragon 8 Gen 3, Adreno 750, 11 GB, Android 14). Turnip Mesa 27.0.0-devel (git-3e8621cc0e, the one TotK Native ships). Banana Native v0.3.45. The Legend of Zelda: Ocarina of Time 0400486024DEC000, update 131072.

**Where the time goes.** In Castle Town by day, with a recorded route (`DM_REC`, then `DM_KEYS=@file`), the GPU takes 96 ms a frame. `DM_VK_GPUPROF_SPLIT=1` puts about 50 ms of that on vertex shader `b1f06157308e3b22` (Model.Product var1908, the townspeople), at 0.266 µs a vertex against 0.006 for the scene's ordinary vertex shader. This is the shader of "Raw global memory loads one block each on Turnip" in `docs/reference/shaders.md`. Shadow range, draw distance, a 640x360 scene, `TU_DEBUG=sysmem` and `TU_DEBUG=forcecb` did not lower it; the last three made the frame slower.

**A gap in `cache_raw_loads`.** In the v0.3.45 library this module still has 70 helper calls. 9 are cache runs, and **61 are a 128-bit raw load helper**, which `_raw_load_helper` does not take: a uvec4 physical pointer, word 0 returned and words 1-3 stored to a Private array. Extending `cache_raw_loads` to it gives valid SPIR-V but barely any gain: 0.157 µs a vertex, while the reference shader also got cheaper. The cost is the 61 inlined searches (code size and ir3's spills), not the time a search takes.

**What worked.** Every raw load call site of a straight-line vertex shader becomes:
- two 64-bit compares against K kept pool entries (Private, start/end/delta);
- one load at address + delta, or of the table's sink on a miss.

A miss reads 0, records its address (the first miss of the run) and sets a flag. `main` runs the old body as a function, in a loop:
- after a run that missed, **one** table search (an existing cache function, the only copy of the search left) adds that address's entry to the next slot, and the body runs again;
- the first call site seeds slot 0 with that search, so a vertex whose loads lie in one pool runs the body once;
- an address in no pool is remembered and reads 0, as the helper gives 0;
- addresses below 64 KiB read 0 at once.

Every value read is the helper's: same pool, same delta. A 128-bit call checks its base only, as the helper did. It applies only to vertex shaders whose main is one block and writes nothing but Function, Private and Output variables, since the body runs again.

**Results** (same route and scene, about 2,450 draws):

| | fps | GPU ms | `b1f06157` µs/vertex | `e9d9c742` µs/vertex |
|---|---|---|---|---|
| v0.3.45 library | 9.8 | 96.4 | 0.266 | 0.261 |
| K = 2 kept entries | 18.8 | 48.6 | 0.077 | 0.084 |
| K = 4 (current) | (route disturbed) | | 0.088 | |

With K = 2 some townspeople flickered: a vertex reading three pools cycled the two slots, reached the run limit (4) and drew zeros. K = 4 with 6 runs fixed it, checked by playing in Castle Town. The pass changes 734 of the 802 vertex shaders in Ocarina of Time's library that have a pool table; 67 are skipped because their main has more than one block. All 734 pass `spirv-val --target-env vulkan1.3`. Not checked yet: Qualcomm's own driver, and other games (their raw loads are in compute shaders, per the reference entry).

The fork has the pass as a standalone tool that rewrites a built library, loaded with `DM_VK_SHLIB`. It would belong in `vk_android_spv.py` after `cache_raw_loads`, which means a new `DMSH_VK_CHAIN`. Would you take it as a PR, and should it be limited to vertex shaders as here? I can open one with the pass in `vk_android_spv.py`, a SPIR-V interpreter test in the style of `test_vk_gmem_cache.py` and a `docs/reference/shaders.md` entry, after a run on Qualcomm's driver.

---

## B. Issue: a save commit that cannot clear its leftover logs a red line on every commit

**Title:** `[RED] save commit: cannot clear … .new left over errno=13` repeats on every save commit: 2.4 M lines, a 457 MB log, the game stalls

**Body:**

v0.3.45 test app (a second app id), Ocarina of Time. The save folder's parent had been made by `adb shell` (owner `shell`), so the app could make `<save>.new` but not remove it. Every later commit logged:

```
[dm] [RED] save commit: cannot clear the …/saves/0400486024DEC000.new left over errno=13 (committed version unchanged)
```

That was 2,447,324 times in a 10-minute run, a 457 MB log; the game stuttered badly while it wrote them. The save itself stayed at the committed version, so nothing was lost.

The cause was ours (folders made outside the app). Still, a red line once per path, with a count, would keep such a run playable and the log readable.

---

## C. Comment on PR #83 (Fast FP16 shader math for Turnip)

In the Turnip build that TotK Native ships (Mesa 27.0.0-devel, git-3e8621cc0e), `TU_DEBUG` has no `fp16` option. The string `fp16` occurs only inside ir3's `nofp16` (`IR3_SHADER_DEBUG`), and `FD_MESA_DEBUG` is not read by Turnip at all. With this driver the toggle would change nothing. ir3 lowers to half precision only what the SPIR-V marks as relaxed precision, and the translator's modules carry no such marking. That would be the place to get fp16 ALU on Adreno.

---

## E. (later) Ocarina of Time: Infinite Health holds Link's own life handle

Notes for the PR, when it is redone with a profile row:

- **Symptom:** with "Infinite Health (experimental)" on, Link still dies over a scene's damage.
- **Cause:** Link's status object keeps two GameDataInt handles (vtable, value at +8, hash at +0xc), at `[owner+0x1c10]` (life, `0x31ab5580`) and `[owner+0x1c18]` (max life, `0xfbe01da1`), and pushes them through `main+0x163b20` → setInt `main+0x163b70` every frame. Damage lowers the handle's value, so the cheat's write to the record was overwritten the next frame.
  - Found with `DM_PROBE_WATCH` on the game data write queue (the store at `main+0x163c5c`) and `DM_PROBE_LIVE=163b44?x2=31ab5580`.
  - `main+0x17de20`, earlier taken for Link, is the hearts HUD.
- **Fix:** a probe at `main+0x49e08c` (`ldr x0, [x19, #0x1c10]`, just before the push) sets the life handle's value to the max handle's while the cheat is on.
  - Main build e0f3ccfaf50065ae, instruction checked.
  - Verified in game: life 18 → 20 after each hit.
  - The offsets belong in a `game.tsv` row (as `drs_ctl` / `devtools`), not in code.
