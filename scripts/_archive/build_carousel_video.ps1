# build_carousel_video.ps1 — TheGothicVault Gothic Heels Carousel Video
# Output: 9:16 vertical video, ~15s, Reels/TikTok ready

$SLIDES   = "E:\PROJECTS\thegothicvault\LIBRARY\carousels\shoes-killstar"
$SOUND    = "E:\PROJECTS\thegothicvault\GELEM\BW108-cat-haunt-zipper-top\SOUND\Gothic Industrial\cleanmindsounds_gothic-industrial_main.mp3"
$OUT      = "E:\PROJECTS\thegothicvault\LIBRARY\carousels\shoes-killstar\gothic-heels-reels.mp4"
$W        = 1080
$H        = 1920
$FONT     = "C:\Windows\Fonts\Arial.ttf"  # fallback — replace with Cinzel if installed
$DUR      = 2.8   # seconds per slide
$FADE     = 0.4   # fade transition

# --- Text for each slide ---
$SLIDES_DEF = @(
    @{
        bg    = "$SLIDES\slide-01-hook-bg.png"
        lines = @("GOTHIC HEELS", "DON'T ASK", "PERMISSION.")
        y_start = 700
        fontsize = 90
    },
    @{
        bg    = "$SLIDES\slide-02-bignumber-bg.png"
        lines = @("4", "", "Gothic boots that", "speak before you do.")
        y_start = 600
        fontsize = 300
        subtitle_fontsize = 48
    },
    @{
        bg    = "$SLIDES\01-crux-obscura-boots.png"
        lines = @("THE BOOT IS", "THE SENTENCE.")
        y_start = 160
        fontsize = 72
    },
    @{
        bg    = "$SLIDES\04-gloomed-and-doomed-boots.png"
        lines = @("4 LOOKS.", "ONE DARK UNIVERSE.")
        y_start = 140
        fontsize = 68
    },
    @{
        bg    = "$SLIDES\slide-05-cta-bg.png"
        lines = @("ALL FOUR.", "ONE LINK.", "BIO.")
        y_start = 680
        fontsize = 88
    }
)

# Check FFmpeg
$ffmpeg = "ffmpeg"
try { & $ffmpeg -version 2>&1 | Out-Null }
catch {
    Write-Error "FFmpeg not found. Install: winget install ffmpeg"
    exit 1
}

Write-Host "=== Building Gothic Heels Carousel Video ===" -ForegroundColor Magenta
Write-Host "Output: $OUT"

# --- Step 1: Create each slide as a 2.8s video segment ---
$clips = @()
for ($i = 0; $i -lt $SLIDES_DEF.Count; $i++) {
    $s    = $SLIDES_DEF[$i]
    $clip = "$SLIDES\tmp_clip_$i.mp4"
    $clips += $clip

    $bg = $s.bg
    if (-not (Test-Path $bg)) {
        Write-Warning "Missing: $bg — using black fallback"
        $bg = "color=black:s=${W}x${H}"
    }

    # Build drawtext filters
    $dt = @()
    $y = $s.y_start
    foreach ($line in $s.lines) {
        if ($line -eq "") { $y += 60; continue }
        $fs = if ($s.lines.IndexOf($line) -eq 1 -and $s.fontsize -eq 300) { 300 } else { $s.fontsize }
        $escaped = $line -replace "'", "'\\''" -replace ":", "\\:"
        $dt += "drawtext=fontfile='$FONT':text='$escaped':fontcolor=white:fontsize=$fs:x=(w-text_w)/2:y=${y}:shadowcolor=black:shadowx=3:shadowy=3"
        $y += [int]($fs * 1.2) + 10
    }
    # Add crimson bottom bar
    $dt += "drawbox=y=ih-6:color=0x8B0000@1:width=iw*0.5:height=6:t=fill"
    # Add watermark
    $dt += "drawtext=fontfile='$FONT':text='@THEGOTHICVAULT':fontcolor=0xB8860B:fontsize=28:x=(w-text_w)/2:y=h-60:alpha=0.8"

    $filter = ($dt -join ",") + ",fade=t=in:st=0:d=$FADE,fade=t=out:st=$($DUR - $FADE):d=$FADE"

    Write-Host "Creating clip $($i+1)/5..."
    & $ffmpeg -y -loop 1 -i $bg -vf "scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},$filter" `
        -t $DUR -c:v libx264 -preset fast -pix_fmt yuv420p $clip 2>&1 | Out-Null
    Write-Host "  ✅ clip_$i.mp4"
}

# --- Step 2: Create concat file ---
$concatFile = "$SLIDES\concat.txt"
($clips | ForEach-Object { "file '$_'" }) -join "`n" | Out-File $concatFile -Encoding utf8

# --- Step 3: Concat all clips ---
$rawVideo = "$SLIDES\tmp_raw.mp4"
Write-Host "Concatenating 5 clips..."
& $ffmpeg -y -f concat -safe 0 -i $concatFile -c copy $rawVideo 2>&1 | Out-Null

# --- Step 4: Add music (trim to video length) ---
$totalDur = $DUR * $SLIDES_DEF.Count
Write-Host "Adding Gothic Industrial music ($totalDur s)..."
& $ffmpeg -y -i $rawVideo -i $SOUND `
    -t $totalDur `
    -c:v copy -c:a aac -b:a 192k `
    -shortest `
    $OUT 2>&1 | Out-Null

# --- Cleanup temp files ---
$clips | ForEach-Object { Remove-Item $_ -ErrorAction SilentlyContinue }
Remove-Item $rawVideo -ErrorAction SilentlyContinue
Remove-Item $concatFile -ErrorAction SilentlyContinue

if (Test-Path $OUT) {
    $size = [math]::Round((Get-Item $OUT).Length / 1MB, 1)
    Write-Host "`n✅ VIDEO READY: gothic-heels-reels.mp4 ($size MB)" -ForegroundColor Green
    Write-Host "Path: $OUT"
} else {
    Write-Error "Video not created — check FFmpeg errors above"
}
