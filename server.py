import cv2
import mediapipe as mp
import time
import numpy as np
import asyncio
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaBlackhole
import json

mp_drawing = mp.solutions.drawing_utils
mp_hands = mp.solutions.hands

FINGER_GROUPS = {
    'thumb': [0, 1, 2, 3, 4],
    'index': [5, 6, 7, 8],
    'middle': [9, 10, 11, 12],
    'ring': [13, 14, 15, 16],
    'pinky': [17, 18, 19, 20]
}

FINGER_COLORS = {
    'thumb': (0, 0, 255),
    'index': (0, 255, 0),
    'middle': (255, 0, 0),
    'ring': (255, 0, 255),
    'pinky': (255, 255, 255)
}

def is_peace_sign(landmarks):
    tips = {'index': 8, 'middle': 12, 'ring': 16, 'pinky': 20}
    pips = {'index': 6, 'middle': 10, 'ring': 14, 'pinky': 18}
    return (
        landmarks[tips['index']].y < landmarks[pips['index']].y and
        landmarks[tips['middle']].y < landmarks[pips['middle']].y and
        landmarks[tips['ring']].y > landmarks[pips['ring']].y and
        landmarks[tips['pinky']].y > landmarks[pips['pinky']].y
    )

async def signaling_handler(websocket, path=None):
    pc = RTCPeerConnection()
    video_track = None
    show_table = True
    last_toggle_time = 0
    cooldown = 1.5
    hands = mp_hands.Hands(min_detection_confidence=0.8, min_tracking_confidence=0.5)

    @pc.on('track')
    def on_track(track):
        nonlocal video_track
        if track.kind == 'video':
            video_track = track
            print('Video track received')

    @pc.on('icecandidate')
    async def on_icecandidate(event):
        if event.candidate:
            await websocket.send(json.dumps({
                'type': 'candidate',
                'candidate': {
                    'candidate': event.candidate.candidate,
                    'sdpMid': event.candidate.sdpMid,
                    'sdpMLineIndex': event.candidate.sdpMLineIndex
                }
            }))

    async for message in websocket:
        data = json.loads(message)
        if data['type'] == 'offer':
            offer = RTCSessionDescription(sdp=data['sdp'], type=data['type'])
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await websocket.send(json.dumps({'type': pc.localDescription.type, 'sdp': pc.localDescription.sdp}))
        elif data['type'] == 'candidate':
            c = data['candidate']
            # aiortc expects candidate as dict or RTCIceCandidate
            await pc.addIceCandidate(c)

        # Process video frames
        if video_track:
            while True:
                frame = await video_track.recv()
                img = frame.to_ndarray(format="bgr24")
                image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                image.flags.writeable = False
                results = hands.process(image)
                image.flags.writeable = True
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                if results.multi_hand_landmarks:
                    for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                        mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                        h, w, _ = image.shape
                        for group, indices in FINGER_GROUPS.items():
                            color = FINGER_COLORS[group]
                            for idx in indices:
                                lm = hand_landmarks.landmark[idx]
                                cx, cy = int(lm.x * w), int(lm.y * h)
                                cv2.circle(image, (cx, cy), 6, color, -1)
                        current_time = time.time()
                        if current_time - last_toggle_time > cooldown:
                            if is_peace_sign(hand_landmarks.landmark):
                                show_table = not show_table
                                last_toggle_time = current_time
                        if show_table:
                            base_x = 10 if hand_idx == 0 else w - 200
                            base_y = 20
                            spacing = 15
                            font = cv2.FONT_HERSHEY_SIMPLEX
                            scale = 0.4
                            cv2.putText(image, f"Hand {hand_idx + 1}", (base_x, base_y), font, scale, (0, 255, 255), 1)
                            cv2.putText(image, "ID    X     Y     Z", (base_x, base_y + spacing), font, scale, (0, 255, 255), 1)
                            for idx, lm in enumerate(hand_landmarks.landmark[:15]):
                                row = f"{idx:<2}  {lm.x:.2f} {lm.y:.2f} {lm.z:.2f}"
                                y_offset = base_y + (idx + 2) * spacing
                                cv2.putText(image, row, (base_x, y_offset), font, scale, (255, 255, 255), 1)
                cv2.imshow('WebRTC Hand Tracking', image)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cv2.destroyAllWindows()
            break

async def main():
    server = await websockets.serve(signaling_handler, '0.0.0.0', 5001)
    print("WebRTC signaling server started on ws://0.0.0.0:5001")
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped")
