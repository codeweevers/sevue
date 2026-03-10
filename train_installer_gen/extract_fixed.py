import cv2
import os
import tensorflow as tf

assert tf.__version__.startswith("2")

from mediapipe_model_maker import gesture_recognizer

import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

tasks = []
model = None


def init_models():
    global model

    h_base_options = python.BaseOptions(model_asset_path="model/hand_landmarker.task")
    hands_options = vision.HandLandmarkerOptions(
        base_options=h_base_options,
        num_hands=2,
        min_hand_detection_confidence=0.5,
    )
    hands_model = vision.HandLandmarker.create_from_options(hands_options)

    p_base_options = python.BaseOptions(model_asset_path="model/pose_landmarker.task")
    pose_options = vision.PoseLandmarkerOptions(
        base_options=p_base_options,
        min_pose_detection_confidence=0.5,
    )
    pose_model = vision.PoseLandmarker.create_from_options(pose_options)


def process_pose_image(args):
    global hands_model, pose_model
    path, label = args

    img = load_and_resize(path)
    if img is None:
        return None

    hands_result = hands_model.detect(img)
    pose_result = pose_model.detect(img)

    features = build_features_pose_category(hands_result, pose_result)

    if features is None or len(features) != FEATURE_SIZE:
        return None

    return features, label, path


def process_hands_image(args):
    global hands_model
    path, label = args
    img = load_and_resize(path)
    if img is None:
        return None

    hands_result = hands_model.detect(img)

    if not hands_result.hand_landmarks:
        return None

    features = build_features_hands_category(hands_result)

    if features is None or len(features) != FEATURE_SIZE:
        return None

    return features, label, path


def extract_hand(hand_landmarks):
    coords = np.array([(lm.x, lm.y, lm.z) for lm in hand_landmarks])

    wrist = coords[0]
    coords = coords - wrist  # center around wrist

    palm_size = np.linalg.norm(coords[9])  # middle_mcp relative to wrist
    if palm_size > 1e-6:
        coords = coords / palm_size

    return coords.reshape(-1)


def extract_pose_refs(pose_landmarks):
    lm = pose_landmarks[0]

    head = np.array([lm[0].x, lm[0].y, lm[0].z])  # nose
    left_shoulder = np.array([lm[11].x, lm[11].y, lm[11].z])
    right_shoulder = np.array([lm[12].x, lm[12].y, lm[12].z])

    return head, left_shoulder, right_shoulder


def distance(a, b):
    return np.linalg.norm(a - b)


def build_features_pose_category(hands_result, pose_result):
    """
    Build features for pose category.
    Total: 63 + 63 + 6 + 1 + 3 = 136
    - left_hand: 63
    - right_hand: 63
    - pose distances (to head/shoulders): 6
    - hand-to-hand distance: 1
    - depth features: 3
    """
    features = []

    left_hand = np.zeros(63)
    right_hand = np.zeros(63)

    left_center = None
    right_center = None

    # ---- HAND EXTRACTION ----
    if hands_result.hand_landmarks and hands_result.handedness:
        for i, hand_lms in enumerate(hands_result.hand_landmarks):
            data = extract_hand(hand_lms)

            # Calculate center from the NORMALIZED coordinates
            coords = data.reshape(-1, 3)
            center = coords.mean(axis=0)

            handedness = hands_result.handedness[i][0].category_name

            if handedness == "Left":
                left_hand = data
                left_center = center
            elif handedness == "Right":
                right_hand = data
                right_center = center

    features.extend(left_hand)  # 63
    features.extend(right_hand)  # 63

    # ---- POSE DISTANCE FEATURES ----
    shoulder_width = 1.0
    if pose_result.pose_landmarks:
        head, l_sh, r_sh = extract_pose_refs(pose_result.pose_landmarks)

        shoulder_width = distance(l_sh, r_sh)
        if shoulder_width < 1e-6:
            shoulder_width = 1.0

        for hc in [left_center, right_center]:
            if hc is None:
                features.extend([0.0, 0.0, 0.0])
            else:
                features.extend(
                    [
                        distance(hc, head) / shoulder_width,
                        distance(hc, l_sh) / shoulder_width,
                        distance(hc, r_sh) / shoulder_width,
                    ]
                )
    else:
        features.extend([0.0] * 6)  # 6

    # ---- HAND TO HAND DISTANCE ----
    if left_center is not None and right_center is not None:
        features.append(distance(left_center, right_center) / shoulder_width)  # 1
    else:
        features.append(0.0)

    # ---- DEPTH FEATURES ----
    left_depth = left_center[2] if left_center is not None else 0.0
    right_depth = right_center[2] if right_center is not None else 0.0

    # Normalize by shoulder width
    left_depth /= shoulder_width
    right_depth /= shoulder_width

    features.append(left_depth)  # 1
    features.append(right_depth)  # 1
    features.append(left_depth - right_depth)  # 1

    return np.array(features)


