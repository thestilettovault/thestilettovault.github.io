# run_carousels.ps1 — TheGothicVault carousel generation
# Run from: E:\PROJECTS\thegothicvault\scripts\
# Prereq: higgsfield auth login

$LIB    = "E:\PROJECTS\thegothicvault\LIBRARY"
$OUT    = "E:\PROJECTS\thegothicvault\LIBRARY\carousels"
$DNA    = "dark femme glam, chiaroscuro candlelight, aged stone, crimson and black, editorial gothic fashion, TheGothicVault"

$jobs = @(
    @{
        name   = "shoes-killstar"
        prompt = "gothic boots collection Killstar, $DNA, IG carousel 4:5"
        images = @(
            "$LIB\shoes\killstar\crux-obscura-boots.jpg",
            "$LIB\shoes\killstar\broom-rider-boots.jpg",
            "$LIB\shoes\killstar\raven-pointed-toe-bootie.jpg",
            "$LIB\shoes\killstar\gloomed-and-doomed-boots.jpg"
        )
        count  = 4
    },
    @{
        name   = "shoes-tuk"
        prompt = "gothic creeper shoes TUK collection, $DNA, punk editorial IG carousel 4:5"
        images = @(
            "$LIB\shoes\tuk\1970-creeper-black-leather.jpg",
            "$LIB\shoes\tuk\1970-creeper-black-white.jpg",
            "$LIB\shoes\tuk\creeper-sneaker-stacked-suede.jpg",
            "$LIB\shoes\tuk\viva-high-stud-sandal.jpg"
        )
        count  = 4
    },
    @{
        name   = "clothing-killstar"
        prompt = "gothic fashion Killstar corset dress, $DNA, editorial IG carousel 4:5"
        images = @(
            "$LIB\clothing\killstar\midnight-vale-corset-top.jpg",
            "$LIB\clothing\killstar\kihilist-nova-maxi-dress.jpg"
        )
        count  = 2
    },
    @{
        name   = "clothing-darkinlove"
        prompt = "gothic alternative dresses Dark In Love, $DNA, editorial IG carousel 4:5"
        images = @(
            "$LIB\clothing\darkinlove\dw488-rebel-doll-dress.jpg",
            "$LIB\clothing\darkinlove\kw236-plaid-frilly-dress.jpg"
        )
        count  = 2
    },
    @{
        name   = "accessories"
        prompt = "gothic accessories collection Killstar Lip Service, $DNA, editorial product IG carousel 4:5"
        images = @(
            "$LIB\accessories\lip-service-bondage-cuff.jpg",
            "$LIB\accessories\lip-service-dagger-suspenders.jpg",
            "$LIB\accessories\killstar-nova-handbag.jpg"
        )
        count  = 3
    }
)

foreach ($job in $jobs) {
    Write-Host "`n=== $($job.name) ($($job.count) slides) ==="

    $imgFlags = ($job.images | ForEach-Object { "--image `"$_`"" }) -join " "
    $cmd = "higgsfield product-photoshoot create --mode social_carousel --prompt `"$($job.prompt)`" $imgFlags --count $($job.count) --aspect_ratio 4:5"

    Write-Host "Running: $cmd"
    $result = Invoke-Expression $cmd 2>&1
    Write-Host $result

    # Save URLs to file
    $outFile = "$OUT\$($job.name)\urls.txt"
    $result | Out-File -FilePath $outFile -Encoding utf8
    Write-Host "Saved → $outFile"
}

Write-Host "`n=== ALL DONE ==="
