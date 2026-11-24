# GF63 Mic Fix — design

Data: 24/11/2026 · Estado: aguardando aprovação

## 1. Intenção e porquê

O microfone interno do MSI GF63 Thin é inutilizável no Linux (ruído altíssimo) em qualquer
distribuição, embora funcione no Windows. A causa foi medida em 24/11/2026 num GF63 Thin 10SC
(codec Realtek ALC233, `10ec:0235`, subsistema `1462:12f4`, microfone no pino `0x12`):

1. **Canal esquerdo morto.** Há um único microfone digital, ligado no canal direito. O Linux expõe
   a captura como estéreo; o canal esquerdo é só chiado. Um tom de 1 kHz tocado nos alto-falantes
   aparece no canal direito (+47 dB) e praticamente não aparece no esquerdo (+3 dB).
2. **Ganho exagerado.** 100% no volume da fonte = +60 dB no hardware (Capture +30 dB e
   Internal Mic Boost +30 dB). No padrão das distros o sinal satura mesmo em silêncio.
3. **Ronco grave** de 40–120 Hz no canal bom.

A correção manual que funcionou: fonte virtual mono do PipeWire que usa só o canal direito, com
passa-altas de 4ª ordem em 120 Hz, e volume da fonte física em 20% (+18 dB, sem boost).
Resultado medido: o tom de teste passou de +13 dB para +22 dB acima do ruído, sem saturação.

O dono quer transformar isso num app instalável e público, para ajudar outras pessoas com o
mesmo notebook, usado inteiramente por janela e que se atualize sozinho.

## 2. Objetivos

- Corrigir o microfone do GF63 Thin com um clique, sem terminal.
- Tudo por interface gráfica: corrigir, testar, ajustar, desfazer e desinstalar.
- Desinstalador próprio, "como app de Windows": remove a correção e o programa.
- Pacotes `.rpm`, `.deb`, pacote do Arch e instalador universal.
- Atualização automática pelo gerenciador de pacotes, via repositório apt/dnf próprio assinado.
- Repositório público no GitHub com página (README) explicativa, com textos e imagens.

## 3. Fora do escopo

- Outros notebooks. O app só atua em "GF63 Thin" com codec ALC233.
- PulseAudio puro (sem PipeWire). O app detecta e explica que não é suportado.
- Flatpak, Snap e AppImage: rodam isolados e não configuram o áudio do sistema de forma confiável.
- Publicação no AUR (exige conta própria); o repositório traz o `PKGBUILD` e o pacote pronto.
- Correção no kernel (quirk do codec). Pode ser sugerida upstream depois, fora deste projeto.

## 4. O que faria disto um fracasso

- Deixar o áudio de alguém pior do que estava, ou sem volta. Tudo que o app muda tem de ser
  desfeito por ele, restaurando os valores anteriores.
- Aplicar a correção em hardware diferente do esperado.
- Atualização que baixe e execute código não assinado.
- Abrir janelas ou tirar capturas da tela do dono durante o desenvolvimento (preferência dele):
  testes de interface e capturas de tela são feitos sem exibir nada na sessão dele.

## 5. Restrições

- Nenhuma alteração fora da pasta do usuário para aplicar a correção; root só para instalar,
  atualizar e remover o pacote.
- Dependências apenas dos repositórios oficiais das distros-alvo.
- Chave privada de assinatura nunca entra no repositório; fica em segredo do GitHub Actions.
- Licença GPL-3.0, SemVer e `CHANGELOG.md` atualizado a cada versão (convenção dos projetos do dono).
- Commits como `junior9283 <eng.geraldo@outlook.com>`.

## 6. Abordagens consideradas

| | Abordagem | Prós | Contras |
|---|---|---|---|
| A | **Python + GTK4/libadwaita** (escolhida pelo dono) | pacote minúsculo, `noarch`, dependências nos repositórios oficiais de todas as distros-alvo, código fácil de contribuir | no KDE tem visual do GNOME |
| B | Python + Qt6 | visual nativo no KDE | dependência pesada nas distros GNOME; nomes de pacote variam |
| C | Diálogos zenity/kdialog | quase sem código | sem medidor nem ajuste ao vivo; não é "tudo por interface" |

Descartado: binário compilado (Rust/Tauri), dezenas de MB por arquitetura para uma correção de
configuração.

