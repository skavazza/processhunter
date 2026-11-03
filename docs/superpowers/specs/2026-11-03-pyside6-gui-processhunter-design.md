# Especificação de Design: ProcessHunter GUI (PySide6)

**Data:** 2026-11-03  
**Status:** Aprovado para Planejamento  
**Autor:** Antigravity & Usuário  

---

## 1. Visão Geral e Objetivos

O **ProcessHunter GUI** é uma aplicação desktop desenvolvida em Python 3 e PySide6 (Qt) para o sistema operacional Windows. O objetivo é substituir e expandir a funcionalidade do script PowerShell `processhunter.ps1`, fornecendo uma interface gráfica moderna, amigável e robusta para gerenciamento e encerramento automatizado de processos indesejados.

### 1.1 Objetivos Principais
- **Modo Híbrido**: Permitir tanto o encerramento imediato sob demanda quanto o monitoramento contínuo em segundo plano (Modo Sentinela).
- **Gerenciamento Flexível de Alvos**: Seleção por inspeção de processos em execução ou inserção manual de nomes de executáveis.
- **Integração com Inicialização do Windows**: Opção nativa para iniciar com o Windows silenciosamente na bandeja do sistema (`System Tray`).
- **Resiliência e Boas Práticas**: Separação estrita de camadas (Core / UI / Workers), captura segura de permissões de sistema (`AccessDenied`), suporte a testes automatizados com `pytest` e proteção contra múltiplas instâncias concorrentes.

---

## 2. Arquitetura do Sistema

A aplicação adota uma arquitetura em camadas desacopladas. Toda a lógica de negócio do Windows e de controle de processos é mantida isolada de qualquer elemento gráfico ou framework de UI.

```
c:\Scripts\processhunter\
├── core/
│   ├── __init__.py
│   ├── hunter.py          # Motor de busca e encerramento de processos (psutil)
│   ├── config.py          # Modelo de dados e persistência JSON das configurações
│   ├── autostart.py       # Manipulação da chave Run no Registro do Windows (HKCU)
│   └── logger.py          # Sistema central de logs com handlers de arquivo e emissão de eventos
├── ui/
│   ├── __init__.py
│   ├── main_window.py     # Janela principal em PySide6
│   ├── tray.py            # Ícone e menu da bandeja do sistema (System Tray)
│   ├── workers.py         # QThreads para execução em segundo plano sem congelar a UI
│   └── components/
│       ├── __init__.py
│       ├── process_table.py # Tabela de processos ativos no Windows com filtro de busca
│       └── target_list.py   # Lista de alvos configurados com switches/checkboxes
├── tests/
│   ├── test_hunter.py     # Testes do motor com mocks de processos
│   ├── test_config.py     # Testes de leitura/gravação das configurações
│   └── test_autostart.py  # Testes de ativação/desativação do registro Windows
├── app.py                 # Ponto de entrada da aplicação (Entrypoint)
├── requirements.txt       # Dependências: PySide6, psutil, pytest
└── README.md              # Documentação de uso e execução
```

---

## 3. Especificação dos Módulos

### 3.1 Camada Core (Independente de UI)

#### `core/config.py`
- **Responsabilidade**: Gerenciar a leitura, gravação e validação das configurações da aplicação.
- **Localização do arquivo**: `%APPDATA%\ProcessHunter\config.json` (com fallback no diretório da aplicação se `%APPDATA%` não estiver acessível).
- **Esquema de Dados**:
  ```json
  {
    "targets": [
      { "name": "msedgewebview2d", "enabled": true }
    ],
    "sentinel_interval_seconds": 5,
    "autostart": false,
    "start_minimized": true,
    "minimize_to_tray_on_close": true,
    "notify_on_kill": true
  }
  ```
- **Métodos da classe `ConfigManager`**:
  - `load() -> ConfigData`: Carrega o arquivo JSON existente ou cria configuração padrão se ausente.
  - `save() -> None`: Salva as configurações de forma atômica no disco.
  - `add_target(name: str) -> bool`: Normaliza e adiciona um novo alvo. Retorna falso se já existir.
  - `remove_target(name: str) -> bool`: Remove o alvo da lista.
  - `toggle_target(name: str, enabled: bool) -> bool`: Altera o estado ativo/inativo do alvo.
  - `set_sentinel_interval(seconds: int) -> None`: Atualiza o intervalo da sentinela.

#### `core/hunter.py`
- **Responsabilidade**: Localizar e finalizar processos do sistema utilizando `psutil`.
- **Tipos de Dados**:
  - `ProcessInfo`: `NamedTuple` contendo `pid: int`, `name: str`, `memory_mb: float`, `status: str`.
  - `KillResult`: `NamedTuple` contendo `pid: int`, `name: str`, `success: bool`, `error_message: str`.
- **Métodos da classe `ProcessHunter`**:
  - `normalize_name(name: str) -> str`: Remove espaços em branco, remove `.exe` ao final e converte para minúsculas.
  - `scan_active_processes() -> list[ProcessInfo]`: Itera sobre processos ativos com `psutil.process_iter(['pid', 'name', 'memory_info', 'status'])`. Ordena alfabeticamente.
  - `kill_targets(target_names: list[str]) -> list[KillResult]`:
    - Normaliza os nomes dos alvos para comparação rápida (conjunto `set`).
    - Para cada processo ativo coincidente, executa `proc.kill()`.
    - Captura explicitamente `psutil.NoSuchProcess` (ignorado com sucesso se o processo encerrou sozinho) e `psutil.AccessDenied` (registrado como falha com aviso de permissão).

