param()

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$installerProject = Join-Path $PSScriptRoot 'Cthulu.Installer.wixproj'
$wizardScript = Join-Path $PSScriptRoot 'cthulu_first_run_setup.ps1'
$launcherSource = Join-Path $PSScriptRoot 'CthuluLauncher.cs'
$distRoot = Join-Path $PSScriptRoot 'dist'
$buildRoot = Join-Path $env:TEMP ('cthulu-msi-' + [guid]::NewGuid().ToString('N'))
$payloadRoot = Join-Path $buildRoot 'payload'

function Test-ExcludedPayloadPath {
    param([string]$RelativePath)

    $normalized = $RelativePath.Replace('\', '/')
    $segments = @($normalized.Split('/'))
    $excludedDirectories = @(
        '.archive', '.git', '.github', '.pytest_cache', '.venv', '__pycache__',
        'build', 'data', 'dist', 'installer', 'logs', 'node_modules', 'resource_aggregator',
        'test_vectors_new', 'tests', 'venv'
    )
    foreach ($segment in $segments) {
        if ($excludedDirectories -contains $segment) {
            return $true
        }
    }

    $leaf = $segments[-1]
    if ($leaf -match '^(config\.json|config_multi\.json|\.env(?:\..*)?)$') {
        return $true
    }
    if ($leaf -match '\.(db|sqlite|sqlite3|sqp|log|msi|exe|pyc|pyd|zip|bin|key|pem|p12)$') {
        return $true
    }
    if ($leaf -like '.tmp_*' -or $leaf -like '*.tmp' -or $leaf -like '*.temp') {
        return $true
    }
    return $false
}

# Explicit components provide HKCU keypaths and uninstall entries for harvested directories.
function Get-PayloadHash {
    param([Parameter(Mandatory = $true)][string]$Value)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Value))
        return [System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}