Decisões do dono: só GF63 Thin; tudo por interface com desinstalador próprio; atualização por
repositório apt/dnf próprio; GTK4/libadwaita.

## 7. Design

Tudo abaixo que não está na seção 6 é decisão minha (do autor do design), não do dono.

### 7.1 Identidade

- Nome do projeto e do repositório: `gf63-mic-fix` (`github.com/junior9283/gf63-mic-fix`).
- Nome exibido: "GF63 Mic Fix". ID do app: `io.github.junior9283.Gf63MicFix`.
- Interface em português do Brasil e inglês (gettext), conforme o idioma do sistema.
- Pasta local: a pasta local do projeto.

### 7.2 Como a correção é aplicada (por usuário, sem root)

O app **não** usa o `filter-chain.service` da distro nem mexe na configuração do PipeWire do
usuário. Ele traz um serviço de usuário próprio:

- `/usr/lib/systemd/user/gf63-mic-fix.service` roda
  `pipewire -c ~/.config/gf63-mic-fix/pipewire.conf` (um cliente PipeWire isolado, só com o
  módulo filter-chain).
- O app gera esse `pipewire.conf` com: captura só do canal `FR` da fonte física
  (`stream.dont-remix`, `node.passive`), dois `bq_highpass` em série (120 Hz, Q 0,54 e 1,31),
  saída `Audio/Source` mono chamada `gf63_mic_fix`, descrição "Microfone interno (corrigido)".
  Se a supressão de ruído estiver ligada, acrescenta o plugin RNNoise na cadeia.
- O nome da fonte física é descoberto em tempo de execução (a fonte ALSA da placa cujo codec é
  o ALC233), não fixado.

"Corrigir" faz, nesta ordem: confere o hardware → salva o estado anterior (fonte padrão e volume
da fonte física) em `~/.config/gf63-mic-fix/state.json` → gera o conf → habilita e inicia o
serviço → define a fonte virtual como padrão → põe a fonte física em 20%.

"Desfazer" restaura a fonte padrão e o volume salvos, para e desabilita o serviço e apaga
`~/.config/gf63-mic-fix/`.

Consequência desejada: se alguém remover o pacote pelo gerenciador de pacotes, a unidade some,
o serviço deixa de existir e o sistema volta sozinho ao microfone físico. Sobram apenas o volume
em 20% e uma pasta pequena de configuração.

Regras de estado (para nunca deixar pior nem sem volta):

- "Corrigir" é idempotente: o estado anterior só é salvo se ainda não houver `state.json` e a
  fonte padrão atual não for a própria fonte virtual. Rodar duas vezes não sobrescreve o que
  foi salvo.
- "Desfazer" sem `state.json`, ou com a fonte padrão salva inexistente (ex.: USB desconectado):
  limpa a escolha de padrão e deixa o WirePlumber eleger a fonte, e mantém o volume da fonte
  física como está. O volume alto original é justamente o defeito, então não há valor "bom" a
  inventar.
- Remoção do pacote pelo gerenciador, sem passar pelo desinstalador: aceita-se que sobrem o
  volume em 20% e a pasta `~/.config/gf63-mic-fix/`. Ambos são inofensivos e não há scriptlet
  que alcance os homes de todos os usuários. A limpeza completa é a do desinstalador (7.5).
- Sem daemon de vigilância. A fonte virtual tem prioridade alta e o WirePlumber memoriza o
  padrão escolhido. Se o padrão mudar (ex.: a pessoa ligou um headset), isso é respeitado; a
  janela mostra "correção ativa, mas outro microfone é o padrão" com o botão "Usar como padrão".

### 7.3 Conferência do hardware

O app só habilita "Corrigir" se:

- `/sys/class/dmi/id/product_name` começa com `GF63 Thin`; e
- existe codec com Vendor Id `0x10ec0235` em `/proc/asound/card*/codec#*`; e
- o servidor de áudio é PipeWire com `pipewire-pulse` (`pactl info`).

