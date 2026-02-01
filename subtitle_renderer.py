import cv2
import numpy as np
import time


def wrap_text(text, font, font_scale, thickness, max_width):
    """Wrap text into multiple lines based on max pixel width."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = current + (" " if current else "") + word
        (w, _), _ = cv2.getTextSize(test, font, font_scale, thickness)

        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def render_youtube_cc_prediction(
    frame: np.ndarray,
    text: str,
    start_time: float,
    duration: float,
    current_time: float,
    confidence: float | None = None,
    flip_text: bool = False,
    font_scale: float = 1.0,
    padding: int = 12,
    bottom_margin: int = 60,
    bg_opacity: float = 0.75,
    max_width_ratio: float = 0.8,
) -> np.ndarray:
    """
    Render YouTube-style multi-line CC subtitle with timed persistence.
    """

    # ---- Timing gate ----
    if not (start_time <= current_time <= start_time + duration):
        return frame

    if not text:
        return frame

    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 2

    subtitle = f"{text} ({confidence:.2f})" if confidence is not None else text

    max_text_width = int(w * max_width_ratio)

    # ---- Wrap text ----
    lines = wrap_text(subtitle, font, font_scale, thickness, max_text_width)

    # ---- Measure block size ----
    line_sizes = [
        cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines
    ]

    text_width = max(w for w, _ in line_sizes)
    text_height = sum(h for _, h in line_sizes)
    line_spacing = int(font_scale * 10)

    box_w = text_width + padding * 2
    box_h = text_height + padding * 2 + line_spacing * (len(lines) - 1)

    box_x = (w - box_w) // 2
    box_y = h - bottom_margin - box_h

    # ---- Background ----
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (box_x, box_y),
        (box_x + box_w, box_y + box_h),
        (0, 0, 0),
        -1,
    )

    frame = cv2.addWeighted(overlay, bg_opacity, frame, 1 - bg_opacity, 0)

    # ---- Text layer ----
    text_layer = np.zeros_like(frame)

    y = box_y + padding
    for line, (lw, lh) in zip(lines, line_sizes):
        x = box_x + (box_w - lw) // 2
        y += lh
        cv2.putText(
            text_layer,
            line,
            (x, y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )
        y += line_spacing

    if flip_text:
        text_layer = cv2.flip(text_layer, 1)

    mask = cv2.cvtColor(text_layer, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)

    frame = cv2.bitwise_and(frame, frame, mask=cv2.bitwise_not(mask))
    frame = cv2.add(frame, text_layer)

    return frame
