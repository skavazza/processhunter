# ==========================================
# processhunter.ps1
# ==========================================

# 1. LISTA DE PROCESSOS
# Adicione ou remova processos aqui, um por linha, SEM vírgula no final.
# Não precisa colocar o ".exe" no final.
# Para adicionar mais de um, separe com vírgula (exceto o último) ou use uma linha por item:
#   "outlook"
#   "teams"
$ProcessosParaEncerrar = @(
    "msedgewebview2d"
    # "outlook"
    # "teams"
    # "spotify"
)

# 2. CONFIGURAÇÃO DE LOG
# O script criará um arquivo de log na mesma pasta onde ele estiver salvo
$PastaDoScript = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$LogFile = Join-Path $PastaDoScript "processhunter_log.txt"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Add-Content -Path $LogFile -Encoding UTF8
}

# 3. EXECUÇÃO
Write-Log "--- Início da execução do ProcessHunter ---"

foreach ($proc in $ProcessosParaEncerrar) {
    # Remove ".exe" caso o usuário tenha colocado, para padronizar a busca
    $nomeLimpo = $proc -replace '\.exe$', ''

    # Busca os processos em execução
    $processosEncontrados = Get-Process -Name $nomeLimpo -ErrorAction SilentlyContinue

    if ($processosEncontrados) {
        foreach ($p in $processosEncontrados) {
            try {
                # Força o encerramento do processo
                Stop-Process -Id $p.Id -Force -ErrorAction Stop
                Write-Log "SUCESSO: Processo '$($p.Name)' (PID: $($p.Id)) encerrado."
            } catch {
                Write-Log "FALHA: Não foi possível encerrar '$($p.Name)' (PID: $($p.Id)). Erro: $_"
            }
        }
    } else {
        Write-Log "INFO: Nenhuma instância de '$nomeLimpo' encontrada em execução."
    }
}

Write-Log "--- Fim da execução do ProcessHunter ---`n"