Variantes: `GF63 Thin 10SC` é marcada como "verificada". Outras variantes "GF63 Thin" passam
pelo **diagnóstico** antes de liberar a correção: o app toca um tom de 1 kHz por 2 s nos
alto-falantes, grava os dois canais e só libera se o direito captar o tom e o esquerdo não
(diferença ≥ 20 dB). A análise é em Python puro (Goertzel), sem numpy. Caso contrário, mostra
"este notebook não apresenta o defeito conhecido" e não altera nada. Se nenhum canal captar o
tom (alto-falantes mudos, fone conectado), o resultado é "inconclusivo": o app orienta a
aumentar o volume e tirar o fone, oferece tentar de novo e não libera a correção.

Versões: o alvo são distros em que o PipeWire é o servidor de áudio padrão. A versão mínima do
PipeWire é a que passar na verificação da seção 8; abaixo dela o app mostra "PipeWire antigo
demais" com a versão exigida, sem alternativa por PulseAudio.

### 7.4 Janela

Uma janela única (libadwaita), com:

```
┌ GF63 Mic Fix ────────────────────────────── ⋮ ┐
│  ● Microfone corrigido                        │
│  MSI GF63 Thin 10SC · Realtek ALC233          │
│                                               │
│  Nível   ▮▮▮▮▮▮▮▯▯▯▯▯▯▯▯▯                     │
│                                               │
│  Correção ativa                      [ ●━ ]   │
│  Ganho do microfone          ──────●────      │
│  Supressão de ruído (RNNoise)        [ ━○ ]   │
│                                               │
│  [ Testar microfone ]                         │
│                                               │
│  v1.0.0 · atualizado pelo sistema             │
└───────────────────────────────────────────────┘
   menu ⋮: Diagnóstico · Sobre · Desinstalar…
```

- **Estado**: corrigido / não corrigido / hardware não suportado / PipeWire ausente.
- **Nível**: medidor ao vivo da fonte em uso, só enquanto a janela está aberta.
- **Correção ativa**: liga (Corrigir) e desliga (Desfazer).
- **Ganho**: volume da fonte física, limitado à faixa 10%–30% (0 a +28 dB), acima disso satura.
- **Supressão de ruído**: só aparece habilitada se o plugin LADSPA do RNNoise estiver instalado;
  senão mostra como instalar. O pacote o declara como dependência recomendada onde existir.
- **Testar microfone**: grava 5 s e reproduz, para a pessoa ouvir o resultado.
- **Desinstalar…**: ver 7.5.

Existe uma interface mínima de linha de comando no mesmo executável (`--status`, `--apply`,
`--undo`), usada pelos testes e pelos scripts do pacote; não é o caminho documentado ao usuário.

### 7.5 Desinstalador

Acessível pelo menu da janela e por uma entrada própria no menu de aplicativos
("Desinstalar GF63 Mic Fix"). Fluxo: confirmação → "Desfazer" (7.2) → remoção do programa:

- instalado por pacote: `pkexec /usr/libexec/gf63-mic-fix-uninstall`, um script root pequeno e
  sem argumentos que remove o pacote pelo gerenciador da distro (dnf/apt/pacman), junto com o
  arquivo de repositório e a chave. Vem com política do polkit para a janela de senha ter texto
  claro.
- instalado pelo instalador universal: apaga os arquivos em `~/.local`, sem root.

### 7.6 Pacotes

Um único arquivo de configuração do `nfpm` gera `.rpm`, `.deb` e pacote do Arch, no GitHub
Actions. Todos `noarch`.

| Formato | Distros | Atualização |
|---|---|---|
| `.rpm` | Fedora, Nobara e derivadas | repositório dnf próprio |
| `.deb` | Ubuntu, Mint, Zorin, Pop!_OS, Debian | repositório apt próprio |
| pacote Arch + `PKGBUILD` | Arch, Manjaro, CachyOS | app avisa da versão nova (notificação com link) |
| `install.sh` + `.tar.gz` | qualquer outra (openSUSE, Void, etc.) | autoatualização em `~/.local`, com assinatura conferida |

Dependências: Python 3, PyGObject, GTK4, libadwaita, PipeWire, pipewire-pulse (`pactl`),
WirePlumber. Recomendada: plugin LADSPA do RNNoise (`noise-suppression-for-voice`).

O `.rpm` e o `.deb` instalam o arquivo de repositório (`/etc/yum.repos.d/gf63-mic-fix.repo` ou
`/etc/apt/sources.list.d/gf63-mic-fix.sources`) e a chave pública, de modo que baixar o pacote
uma vez basta: as versões seguintes chegam com as atualizações normais do sistema.

