"""
Build one reel: Gemini writes the scene + caption, Pollinations renders a
vertical still, ffmpeg turns it into a slow Ken Burns push.

Reels want a 9:16 video with an audio stream. The image is generated at
1080x1920 directly rather than cropped from a square, so nothing important
falls outside the frame, and a silent AAC track is muxed in because
Instagram rejects video with no audio stream at all.

Env vars required:
  GEMINI_KEY  Google AI Studio key
  GH_REPO     "username/repo" -> used to build the public raw video URL

Writes: reel_out/<stamp>.mp4 and pending_reel.json
"""

import datetime
import json
import pathlib
import subprocess
import sys

from post import generate_image, generate_text, load_config

OUT = pathlib.Path("reel_out")
SECONDS = 8
FPS = 30


def build_video(image, out):
    """Slow zoom-in. zoompan works per-frame, so d = seconds * fps."""
    frames = SECONDS * FPS
    vf = (
        f"zoompan=z='min(zoom+0.0006,1.20)':d={frames}"
        ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s=1080x1920:fps={FPS},format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-t", str(SECONDS), "-i", str(image),
        "-f", "lavfi", "-t", str(SECONDS),
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main():
    import os

    cfg = load_config()
    repo = os.environ["GH_REPO"]

    scene, caption = generate_text(cfg["topic"], cfg["style"], os.environ["GEMINI_KEY"])
    print("SCENE:", scene)
    print("CAPTION:", caption)

    OUT.mkdir(exist_ok=True)
    stamp = f"{datetime.datetime.now(datetime.timezone.utc):%Y%m%d-%H%M}"
    still = OUT / f"{stamp}.jpg"
    video = OUT / f"{stamp}.mp4"

    generate_image(scene, still, width=1080, height=1920, cfg=cfg,
                   gemini_key=os.environ["GEMINI_KEY"])
    print("Still saved:", still.name)

    build_video(still, video)
    size_mb = video.stat().st_size / 1_048_576
    print(f"Video built: {video.name}  {size_mb:.1f} MB  {SECONDS}s")
    still.unlink()  # only the mp4 gets published

    with open("pending_reel.json", "w") as f:
        json.dump(
            {
                "video_url": (
                    f"https://raw.githubusercontent.com/{repo}/media/{video.name}"
                ),
                "caption": caption,
            },
            f,
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print("FAILED: ffmpeg exited", e.returncode, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(1)
