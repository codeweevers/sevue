import os
import shutil

# -------- CONFIG --------
SOURCE_DIR = "data"
DEST_DIR = "dataset"
MAX_FILES_PER_FOLDER = 600
# ------------------------

os.makedirs(DEST_DIR, exist_ok=True)

for subfolder in os.listdir(SOURCE_DIR):
    subfolder_path = os.path.join(SOURCE_DIR, subfolder)

    if not os.path.isdir(subfolder_path):
        continue

    dest_subfolder = os.path.join(DEST_DIR, subfolder)
    os.makedirs(dest_subfolder, exist_ok=True)

    count = 0

    for root, dirs, files in os.walk(subfolder_path):
        for file in files:
            if count >= MAX_FILES_PER_FOLDER:
                break

            src_path = os.path.join(root, file)
            dst_path = os.path.join(dest_subfolder, file)

            # Prevent overwrite
            if os.path.exists(dst_path):
                base, ext = os.path.splitext(file)
                dst_path = os.path.join(dest_subfolder, f"{base}_{count}{ext}")

            shutil.move(src_path, dst_path)
            count += 1

        if count >= MAX_FILES_PER_FOLDER:
            break