#### `core/autostart.py`
- **Responsabilidade**: Integrar com a inicialização do Windows via Registro do Usuário (`HKCU`).
- **Chave de Registro**: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`.
- **Nome do Valor**: `"ProcessHunter"`.
- **Comando Registrado**: `f'"{sys.executable}" "{entrypoint_path}" --minimized'` (inicia com flag que suprime a janela na inicialização).
- **Métodos da classe `WindowsAutostart`**:
  - `is_enabled() -> bool`: Verifica se a chave existe e aponta para a aplicação.
  - `enable(entrypoint_path: str, minimized: bool = True) -> bool`: Cria ou atualiza a entrada no Registro.
  - `disable() -> bool`: Remove a entrada do Registro com segurança.

#### `core/logger.py`
- **Responsabilidade**: Padronizar logs e distribuir eventos para o console da UI e para o arquivo físico de log.
- **Arquivo de Log**: `%APPDATA%\ProcessHunter\processhunter.log` com rotação (`RotatingFileHandler`, max 5MB, 3 backups).
- **Formato**: `yyyy-MM-dd HH:mm:ss - [NÍVEL] Mensagem`.

---

### 3.2 Camada de Interface Gráfica (`ui/`)

#### `ui/main_window.py`
- **Barra Superior**:
  - Indicador de status da Sentinela com badge colorido.
  - Botão `[ ⚡ Caçar Agora ]` com feedback visual imediato.
  - Botão `[ 🛡️ Iniciar / Pausar Sentinela ]`.
- **Painel Central Esquerdo (Alvos)**:
  - Input para inserção manual + botão `[ + Adicionar ]`.
  - Tabela/Lista de alvos: Checkbox (ativo/inativo), Nome, Indicador de instâncias ativas no momento, Botão de excluir.
- **Painel Central Direito (Processos Ativos)**:
  - Campo de busca instantânea (filtro em tempo real) + botão de recarregar.
  - Tabela com PID, Nome e Memória (MB).
  - Botão `[ 🎯 Adicionar aos Alvos ]` para inclusão com um clique.
- **Painel Inferior (Log & Configurações)**:
  - Console de logs coloridos com botão de limpar e abrir arquivo.
  - Checkbox sincronizado: `[x] Iniciar com o Windows`.
  - Spinbox: `Intervalo da Sentinela (segundos)`.
- **Tratamento de Fechamento**: Sobrescrita de `closeEvent` para ocultar a janela e manter a execução na bandeja do sistema quando configurado.

#### `ui/tray.py`
- **Ícone na Bandeja (`QSystemTrayIcon`)**:
  - Menu de contexto:
    - *Abrir ProcessHunter*
    - *Separador*
    - *Caçar Agora*
    - *Pausar / Retomar Sentinela*
    - *Separador*
    - *Sair do ProcessHunter*
  - Notificações balão (Toast) quando processos forem eliminados em segundo plano.

#### `ui/workers.py`
- **`SentinelWorker(QThread)`**:
  - Loop assíncrono que acorda a cada `sentinel_interval_seconds`, consulta alvos ativos no `ConfigManager`, invoca `ProcessHunter.kill_targets()` e emite sinais Qt com os resultados e logs.
  - Interrompível de forma segura via flags de controle.
- **`ProcessScannerWorker(QThread)`**:
  - Varredura de processos em segundo plano para não travar a UI ao clicar em "Atualizar lista de processos ativos".

---

## 4. Tratamento de Exceções e Resiliência

1. **Permissões Administrativas**:
   - Falhas do tipo `psutil.AccessDenied` não derrubam a aplicação. São registradas com mensagem orientando executar o app como Administrador caso o usuário deseje matar processos de outros usuários ou do sistema.
2. **Processos Fantasma**:
   - Erros `psutil.NoSuchProcess` são tratados silenciosamente como processos já encerrados.
3. **Instância Única**:
   - O ponto de entrada `app.py` utiliza `QLockFile` no diretório temporário para impedir que duas instâncias rodem simultaneamente.
4. **Corrupção de Configuração**:
   - Falhas de parse no `config.json` geram backup automático do arquivo corrompido e restauram o arquivo com as configurações padrão.

---

## 5. Estratégia de Testes

Os testes automatizados serão implementados em `tests/` com o executor `pytest`:
- **`test_hunter.py`**:
  - Validação da normalização de nomes de executáveis.
  - Simulação de detecção e encerramento com mocks de `psutil.process_iter` e `psutil.Process`.
  - Validação do comportamento sob `AccessDenied` e `NoSuchProcess`.
- **`test_config.py`**:
  - Testes de carregamento, salvamento, adição, remoção e alternância de alvos.
  - Testes de recuperação de arquivo corrompido.
- **`test_autostart.py`**:
  - Testes de ativação e remoção do registro do Windows utilizando `unittest.mock` para o módulo `winreg`.
