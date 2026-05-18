from ultralytics import YOLO
from pathlib import Path
from PIL import Image
import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print('using ', device)
print(torch.__version__)
# Load a model
model = YOLO("/mnt/managed_home/farm-ng-user-byu-crimson/farm-ng-amiga/BYU_Amiga/amiga_YOLO/amiga_YOLO_benchmark/26n.pt")

# --- CONFIG ---
IMAGE_FOLDER = Path("/mnt/managed_home/farm-ng-user-byu-crimson/farm-ng-amiga/BYU_Amiga/amiga_YOLO/amiga_YOLO_benchmark/test_images")  
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

def is_valid_image(path: Path) -> bool:
    """Returns True if the image can be opened and verified, False if corrupted."""
    try:
        with Image.open(path) as img:
            img.verify()  # Catches truncated/corrupted files
        # Re-open after verify() — PIL leaves the file in an unusable state after verify
        with Image.open(path) as img:
            img.load()    # Forces full decode, catches partially corrupted files
        return True
    except Exception as e:
        print(f"  [SKIPPED] {path.name}: {e}")
        return False

# Collect and validate images
all_paths = [p for p in IMAGE_FOLDER.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
print(f"Found {len(all_paths)} images in {IMAGE_FOLDER}, validating...")

valid_paths = [p for p in all_paths if is_valid_image(p)]
skipped = len(all_paths) - len(valid_paths)
print(f"  {len(valid_paths)} valid, {skipped} skipped\n")

if not valid_paths:
    print("No valid images to process.")
    exit()

# Predict on validated images
for path in valid_paths:
    results = model(path, stream=True)  # stream=True returns a generator
    for result in results:
        # process and discard immediately
        names = [result.names[cls.item()] for cls in result.boxes.cls.int()]
        confs = result.boxes.conf
        xyxy  = result.boxes.xyxy
        print(f"{path.name}: {len(names)} detections")
        # result goes out of scope here and gets garbage collected
