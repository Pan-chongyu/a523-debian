param([switch]$Configure)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$tzxNetwork = [ordered]@{ present = $false; ready = $false; configured_now = $false }
try {
    $tzxAdapters = @(Get-NetAdapter | Where-Object {
        $_.MacAddress -eq '02-54-5A-52-00-01' -and $_.InterfaceDescription -like 'UsbNcm*'
    })
    if ($tzxAdapters.Count -gt 1) { throw 'More than one TZX USB network adapter' }
    if ($tzxAdapters.Count -eq 1) {
        $tzxAdapter = $tzxAdapters[0]
        $tzxNetwork.present = $true
        $tzxNetwork.interface_index = $tzxAdapter.ifIndex
        $tzxNetwork.interface_name = $tzxAdapter.Name
        $tzxNetwork.status = "$($tzxAdapter.Status)"
        $tzxAddresses = @(Get-NetIPAddress -InterfaceIndex $tzxAdapter.ifIndex -AddressFamily IPv4)
        $tzxExpected = @($tzxAddresses | Where-Object { $_.IPAddress -eq '192.168.77.1' -and $_.PrefixLength -eq 30 })
        if ($Configure -and $tzxExpected.Count -eq 0) {
            New-NetIPAddress -InterfaceIndex $tzxAdapter.ifIndex -IPAddress 192.168.77.1 -PrefixLength 30 | Out-Null
            $tzxNetwork.configured_now = $true
            $tzxAddresses = @(Get-NetIPAddress -InterfaceIndex $tzxAdapter.ifIndex -AddressFamily IPv4)
            $tzxExpected = @($tzxAddresses | Where-Object { $_.IPAddress -eq '192.168.77.1' -and $_.PrefixLength -eq 30 })
        }
        $tzxNetwork.addresses = @($tzxAddresses | ForEach-Object { "$($_.IPAddress)/$($_.PrefixLength)" })
        $tzxNetwork.ready = $tzxExpected.Count -eq 1
    }
} catch {
    $tzxNetwork.error = $_.Exception.Message
}
$tzxNetwork | ConvertTo-Json -Depth 4 -Compress
