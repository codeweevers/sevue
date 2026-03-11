import os
import cv2
import numpy as np
import random
TARGET_NONE_COUNT = 3000
DATASET_PATH = "frames"
NONE_FOLDER = os.path.join(DATASET_PATH, "none")
GENERATE_PER_IMAGE = 2

os.makedirs(NONE_FOLDER, exist_ok=True)


def heavy_blur(image):
    return cv2.GaussianBlur(image, (25, 25), 0)


def random_crop_resize(image):
    h, w = image.shape[:2]
    crop_x = random.randint(0, int(w * 0.4))
    crop_y = random.randint(0, int(h * 0.4))
    crop_w = random.randint(int(w * 0.5), w)
    crop_h = random.randint(int(h * 0.5), h)

    cropped = image[crop_y:crop_h, crop_x:crop_w]
    return cv2.resize(cropped, (w, h))


def add_noise(image):
    noise = np.random.normal(0, 50, image.shape).astype(np.uint8)
    return cv2.add(image, noise)


def blackout_region(image):
    h, w = image.shape[:2]
    x1 = random.randint(0, w // 2)
    y1 = random.randint(0, h // 2)
    x2 = random.randint(w // 2, w)
    y2 = random.randint(h // 2, h)

    image[y1:y2, x1:x2] = 0
    return image


def strong_rotation(image):
    h, w = image.shape[:2]
    angle = random.uniform(-60, 60)
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1)
    return cv2.warpAffine(image, M, (w, h))


def strong_brightness(image):
    alpha = random.uniform(0.3, 2.0)
    return cv2.convertScaleAbs(image, alpha=alpha, beta=0)


def destroy_gesture(image):
    transforms = [
        heavy_blur,
        random_crop_resize,
        add_noise,
        blackout_region,
        strong_rotation,
        strong_brightness
    ]

    # Apply 1 to 3 random destructive transforms
    num_transforms = random.randint(1, 3)
    selected = random.sample(transforms, num_transforms)

    for t in selected:
        image = t(image)

    return image

def collect_all_images():
    all_images = []

    for class_name in os.listdir(DATASET_PATH):
        if class_name == "none":
            continue

        class_path = os.path.join(DATASET_PATH, class_name)
        if not os.path.isdir(class_path):
            continue

        for file in os.listdir(class_path):
            full_path = os.path.join(class_path, file)
            all_images.append(full_path)

    return all_images

def generate_none_class():
    all_images = collect_all_images()
    random.shuffle(all_images)

    count = 0

    for img_path in all_images:
        if count >= TARGET_NONE_COUNT:
            break

        image = cv2.imread(img_path)
        if image is None:
            continue

        destroyed = destroy_gesture(image.copy())

        save_name = f"none_{count}.jpg"
        cv2.imwrite(os.path.join(NONE_FOLDER, save_name), destroyed)

        count += 1

    print(f"Generated {count} 'none' images.")

if __name__ == "__main__":
    generate_none_class()
