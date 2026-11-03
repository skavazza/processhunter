BeforeAll {
    $script:OriginalScript = Join-Path $PSScriptRoot 'processhunter.ps1'

    # Gera uma cópia do script no TestDrive com a lista de processos customizada
    function New-TestScript {
        param([string[]]$Processes = @())

        $content = Get-Content $script:OriginalScript -Raw
        $items   = ($Processes | ForEach-Object { "`"$_`"" }) -join ','
        $novaLista = "`$ProcessosParaEncerrar = @($items)"

        $content = [regex]::Replace(
            $content,
            '(?s)\$ProcessosParaEncerrar\s*=\s*@\(.*?\r?\n\)',
            { param($m) $novaLista }
        )

        $path = Join-Path $TestDrive 'processhunter.ps1'
        Set-Content -Path $path -Value $content -Encoding UTF8
        return $path
    }

    function Get-LogContent {
        $log = Join-Path $TestDrive 'processhunter_log.txt'
        if (Test-Path $log) { Get-Content $log -Raw } else { '' }
    }
}

Describe 'processhunter.ps1' {

    BeforeEach {
        $log = Join-Path $TestDrive 'processhunter_log.txt'
        if (Test-Path $log) { Remove-Item $log -Force }

        Mock Get-Process { $null }
        Mock Stop-Process { }
    }

    Context 'Sintaxe do script original' {
        It 'não possui erros de parse' {
            $errors = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile(
                $script:OriginalScript, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }
    }

    Context 'Fluxo principal' {
        It 'encerra o processo encontrado com -Force e registra SUCESSO' {
            Mock Get-Process { [pscustomobject]@{ Name = 'msedgewebview2d'; Id = 101 } }

            . (New-TestScript -Processes 'msedgewebview2d')

            Should -Invoke Stop-Process -Times 1 -Exactly -ParameterFilter {
                $Id -eq 101 -and $Force -eq $true
            }
            Get-LogContent | Should -BeLike "*SUCESSO: Processo 'msedgewebview2d' (PID: 101) encerrado.*"
        }

        It 'encerra todas as instâncias de um mesmo processo' {
            Mock Get-Process {
                [pscustomobject]@{ Name = 'msedgewebview2d'; Id = 101 }
                [pscustomobject]@{ Name = 'msedgewebview2d'; Id = 102 }
                [pscustomobject]@{ Name = 'msedgewebview2d'; Id = 103 }
            }

            . (New-TestScript -Processes 'msedgewebview2d')

            Should -Invoke Stop-Process -Times 3 -Exactly
            $log = Get-LogContent
            $log | Should -BeLike '*(PID: 101) encerrado*'
            $log | Should -BeLike '*(PID: 102) encerrado*'
            $log | Should -BeLike '*(PID: 103) encerrado*'
        }

        It 'processa vários nomes da lista, tratando cada um separadamente' {
            Mock Get-Process { [pscustomobject]@{ Name = 'outlook'; Id = 201 } } `
                -ParameterFilter { $Name -eq 'outlook' }
            Mock Get-Process { [pscustomobject]@{ Name = 'teams'; Id = 202 } } `
                -ParameterFilter { $Name -eq 'teams' }

            . (New-TestScript -Processes 'outlook', 'teams')

            Should -Invoke Stop-Process -Times 1 -Exactly -ParameterFilter { $Id -eq 201 }
            Should -Invoke Stop-Process -Times 1 -Exactly -ParameterFilter { $Id -eq 202 }
        }

        It 'sempre escreve as linhas de início e fim no log' {
            . (New-TestScript -Processes 'qualquer')

            $log = Get-LogContent
            $log | Should -BeLike '*--- Início da execução do ProcessHunter ---*'
            $log | Should -BeLike '*--- Fim da execução do ProcessHunter ---*'
        }

        It 'prefixa cada linha do log com timestamp no formato yyyy-MM-dd HH:mm:ss' {
            . (New-TestScript -Processes 'qualquer')

            $linhas = (Get-LogContent) -split "\r?\n" | Where-Object { $_.Trim() }
            foreach ($linha in $linhas) {
                $linha | Should -Match '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - '
            }
        }
    }

    Context 'Casos de borda' {
        It 'registra INFO e não chama Stop-Process quando o processo não está rodando' {
            . (New-TestScript -Processes 'naoexiste')

            Should -Invoke Stop-Process -Times 0 -Exactly
            Get-LogContent | Should -BeLike "*INFO: Nenhuma instância de 'naoexiste' encontrada em execução.*"
        }

        It 'mistura corretamente processos encontrados e não encontrados' {
            Mock Get-Process { [pscustomobject]@{ Name = 'a'; Id = 1 } } `
                -ParameterFilter { $Name -eq 'a' }
            Mock Get-Process { $null } -ParameterFilter { $Name -eq 'b' }

            . (New-TestScript -Processes 'a', 'b')

            $log = Get-LogContent
            $log | Should -BeLike "*SUCESSO: Processo 'a'*"
            $log | Should -BeLike "*INFO: Nenhuma instância de 'b'*"
            Should -Invoke Stop-Process -Times 1 -Exactly
        }

        It 'lista vazia: só escreve início e fim, sem consultar processos' {
            . (New-TestScript -Processes @())

            Should -Invoke Get-Process -Times 0 -Exactly
            Should -Invoke Stop-Process -Times 0 -Exactly
            $log = Get-LogContent
            $log | Should -BeLike '*Início da execução*'
            $log | Should -BeLike '*Fim da execução*'
            $log | Should -Not -BeLike '*INFO:*'
        }

        It 'remove o sufixo ".exe" antes de buscar o processo' {
            . (New-TestScript -Processes 'notepad.exe')

            Should -Invoke Get-Process -Times 1 -Exactly -ParameterFilter { $Name -eq 'notepad' }
            Get-LogContent | Should -BeLike "*Nenhuma instância de 'notepad'*"
        }

        It 'remove ".EXE" em maiúsculas (comparação case-insensitive)' {
            . (New-TestScript -Processes 'NOTEPAD.EXE')

            Should -Invoke Get-Process -Times 1 -Exactly -ParameterFilter { $Name -eq 'NOTEPAD' }
        }

        It 'não remove "exe" quando não é a extensão no final do nome' {
            . (New-TestScript -Processes 'executor')

            Should -Invoke Get-Process -Times 1 -Exactly -ParameterFilter { $Name -eq 'executor' }
        }

        It 'consulta Get-Process com -ErrorAction SilentlyContinue' {
            . (New-TestScript -Processes 'qualquer')

            Should -Invoke Get-Process -Times 1 -Exactly -ParameterFilter {
                $ErrorAction -eq 'SilentlyContinue'
            }
        }
    }

    Context 'Tratamento de erros' {
        It 'registra FALHA com a mensagem de erro quando Stop-Process lança exceção' {
            Mock Get-Process { [pscustomobject]@{ Name = 'travado'; Id = 301 } }
            Mock Stop-Process { throw 'Acesso negado' }

            { . (New-TestScript -Processes 'travado') } | Should -Not -Throw

            $log = Get-LogContent
            $log | Should -BeLike "*FALHA: Não foi possível encerrar 'travado' (PID: 301)*"
            $log | Should -BeLike '*Acesso negado*'
            $log | Should -Not -BeLike '*SUCESSO*'
        }

        It 'continua para as próximas instâncias após uma falha' {
            Mock Get-Process {
                [pscustomobject]@{ Name = 'x'; Id = 401 }
                [pscustomobject]@{ Name = 'x'; Id = 402 }
            }
            Mock Stop-Process { throw 'Acesso negado' } -ParameterFilter { $Id -eq 401 }
            Mock Stop-Process { }                        -ParameterFilter { $Id -eq 402 }

            . (New-TestScript -Processes 'x')

            $log = Get-LogContent
            $log | Should -BeLike '*FALHA*(PID: 401)*'
            $log | Should -BeLike "*SUCESSO: Processo 'x' (PID: 402) encerrado.*"
        }

        It 'continua para o próximo nome da lista após uma falha' {
            Mock Get-Process { [pscustomobject]@{ Name = 'a'; Id = 501 } } `
                -ParameterFilter { $Name -eq 'a' }
            Mock Get-Process { [pscustomobject]@{ Name = 'b'; Id = 502 } } `
                -ParameterFilter { $Name -eq 'b' }
            Mock Stop-Process { throw 'Erro' } -ParameterFilter { $Id -eq 501 }

            . (New-TestScript -Processes 'a', 'b')

            Should -Invoke Stop-Process -Times 1 -Exactly -ParameterFilter { $Id -eq 502 }
            Get-LogContent | Should -BeLike "*SUCESSO: Processo 'b'*"
        }
    }

    Context 'Persistência do log' {
        It 'acrescenta ao log existente em vez de sobrescrever' {
            $script = New-TestScript -Processes 'qualquer'

            . $script
            . $script

            $ocorrencias = ([regex]::Matches((Get-LogContent), 'Início da execução')).Count
            $ocorrencias | Should -Be 2
        }

        It 'grava o log na mesma pasta do script' {
            . (New-TestScript -Processes 'qualquer')

            Test-Path (Join-Path $TestDrive 'processhunter_log.txt') | Should -BeTrue
        }
    }
}