# Registro de bugs

Formato: sintoma → causa → correção → teste → lição.

## 1. Rebaixamento de versão por replay (atualizador)

- **Sintoma:** uma release antiga e corretamente assinada, republicada com número maior, seria instalada.
- **Causa:** a versão anunciada não estava amarrada ao conteúdo assinado.
- **Correção:** o tarball precisa ter a pasta de topo `gf63-mic-fix-<versão>`, as URLs precisam
  ser do projeto e a versão precisa ser maior que a instalada.
- **Testes:** `test_self_update_rejects_renamed_old_release`, `test_self_update_rejects_foreign_download_url`,
  `test_self_update_rejects_not_newer`.
- **Lição:** assinatura prova a origem, não a versão; amarre o que importa ao conteúdo assinado.

## 2. Interface em inglês apesar da tradução (fuzzy)

- **Sintoma:** títulos como "Microphone fixed" apareciam em inglês com o sistema em pt-BR.
- **Causa:** o `msgmerge` criou entradas fuzzy com traduções erradas, e o `msgfmt` ignora fuzzy.
- **Correção:** `update-po.sh` com `--no-fuzzy-matching`; entradas traduzidas de novo.
- **Teste:** `test_pt_br_has_no_fuzzy_guesses`.
- **Lição:** um `.po` "completo" pode não estar; teste a ausência de fuzzy.

## 3. Descrição cortada na janela

- **Sintoma:** a descrição do estado ficava cortada numa caixa com rolagem.
- **Causa:** `Adw.StatusPage` tem rolagem interna.
- **Correção:** cabeçalho próprio (ícone, título e descrição com quebra de linha).
- **Teste:** `test_window_opens_for_each_status` + conferência visual das capturas.
- **Lição:** confira as capturas; o teste de fumaça não vê corte de texto.

## 4. Janela travada após falha na desinstalação

- **Sintoma:** se a desinstalação lançasse exceção, a janela ficava insensível para sempre.
- **Causa:** a thread morria antes de devolver o resultado ao loop da interface.
- **Correção:** `run_in_thread` comum (`ui/tasks.py`), que sempre devolve `(resultado, erro)`.
- **Teste:** `test_uninstall_crash_gives_the_window_back`.
- **Lição:** todo trabalho em thread precisa de caminho de volta também no erro.

## 5. Arquivo órfão após desinstalar (install.sh)

- **Sintoma:** `~/.local/share/applications/mimeinfo.cache` ficava depois da desinstalação.
- **Causa:** o instalador rodava `update-desktop-database`, que o app não precisa (sem MimeType).
- **Correção:** comando removido.
- **Teste:** `test_install_puts_exactly_what_the_uninstaller_removes`.
- **Lição:** compare o que o instalador cria com o que o desinstalador apaga, arquivo por arquivo.

## 6. namcap: "File is owned by 0:0" no pacote Arch

- **Sintoma:** o namcap rejeitava (erro) todos os arquivos do pacote gerado pelo nfpm.
- **Causa:** o empacotador archlinux do nfpm grava uid/gid 0 sem os nomes "root".
- **Correção:** o `build.sh` reempacota com `--owner=root:0 --group=root:0`.
- **Teste:** `tests/packaging/test_install.sh` (caso `arch-pkg` falha se o namcap acusar erro).
- **Lição:** valide os pacotes com a ferramenta da própria distro.
