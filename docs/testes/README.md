# Guia da suíte de testes

| Camada | Comando | Tempo | O que cobre |
|---|---|---|---|
| Unitários + janela | `.venv/bin/pytest -q` | ~20 s | conf do PipeWire, hardware (sysfs falso), estado, aplicar/desfazer com `pactl`/`systemctl` simulados (`FakeSystem`), diagnóstico com áudio sintético, atualizador (GPG real, anti-downgrade, tar seguro), desinstalação, medidor, CLI, traduções, instalador universal num `HOME` falso, janela em todos os estados |
| Só o que mudou | `.venv/bin/pytest -q tests/test_<módulo>.py` | segundos | durante a codificação |
| Sem a janela | `.venv/bin/pytest -q -m "not ui"` | ~3 s | antes de cada commit |
| Pacotes | `packaging/build.sh 1.0.0 dist/` e `tests/packaging/test_install.sh` | ~10 min | rpm (Fedora), deb (Ubuntu 24.04, Debian 13), Arch (+ namcap) e install.sh, cada um num contêiner limpo |
| Um pacote | `ONLY=arch-pkg tests/packaging/test_install.sh` | ~2 min | repetir um caso |
| Repositórios | `tests/packaging/test_repos.sh dist ~/.local/share/gf63-mic-fix-signing` | ~5 min | assina, monta os repositórios apt/dnf, serve por HTTP e instala com conferência de assinatura |
| Real (só no GF63) | `gf63-mic-fix --apply`, medir, `--undo` | manual | ver "Validação real" abaixo |

## Como a janela é testada sem aparecer na tela

`tests/test_ui_smoke.py` abre a janela de verdade no backend **broadway** do GTK
(`gtk4-broadwayd`, sem navegador conectado) e salva um PNG com `--screenshot`. O mesmo
mecanismo gera as capturas do README (`scripts/screenshot.sh`). Nada aparece na tela de quem
roda os testes.

## Armadilhas conhecidas

- **Broadway não avança o relógio de quadros** sem visualizador: animações ficam pela metade.
  As capturas desligam animações (`gtk-enable-animations=false` num `XDG_CONFIG_HOME` temporário).
- **Capture a janela inteira**, não só o conteúdo, e fixe o esquema de cores
  (`ADW_DEBUG_COLOR_SCHEME`); senão o texto sai branco sobre fundo transparente.
- **`pactl -f json` troca descrições com acento por "(null)"** (bug do pactl): o app nunca usa
  descrições, só nomes e propriedades.
- **`pw-record` para a saída padrão grava AU big-endian**; use `--raw`.
- **Não use `pkill -f` com um padrão que aparece no próprio comando**: ele mata o shell que o
  executa.
- **Testes de tradução dependem do idioma da máquina**: compare com `_("texto")`, nunca com o
  texto em inglês fixo.
- **`msgmerge` sem `--no-fuzzy-matching` inventa traduções** marcadas como fuzzy, que o `msgfmt`
  ignora (a interface volta ao inglês sem aviso).
- **Contêiner Arch com imagem antiga**: `pacman -Sy` sem `-u` quebra (atualização parcial). O
  script usa `--pull=newer` e `pacman -Syu`.

## Validação real

No GF63 do dono (Tarefa 12, Passo 5): instalar o pacote, `--apply`, tocar um tom de 1 kHz e medir
o silêncio e o tom na fonte corrigida, conferir `--undo` (padrão e volume restaurados) e aplicar de
novo. Os números atualizam `MEASURED` em `scripts/readme_images.py`.

Os bugs achados ficam em [bugs.md](bugs.md).
