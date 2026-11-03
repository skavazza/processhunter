# ProcessHunter GUI (PySide6)

O **ProcessHunter** é uma aplicação desktop desenvolvida em Python e PySide6 (Qt 6) projetada para encerrar automaticamente processos indesejados no Windows sob demanda ou através de um monitor contínuo em segundo plano (Modo Sentinela).

---

## 🚀 Principais Recursos

- **Modo Híbrido**:
  - **⚡ Caçada Manual**: Encerra instantaneamente todos os processos alvos configurados com um clique.
  - **🛡️ Modo Sentinela**: Monitora o sistema em segundo plano (com intervalo configurável de 1 a 300 segundos) e encerra os alvos assim que forem detectados.
- **Gerenciamento de Alvos**:
  - **Explorador de Processos Ativos**: Busca em tempo real com filtro por nome e PID, permitindo adicionar qualquer processo em execução com 1 clique.
  - **Inserção Manual**: Permite cadastrar executáveis mesmo quando não estiverem em execução no momento (com normalização automática de nomes e remoção de `.exe`).
  - **Controle Individual**: Ative ou desative regras com checkboxes sem precisar excluí-las.
- **Integração com o Windows**:
  - **Iniciar com o Windows**: Adiciona ou remove a chave do Registro (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) sem necessidade de permissões de Administrador.
  - **Bandeja do Sistema (System Tray)**: Permite minimizar ao fechar a janela, mantendo a vigilância silenciosa. Menu rápido para caçar, pausar/retomar sentinela e sair.
  - **Notificações Nativas**: Notifica o usuário na área de trabalho quando alvos são eliminados.
- **Resiliência e Engenharia Limpa**:
  - Camada de regras e sistema de processos (`core/`) 100% desacoplada da interface gráfica (`ui/`).
  - Threads em segundo plano (`QThread`) para evitar qualquer congelamento na interface.
  - Tratamento de exceções nativas de sistema operacional (`AccessDenied`, `NoSuchProcess`).
  - Proteção de instância única (`Single Instance`) via `QLockFile`.

---

## 📂 Estrutura do Projeto

```text
processhunter/
├── core/
│   ├── config.py         # Persistência e gerenciamento de JSON
│   ├── hunter.py         # Motor nativo de caça via psutil
│   ├── autostart.py      # Gerenciador de Registro HKCU Run do Windows
│   └── logger.py         # Logger rotativo e emissor de eventos para a UI
├── ui/
│   ├── components/
│   │   ├── process_table.py # Tabela de processos ativos com busca
│   │   └── target_list.py   # Lista de alvos configuráveis
│   ├── main_window.py    # Janela principal
│   ├── tray.py           # Ícone e menu de contexto da bandeja
│   └── workers.py        # QThreads da Sentinela e do Scanner
├── tests/                # Suíte completa de testes automatizados com pytest
├── app.py                # Ponto de entrada da aplicação
└── requirements.txt      # Dependências (PySide6, psutil, pytest)
```

---

## 🛠️ Instalação e Execução

### Pré-requisitos
- Windows 10 ou 11
- Python 3.10 ou superior

### 1. Instalar dependências
No terminal na pasta do projeto:
```bash
pip install -r requirements.txt
```

### 2. Executar a aplicação
```bash
python app.py
```

Para iniciar silenciosamente na bandeja (modo utilizado pelo autostart do Windows):
```bash
python app.py --minimized
```

### 3. Executar os testes automatizados
```bash
pytest -v
```