def build_features_hands_category(hands_result):
    """
    Build features for hands-only category.
    Total: 63 + 63 + 6 + 1 + 3 = 136
    - primary_hand: 63
    - secondary_hand: 63
    - pose distances: 6 (all zeros)
    - hand-to-hand distance: 1
    - depth features: 3
    """
    features = []

    primary_hand = np.zeros(63)
    secondary_hand = np.zeros(63)
    primary_center = None
    secondary_center = None

    if hands_result.hand_landmarks:
        hands_data = []

        for hand_lms in hands_result.hand_landmarks:
            data = extract_hand(hand_lms)
            coords = data.reshape(-1, 3)
            # Use original center (before normalization) for x-position
            original_coords = np.array([(lm.x, lm.y, lm.z) for lm in hand_lms])
            center_x = np.mean(original_coords[:, 0])

            # But use normalized coords for center calculation
            center = coords.mean(axis=0)
            hands_data.append((center_x, data, center))

        # Sort by horizontal position (left to right)
        hands_data.sort(key=lambda x: x[0])

        if len(hands_data) > 0:
            primary_hand = hands_data[0][1]
            primary_center = hands_data[0][2]

        if len(hands_data) > 1:
            secondary_hand = hands_data[1][1]
            secondary_center = hands_data[1][2]

    features.extend(primary_hand)  # 63
    features.extend(secondary_hand)  # 63

    # ---- POSE DISTANCE FEATURES (all zeros for hands-only) ----
    features.extend([0.0] * 6)  # 6

    # ---- HAND TO HAND DISTANCE ----
    if primary_center is not None and secondary_center is not None:
        features.append(distance(primary_center, secondary_center))  # 1
    else:
        features.append(0.0)

    # ---- DEPTH FEATURES ----
    primary_depth = primary_center[2] if primary_center is not None else 0.0
    secondary_depth = secondary_center[2] if secondary_center is not None else 0.0

    features.append(primary_depth)  # 1
    features.append(secondary_depth)  # 1
    features.append(primary_depth - secondary_depth)  # 1

    return np.array(features)


def load_and_resize(path, max_size=256):
    img = cv2.imread(path)
    if img is None:
        return None

    h, w = img.shape[:2]
    scale = max_size / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=img)


if __name__ == "__main__":

    DATASET_DIR = "frames"
    X = []
    y = []
    metadata = []

    # =======================
    #        POSE
    # =======================

    pose_tasks = []
    pose_dir = os.path.join(DATASET_DIR, "pose")

    if os.path.exists(pose_dir):
        print("Preparing POSE tasks...")

        for label in os.listdir(pose_dir):
            label_dir = os.path.join(pose_dir, label)
            if not os.path.isdir(label_dir):
                continue

            for file in os.listdir(label_dir):
                if file.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                    path = os.path.join(label_dir, file)
                    pose_tasks.append((path, label))

    print(f"Total pose images: {len(pose_tasks)}")

    if pose_tasks:
        with Pool(processes=cpu_count(), initializer=init_models) as pool:
            results = list(
                tqdm(
                    pool.imap(process_pose_image, pose_tasks),
                    total=len(pose_tasks),
                    desc="Processing POSE",
                )
            )

        for result in results:
            if result is not None:
                features, label, path = result
                if len(features) == FEATURE_SIZE:
                    X.append(features)
                    y.append(label)
                    metadata.append({"path": path, "category": "pose", "label": label})
                else:
                    print(
                        f"Warning: Skipping {path} - feature size mismatch: {len(features)} != {FEATURE_SIZE}"
                    )

    # =======================
    #        HANDS
    # =======================

    hands_tasks = []
    hands_dir = os.path.join(DATASET_DIR, "hands")

    if os.path.exists(hands_dir):
        print("Preparing HANDS tasks...")

        for label in os.listdir(hands_dir):
            label_dir = os.path.join(hands_dir, label)
            if not os.path.isdir(label_dir):
                continue

            for file in os.listdir(label_dir):
                if file.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                    path = os.path.join(label_dir, file)
                    hands_tasks.append((path, label))

    print(f"Total hands images: {len(hands_tasks)}")

    if hands_tasks:
        with Pool(processes=cpu_count(), initializer=init_models) as pool:
            hands_results = list(
                tqdm(
                    pool.imap(process_hands_image, hands_tasks),
                    total=len(hands_tasks),
                    desc="Processing HANDS",
                )
            )

        for result in hands_results:
            if result is not None:
                features, label, path = result
                if len(features) == FEATURE_SIZE:
                    X.append(features)
                    y.append(label)
                    metadata.append({"path": path, "category": "hands", "label": label})
                else:
                    print(
                        f"Warning: Skipping {path} - feature size mismatch: {len(features)} != {FEATURE_SIZE}"
                    )

    # =======================
    #        SAVE
    # =======================

    X = np.array(X)
    y = np.array(y)

    print(f"\nTotal samples collected: {len(X)}")
    print(f"Feature vector size: {FEATURE_SIZE}")

    if len(X) > 0:
        print(f"Actual feature size: {X.shape[1]}")

        # Verify no NaN or Inf values
        if np.any(np.isnan(X)):
            print("WARNING: NaN values detected in features!")
            nan_count = np.sum(np.isnan(X))
            print(f"  Total NaN values: {nan_count}")

        if np.any(np.isinf(X)):
            print("WARNING: Inf values detected in features!")
            inf_count = np.sum(np.isinf(X))
            print(f"  Total Inf values: {inf_count}")

        np.save("X.npy", X)
        np.save("y.npy", y)

        import json

        with open("metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        print("\nSaved: X.npy, y.npy, metadata.json")
        print(f"X.shape: {X.shape}")

        from collections import Counter

        categories = [m["category"] for m in metadata]
        print(f"\nPose samples: {categories.count('pose')}")
        print(f"Hands samples: {categories.count('hands')}")

        label_counts = Counter(y)
        print(f"\nLabel distribution:")
        for label, count in sorted(label_counts.items()):
            print(f"  {label}: {count}")
    else:
        print("\nERROR: No valid samples were collected!")
