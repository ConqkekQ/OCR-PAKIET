# Okno-atrapa jak Comarch ERP XL: główne okno programu z dokumentami (MDI) w środku.
# Użycie: pwsh tests/okno_mdi.ps1 -Obraz syn.png [-AktywnaLista]
param(
    [Parameter(Mandatory = $true)][string]$Obraz,
    [switch]$AktywnaLista
)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$main = New-Object System.Windows.Forms.Form
$main.Text = "Zamówienia [Test] - Comarch ERP XL"
$main.IsMdiContainer = $true
$main.Width = 1700
$main.Height = 820
$main.StartPosition = "Manual"
$main.Location = New-Object System.Drawing.Point(0, 0)

$lista = New-Object System.Windows.Forms.Form
$lista.Text = "Lista zamówień sprzedaży"
$lista.MdiParent = $main
$lista.Width = 900; $lista.Height = 500

$zs = New-Object System.Windows.Forms.Form
$zs.Text = "Zamówienie sprzedaży [ZS-1/26/TEST] - zostanie dodane"
$zs.MdiParent = $main
$zs.Width = 1560; $zs.Height = 640
$pic = New-Object System.Windows.Forms.PictureBox
$pic.Image = [System.Drawing.Image]::FromFile((Resolve-Path $Obraz))
$pic.Dock = "Fill"
$zs.Controls.Add($pic)

$main.Add_Shown({
    $lista.Show()
    $zs.Show()
    $zs.Location = New-Object System.Drawing.Point(0, 0)
    if ($AktywnaLista) { $lista.Activate() } else { $zs.Activate() }
    $main.Activate()
})
[System.Windows.Forms.Application]::Run($main)