### 7.7 Repositórios e atualização

- Repositórios apt e dnf hospedados no GitHub Pages do próprio projeto (ramo `gh-pages`),
  com metadados e pacotes assinados por uma chave GPG dedicada ao projeto.
- A chave é gerada uma vez; a parte privada vai para o segredo `GPG_PRIVATE_KEY` do GitHub
  Actions e uma cópia de segurança fica fora do repositório, em
  `~/.local/share/gf63-mic-fix-signing/` (permissão 700), para o dono guardar.
- Todos os arquivos da Release (`.rpm`, `.deb`, pacote Arch, `.tar.gz`) são assinados com essa
  mesma chave (assinatura destacada `.asc`) e acompanham um `SHA256SUMS`. O `PKGBUILD` aponta
  para o `.tar.gz` da Release, com o sha256.
- Confiança no primeiro uso, como nos repositórios de terceiros usuais: o primeiro pacote é
  baixado por HTTPS da Release e traz a chave pública. O README publica a impressão digital da
  chave e os passos para conferir a assinatura à mão, para quem quiser.
- Troca de chave: como a chave pública vem dentro do pacote, uma versão assinada com a chave
  antiga pode entregar a nova. Se a chave for perdida, a saída é reinstalar manualmente, o que
  o README explica; por isso a cópia de segurança.
- Instalador universal e Arch: um temporizador de usuário consulta uma vez por semana a API
  pública de releases do GitHub (sem enviar dado algum do usuário). No Arch só notifica. No
  instalador universal baixa o `.tar.gz`, confere a assinatura GPG com a chave pública embutida
  e só então substitui os arquivos em `~/.local`; sem `gpg` instalado, apenas notifica.

### 7.8 Publicação de versões

Criar a tag `vX.Y.Z` dispara o GitHub Actions: lint e testes → gera os pacotes → assina →
cria a Release com os arquivos → atualiza os repositórios apt/dnf no `gh-pages`.

### 7.9 Página do repositório

- `README.md` em inglês (alcance mundial) e `README.pt-BR.md` completo, um apontando para o outro.
- Conteúdo: o problema, a causa (com as medições reais), como instalar em cada distro, como usar,
  como desinstalar, como funciona, privacidade (a única conexão é a consulta de versão),
  limitações, como contribuir e como relatar outra variante do GF63.
- Imagens próprias: ícone/logo, faixa de topo, gráfico antes/depois das medições, diagrama de
  como a correção funciona e captura da janela do app (gerada sem exibir nada na tela do dono).
- Descrição e tópicos do repositório, `LICENSE`, `CHANGELOG.md`, modelo de issue.

### 7.10 Testes

- Unitários (pytest): geração do conf, conferência de hardware com sysfs falso, salvar/restaurar
  estado com `pactl` simulado, análise do diagnóstico com áudio sintético, comparação de versões,
  conferência de assinatura no atualizador.
- CI: lint, testes, construção dos pacotes e instalação de cada um em contêiner da distro
  correspondente (Fedora, Ubuntu, Debian, Arch), rodando `--status`.
- Validação real no GF63 do dono: aplicar, medir de novo, desfazer e confirmar a restauração.
- Guia e registro de bugs em `docs/testes/`.

### 7.11 Migração da máquina do dono

A correção manual de hoje (`~/.config/pipewire/filter-chain.conf.d/50-microfone-gf63.conf` e o
`filter-chain.service` habilitado) é removida quando o app for instalado e aplicado nela, para
não haver dois microfones virtuais.

## 8. Deixado para quem for construir

- Estrutura interna dos módulos Python e detalhes visuais da janela.
- Ferramenta para montar os repositórios (`createrepo_c`, `reprepro` ou equivalente).
- Como gerar a captura da janela sem exibi-la (compositor headless, broadway ou no CI).
- Como medir o nível ao vivo (ex.: `pw-record` em pipe).
- Desenho do ícone e das imagens.
- Conferir, antes de fixar, que `pipewire -c <caminho absoluto>` e os controles `bq_highpass`
  funcionam nas versões de PipeWire das distros-alvo; ajustar o mínimo suportado conforme o
  resultado e declarar no README.
