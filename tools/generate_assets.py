"""tools/generate_assets.py — генератор иконок (ICO/PNG) и звуков (WAV) для zapret-simple."""
import math
import os
import struct
import wave

from PIL import Image, ImageDraw, ImageFilter

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
SOUNDS_DIR = os.path.join(ASSETS_DIR, "sounds")


def generate_icons() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    size = 256
    # 1. Base image with transparent background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient background circle/shield shape
    # Deep Cyber Navy / Dark Blue palette with glowing cyan/neon border
    center = size // 2
    radius = 112

    # Outer glow
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(
        [center - radius - 6, center - radius - 6, center + radius + 6, center + radius + 6],
        fill=(56, 189, 248, 70),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    img.alpha_composite(glow)

    # Main dark rounded background
    for r in range(radius, 0, -1):
        ratio = r / radius
        # Gradient from #1e293b (center) to #0f172a (edges)
        red = int(15 + (30 - 15) * ratio)
        green = int(23 + (41 - 23) * ratio)
        blue = int(42 + (59 - 42) * ratio)
        draw.ellipse([center - r, center - r, center + r, center + r], fill=(red, green, blue, 255))

    # Outer ring: Neon Cyan / Electric Blue border (#38bdf8)
    draw.ellipse(
        [center - radius, center - radius, center + radius, center + radius],
        outline=(56, 189, 248, 240),
        width=5,
    )

    # Stylized Zapret Lightning / Shield / Bypass symbol
    # Centered modern polygon: Lightning bolt with cyber aesthetic
    bolt_pts = [
        (138, 44),   # top peak
        (88, 136),   # mid left
        (124, 136),  # mid inner
        (104, 212),  # bottom tip
        (172, 114),  # mid right
        (134, 114),  # mid inner right
    ]

    # Inner glow for lightning
    bolt_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bolt_glow)
    bg_draw.polygon(bolt_pts, fill=(56, 189, 248, 140))
    bolt_glow = bolt_glow.filter(ImageFilter.GaussianBlur(6))
    img.alpha_composite(bolt_glow)

    # Main sharp lightning: gradient / cyan-to-white
    draw.polygon(bolt_pts, fill=(96, 165, 250, 255))

    # Highlight core of the bolt
    core_pts = [
        (136, 52),
        (96, 134),
        (126, 134),
        (110, 200),
        (164, 116),
        (132, 116),
    ]
    draw.polygon(core_pts, fill=(240, 249, 255, 230))

    # Save PNG
    png_path = os.path.join(ASSETS_DIR, "app.png")
    img.save(png_path, "PNG")
    print(f"Saved {png_path}")

    # Generate ICO with multiple standard Windows sizes
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path = os.path.join(ASSETS_DIR, "app.ico")
    img.save(ico_path, format="ICO", sizes=ico_sizes)
    print(f"Saved {ico_path} with sizes {ico_sizes}")


def _write_pcm_wav(path: str, samples: list[float], sample_rate: int = 44100) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as wav_file:
        wav_file.setnchannels(1)      # Mono
        wav_file.setsampwidth(2)      # 16-bit
        wav_file.setframerate(sample_rate)
        # Convert float (-1.0 .. 1.0) to 16-bit signed integer (-32767 .. 32767)
        raw_frames = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            val = int(clamped * 32767.0)
            raw_frames.extend(struct.pack("<h", val))
        wav_file.writeframes(raw_frames)
    print(f"Saved sound: {path} ({len(samples)} samples, {len(samples)/sample_rate:.2f}s)")


def generate_sounds() -> None:
    sample_rate = 44100

    # 1. connect.wav (Service start / connected)
    # Uplifting two-tone harmonic major chime: C5 (523 Hz) -> E5 (659 Hz) -> G5 (784 Hz)
    duration = 0.35
    total_samples = int(sample_rate * duration)
    samples = []
    for i in range(total_samples):
        t = i / sample_rate
        # Envelope: fast attack (5ms), exponential decay
        env = math.exp(-6.0 * t) if t > 0.005 else (t / 0.005)
        # Two phases: tone 1 (0..0.12s) then chord (0.12..end)
        if t < 0.12:
            freq1 = 523.25  # C5
            freq2 = 1046.5  # C6 overtone
            sig = 0.7 * math.sin(2 * math.pi * freq1 * t) + 0.2 * math.sin(2 * math.pi * freq2 * t)
        else:
            t2 = t - 0.12
            env2 = math.exp(-7.0 * t2) if t2 > 0.005 else (t2 / 0.005)
            freq1 = 659.25  # E5
            freq2 = 783.99  # G5
            freq3 = 1046.50 # C6
            sig = (
                0.45 * math.sin(2 * math.pi * freq1 * t2)
                + 0.45 * math.sin(2 * math.pi * freq2 * t2)
                + 0.20 * math.sin(2 * math.pi * freq3 * t2)
            ) * env2
        samples.append(sig * env * 0.75)
    _write_pcm_wav(os.path.join(SOUNDS_DIR, "connect.wav"), samples, sample_rate)

    # 2. disconnect.wav (Service stopped)
    # Gentle descending tone: G5 (784 Hz) -> C5 (523 Hz)
    duration = 0.30
    total_samples = int(sample_rate * duration)
    samples = []
    for i in range(total_samples):
        t = i / sample_rate
        env = math.exp(-8.0 * t) if t > 0.005 else (t / 0.005)
        if t < 0.10:
            freq = 783.99  # G5
            sig = 0.7 * math.sin(2 * math.pi * freq * t)
        else:
            t2 = t - 0.10
            env2 = math.exp(-9.0 * t2) if t2 > 0.005 else (t2 / 0.005)
            freq = 523.25  # C5
            sig = 0.7 * math.sin(2 * math.pi * freq * t2) * env2
        samples.append(sig * env * 0.70)
    _write_pcm_wav(os.path.join(SOUNDS_DIR, "disconnect.wav"), samples, sample_rate)

    # 3. alert.wav (Warning / Error)
    # Subtle alert tone: dual chord with minor second tension resolving
    duration = 0.28
    total_samples = int(sample_rate * duration)
    samples = []
    for i in range(total_samples):
        t = i / sample_rate
        env = math.exp(-9.0 * t) if t > 0.004 else (t / 0.004)
        freq1 = 440.00  # A4
        freq2 = 466.16  # A#4 (subtle dissonant alert pulse)
        sig = 0.5 * math.sin(2 * math.pi * freq1 * t) + 0.5 * math.sin(2 * math.pi * freq2 * t)
        samples.append(sig * env * 0.65)
    _write_pcm_wav(os.path.join(SOUNDS_DIR, "alert.wav"), samples, sample_rate)

    # 4. done.wav (Diagnostics / Tests / Updates complete)
    # High crisp bell chime: B5 (987 Hz) with sparkling octave
    duration = 0.32
    total_samples = int(sample_rate * duration)
    samples = []
    for i in range(total_samples):
        t = i / sample_rate
        env = math.exp(-7.0 * t) if t > 0.003 else (t / 0.003)
        freq1 = 987.77   # B5
        freq2 = 1975.53  # B6
        sig = 0.7 * math.sin(2 * math.pi * freq1 * t) + 0.3 * math.sin(2 * math.pi * freq2 * t)
        samples.append(sig * env * 0.70)
    _write_pcm_wav(os.path.join(SOUNDS_DIR, "done.wav"), samples, sample_rate)


if __name__ == "__main__":
    generate_icons()
    generate_sounds()