function New-PayloadManifest {
    param(
        [Parameter(Mandatory = $true)][string]$PayloadRoot,
        [Parameter(Mandatory = $true)][string]$ManifestPath
    )

    $payloadRootFullPath = (Get-Item -LiteralPath $PayloadRoot).FullName.TrimEnd([char]92, [char]47)
    $payloadFiles = @(Get-ChildItem -LiteralPath $payloadRootFullPath -Recurse -File -Force |
        Where-Object { $_.Name -ne 'CthuluLauncher.exe' } |
        Sort-Object FullName)
    if ($payloadFiles.Count -eq 0) {
        throw 'The staged application payload contains no files for the MSI.'
    }

    $filesByDirectory = @{}
    $directoryPaths = @{}
    $relativePaths = @{}
    foreach ($file in $payloadFiles) {
        $relativePath = $file.FullName.Substring($payloadRootFullPath.Length).TrimStart([char]92, [char]47).Replace('\', '/')
        $relativePaths[$file.FullName] = $relativePath
        $parts = @($relativePath.Split('/'))
        $directoryPath = ''
        if ($parts.Length -gt 1) {
            $directoryPath = [string]::Join('/', $parts[0..($parts.Length - 2)])
        }

        if (-not $filesByDirectory.ContainsKey($directoryPath)) {
            $filesByDirectory[$directoryPath] = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
        }
        $filesByDirectory[$directoryPath].Add($file)

        for ($partCount = 1; $partCount -lt $parts.Length; $partCount++) {
            $directoryPath = [string]::Join('/', $parts[0..($partCount - 1)])
            $directoryPaths[$directoryPath] = $true
        }
    }

    $namespace = 'http://wixtoolset.org/schemas/v4/wxs'
    $document = New-Object System.Xml.XmlDocument
    $document.XmlResolver = $null
    $declaration = $document.CreateXmlDeclaration('1.0', 'UTF-8', $null)
    [void]$document.AppendChild($declaration)
    $wix = $document.CreateElement('Wix', $namespace)
    [void]$document.AppendChild($wix)
    $fragment = $document.CreateElement('Fragment', $namespace)
    [void]$wix.AppendChild($fragment)
    $directoryRef = $document.CreateElement('DirectoryRef', $namespace)
    $directoryRef.SetAttribute('Id', 'INSTALLFOLDER')
    [void]$fragment.AppendChild($directoryRef)

    $directoryNodes = @{}
    $directoryNodes[''] = $directoryRef
    $directoryIds = @{}
    $orderedDirectoryPaths = @($directoryPaths.Keys | Sort-Object { ($_ -split '/').Length }, { $_ })
    foreach ($directoryPath in $orderedDirectoryPaths) {
        $separatorIndex = $directoryPath.LastIndexOf('/')
        if ($separatorIndex -ge 0) {
            $parentPath = $directoryPath.Substring(0, $separatorIndex)
            $directoryName = $directoryPath.Substring($separatorIndex + 1)
        } else {
            $parentPath = ''
            $directoryName = $directoryPath
        }

        $directoryId = 'dir_' + (Get-PayloadHash -Value ('directory|' + $directoryPath.ToLowerInvariant())).Substring(0, 24)
        $directoryNode = $document.CreateElement('Directory', $namespace)
        $directoryNode.SetAttribute('Id', $directoryId)
        $directoryNode.SetAttribute('Name', $directoryName)
        [void]$directoryNodes[$parentPath].AppendChild($directoryNode)
        $directoryNodes[$directoryPath] = $directoryNode
        $directoryIds[$directoryPath] = $directoryId
    }

    $componentGroup = $document.CreateElement('ComponentGroup', $namespace)
    $componentGroup.SetAttribute('Id', 'PayloadFiles')
    $componentIds = New-Object 'System.Collections.Generic.List[string]'
    foreach ($directoryPath in @('') + $orderedDirectoryPaths) {
        $directFiles = @()
        if ($filesByDirectory.ContainsKey($directoryPath)) {
            $directFiles = @($filesByDirectory[$directoryPath] | Sort-Object { $relativePaths[$_.FullName] })
        }
        if ($directoryPath -eq '' -and $directFiles.Count -eq 0) {
            continue
        }

        $componentFilePaths = @($directFiles | ForEach-Object { $relativePaths[$_.FullName].ToLowerInvariant() } | Sort-Object)
        $componentIdentity = 'component|' + $directoryPath.ToLowerInvariant() + '|' + ($componentFilePaths -join '|')
        $componentHash = Get-PayloadHash -Value $componentIdentity
        $componentId = 'cmp_' + $componentHash.Substring(0, 24)
        $guidHash = $componentHash.Substring(0, 32)
        $componentGuid = '{0}-{1}-{2}-{3}-{4}' -f `
            $guidHash.Substring(0, 8), $guidHash.Substring(8, 4), $guidHash.Substring(12, 4), `
            $guidHash.Substring(16, 4), $guidHash.Substring(20, 12)

        $component = $document.CreateElement('Component', $namespace)
        $component.SetAttribute('Id', $componentId)
        $component.SetAttribute('Guid', $componentGuid)
        $registryValue = $document.CreateElement('RegistryValue', $namespace)
        $registryValue.SetAttribute('Root', 'HKCU')
        $registryValue.SetAttribute('Key', 'Software\Cthulu\Installer')
        $registryValue.SetAttribute('Name', 'Payload_' + $componentHash.Substring(0, 24))
        $registryValue.SetAttribute('Type', 'integer')
        $registryValue.SetAttribute('Value', '1')
        $registryValue.SetAttribute('KeyPath', 'yes')
        [void]$component.AppendChild($registryValue)

        foreach ($file in $directFiles) {
            $relativePath = $relativePaths[$file.FullName]
            $fileHash = Get-PayloadHash -Value ('file|' + $relativePath.ToLowerInvariant())
            $fileNode = $document.CreateElement('File', $namespace)
            $fileNode.SetAttribute('Id', 'file_' + $fileHash.Substring(0, 24))
            $fileNode.SetAttribute('Source', $file.FullName)
            $fileNode.SetAttribute('KeyPath', 'no')
            [void]$component.AppendChild($fileNode)
        }

        if ($directoryPath -ne '') {
            $directoryHash = Get-PayloadHash -Value ('remove|' + $directoryPath.ToLowerInvariant())
            $removeFolder = $document.CreateElement('RemoveFolder', $namespace)
            $removeFolder.SetAttribute('Id', 'remove_' + $directoryHash.Substring(0, 24))
            $removeFolder.SetAttribute('Directory', $directoryIds[$directoryPath])
            $removeFolder.SetAttribute('On', 'uninstall')
            [void]$component.AppendChild($removeFolder)
        }

        [void]$directoryNodes[$directoryPath].AppendChild($component)
        $componentIds.Add($componentId)
    }

    foreach ($componentId in $componentIds) {
        $componentRef = $document.CreateElement('ComponentRef', $namespace)
        $componentRef.SetAttribute('Id', $componentId)
        [void]$componentGroup.AppendChild($componentRef)
    }
    [void]$fragment.AppendChild($componentGroup)

    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Indent = $true
    $settings.Encoding = [System.Text.UTF8Encoding]::new($false)
    $writer = [System.Xml.XmlWriter]::Create($ManifestPath, $settings)
    try {
        $document.Save($writer)
    } finally {
        $writer.Dispose()
    }
}

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is required to build the MSI from a clean, tracked-file payload.'
    }
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
        throw 'The .NET 8 SDK is required. Install it, then rerun installer\Build-Msi.ps1.'
    }
    if (-not (Test-Path -LiteralPath $wizardScript -PathType Leaf)) {
        throw "The first-run setup script is missing: $wizardScript"
    }
    if (-not (Test-Path -LiteralPath $launcherSource -PathType Leaf)) {
        throw "The launcher source is missing: $launcherSource"
    }

    New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null
    $payloadRootFullPath = (Get-Item -LiteralPath $payloadRoot).FullName.TrimEnd([char]92, [char]47)
    $trackedFiles = @(& git -C $repoRoot ls-files)
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not list tracked repository files for the MSI payload.'
    }

    $copiedCount = 0
    foreach ($relativePath in $trackedFiles) {
        if (Test-ExcludedPayloadPath -RelativePath $relativePath) {
            continue
        }
        $sourcePath = Join-Path $repoRoot ($relativePath.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            continue
        }
        $destinationPath = Join-Path $payloadRoot ($relativePath.Replace('/', '\'))
        $destinationDirectory = Split-Path -Parent $destinationPath
        if (-not (Test-Path -LiteralPath $destinationDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        }
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
        $copiedCount++
    }

    $wizardDestination = Join-Path $payloadRoot 'installer\cthulu_first_run_setup.ps1'
    New-Item -ItemType Directory -Path (Split-Path -Parent $wizardDestination) -Force | Out-Null
    Copy-Item -LiteralPath $wizardScript -Destination $wizardDestination

    $launcherDestination = Join-Path $payloadRoot 'CthuluLauncher.exe'
    $compilerCandidates = @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    )
    $compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($compiler) {
        & $compiler /nologo /target:winexe "/out:$launcherDestination" /reference:System.dll /reference:System.Windows.Forms.dll $launcherSource
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not compile the Windows launcher executable.'
        }
    } else {
        $source = Get-Content -LiteralPath $launcherSource -Raw -ErrorAction Stop
        Add-Type -TypeDefinition $source -Language CSharp -OutputAssembly $launcherDestination `
            -OutputType WindowsApplication -ReferencedAssemblies 'System.Windows.Forms.dll'
    }

    $unsafePayloadFiles = @(Get-ChildItem -LiteralPath $payloadRoot -Recurse -File | Where-Object {
        $relative = $_.FullName.Substring($payloadRootFullPath.Length).TrimStart([char]92, [char]47).Replace([char]92, '/')
        $relative -notin @('CthuluLauncher.exe', 'installer/cthulu_first_run_setup.ps1') -and
            (Test-ExcludedPayloadPath -RelativePath $relative)
    })
    if ($unsafePayloadFiles.Count -gt 0) {
        throw ('The staged payload contains excluded local data: ' + (($unsafePayloadFiles | ForEach-Object { $_.Name }) -join ', '))
    }

    $payloadManifest = Join-Path $buildRoot 'PayloadFiles.wxs'
    New-PayloadManifest -PayloadRoot $payloadRoot -ManifestPath $payloadManifest

    if (-not (Test-Path -LiteralPath $distRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
    }
    $buildArguments = @(
        'build',
        $installerProject,
        '--configuration',
        'Release',
        '--output',
        $distRoot,
        "--property:PayloadRoot=$payloadRoot",
        "--property:PayloadManifest=$payloadManifest"
    )
    & dotnet @buildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "WiX failed to build the MSI (exit code $LASTEXITCODE)."
    }

    $msiPath = Join-Path $distRoot 'Cthulu-Setup.msi'
    if (-not (Test-Path -LiteralPath $msiPath -PathType Leaf)) {
        throw "WiX completed without producing the expected MSI: $msiPath"
    }

    $msi = Get-Item -LiteralPath $msiPath
    Write-Output "Staged $copiedCount tracked application files; ignored local credentials, runtime configs, databases, logs, tests, and nested repositories."
    Write-Output "Created $($msi.FullName) ($([Math]::Round($msi.Length / 1MB, 1)) MB)."
} finally {
    if (Test-Path -LiteralPath $buildRoot -PathType Container) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force
    }
}
