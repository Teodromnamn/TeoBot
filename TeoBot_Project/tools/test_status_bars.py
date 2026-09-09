"""Run HP/MP detection over screenshots and save annotated images + JSON."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from game.status_bar_detector import detect_hp_mp

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def collect_images(inputs: list[Path]) -> list[Path]:
    files = []
    for path in inputs:
        if path.is_dir():
            files.extend(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        elif path.suffix.lower() in IMAGE_SUFFIXES:
            files.append(path)
    return sorted(set(files))


def serialise(reading):
    if reading is None:
        return None
    data = asdict(reading)
    data["rect"] = list(data["rect"])
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Test automatic HP/MP detection")
    parser.add_argument("inputs", nargs="+", type=Path, help="Images or directories")
    parser.add_argument("--output", type=Path, default=Path("hp_mp_results"))
    args = parser.parse_args()

    images = collect_images(args.inputs)
    if not images:
        parser.error("No supported images found")
    args.output.mkdir(parents=True, exist_ok=True)

    report = {}
    for path in images:
        with Image.open(path) as image:
            result = detect_hp_mp(image)
        output_name = f"{path.stem}_detected.png"
        result.annotated_image.save(args.output / output_name)
        report[path.name] = {
            "hp": serialise(result.hp),
            "mp": serialise(result.mp),
            "annotated_image": output_name,
        }
        hp = f"{result.hp.current}/{result.hp.maximum}" if result.hp else "not found"
        mp = f"{result.mp.current}/{result.mp.maximum}" if result.mp else "not found"
        print(f"{path.name}: HP={hp}, MP={mp}")

    report_path = args.output / "results.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
