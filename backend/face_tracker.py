import os
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Callable

MODEL_PATH = Path(__file__).resolve().parent / "models" / "yunet.onnx"


class FaceTracker:
    def __init__(self, smoothing_factor: float = 0.2):
        """
        Initializes AI Face detector with temporal smoothing.
        smoothing_factor: 0.1 (slow/smooth pan) to 0.35 (faster pan response)
        """
        self.smoothing_factor = smoothing_factor
        self.detector = None
        self.current_input_size = (320, 320)

        if MODEL_PATH.exists() and hasattr(cv2, "FaceDetectorYN_create"):
            try:
                self.detector = cv2.FaceDetectorYN_create(
                    str(MODEL_PATH),
                    "",
                    self.current_input_size,
                    score_threshold=0.6,
                    nms_threshold=0.3,
                    top_k=5000
                )
            except Exception as e:
                print(f"Face detector init notice: {e}")

    def detect_faces(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detects faces in a frame. Returns list of (x, y, w, h)."""
        if self.detector is None or frame is None:
            return []

        h, w = frame.shape[:2]
        if (w, h) != self.current_input_size:
            self.current_input_size = (w, h)
            self.detector.setInputSize((w, h))

        try:
            _, faces = self.detector.detect(frame)
            if faces is None:
                return []

            results = []
            for face in faces:
                # face format: [x1, y1, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
                fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                if fw > 20 and fh > 20:
                    results.append((fx, fy, fw, fh))
            return results
        except Exception:
            return []

    def analyze_clip_speaker_positions(
        self,
        video_path: str | Path,
        start_sec: float,
        duration_sec: float,
        target_aspect_ratio: float = 9 / 16,
        sample_fps: int = 4,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes video frames across timestamp range, detects face positions,
        applies Exponential Moving Average (EMA) smoothing, and returns crop intervals.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Target crop dimensions
        crop_h = orig_height
        crop_w = int(crop_h * target_aspect_ratio)
        if crop_w > orig_width:
            crop_w = orig_width
            crop_h = int(crop_w / target_aspect_ratio)

        max_x_offset = max(0, orig_width - crop_w)
        default_x = max_x_offset // 2

        start_frame = int(start_sec * orig_fps)
        end_frame = min(total_frames, int((start_sec + duration_sec) * orig_fps))
        frame_step = max(1, int(orig_fps / sample_fps))

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        current_frame_idx = start_frame

        raw_positions = []
        last_known_x = default_x

        while current_frame_idx <= end_frame:
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            current_time = (current_frame_idx - start_frame) / orig_fps
            faces = self.detect_faces(frame)

            if len(faces) > 0:
                # Pick largest face
                largest_face = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest_face
                face_center_x = fx + (fw // 2)
                desired_x = face_center_x - (crop_w // 2)
                desired_x = max(0, min(max_x_offset, desired_x))
                last_known_x = desired_x
                raw_positions.append((current_time, desired_x))
            else:
                raw_positions.append((current_time, last_known_x))

            current_frame_idx += frame_step

            if progress_callback and (end_frame - start_frame) > 0:
                pct = int(((current_frame_idx - start_frame) / (end_frame - start_frame)) * 100)
                progress_callback({"percent": pct, "message": f"Tracking faces... {pct}%"})

        cap.release()

        if not raw_positions:
            return [{"start_time": 0.0, "end_time": duration_sec, "x": default_x, "y": 0, "w": crop_w, "h": crop_h}]

        # Temporal Exponential Moving Average (EMA) smoothing
        smoothed_positions = []
        current_smooth_x = float(raw_positions[0][1])

        for t, x in raw_positions:
            current_smooth_x = (self.smoothing_factor * x) + ((1.0 - self.smoothing_factor) * current_smooth_x)
            smoothed_positions.append((t, int(current_smooth_x)))

        crop_segments = []
        for i in range(len(smoothed_positions)):
            t, x = smoothed_positions[i]
            next_t = smoothed_positions[i + 1][0] if i + 1 < len(smoothed_positions) else duration_sec
            crop_segments.append({
                "start_time": t,
                "end_time": next_t,
                "x": x,
                "y": 0,
                "w": crop_w,
                "h": crop_h
            })

        return crop_segments

    def get_average_or_smooth_crop(
        self,
        video_path: str | Path,
        start_sec: float,
        duration_sec: float,
        target_aspect_ratio: float = 9 / 16,
        sample_fps: int = 3
    ) -> Tuple[int, int, int, int]:
        """Calculates dominant speaker framing (x, y, w, h) for a clip."""
        segments = self.analyze_clip_speaker_positions(
            video_path=video_path,
            start_sec=start_sec,
            duration_sec=duration_sec,
            target_aspect_ratio=target_aspect_ratio,
            sample_fps=sample_fps
        )
        if not segments:
            return (0, 0, 0, 0)

        avg_x = int(np.mean([s["x"] for s in segments]))
        w = segments[0]["w"]
        h = segments[0]["h"]
        return (avg_x, 0, w, h)

    def get_dynamic_pan_crop(
        self,
        video_path: str | Path,
        start_sec: float,
        duration_sec: float,
        target_aspect_ratio: float = 9 / 16,
        sample_fps: int = 3
    ) -> Tuple[int, int, str]:
        """
        Calculates dynamic crop with smooth time-based horizontal camera panning expression.
        Returns: (crop_w, crop_h, ffmpeg_x_expression_str)
        """
        segments = self.analyze_clip_speaker_positions(
            video_path=video_path,
            start_sec=start_sec,
            duration_sec=duration_sec,
            target_aspect_ratio=target_aspect_ratio,
            sample_fps=sample_fps
        )
        if not segments:
            return (0, 0, "0")

        w = segments[0]["w"]
        h = segments[0]["h"]

        # If few segments or very low movement variance, return constant static x
        xs = [s["x"] for s in segments]
        if max(xs) - min(xs) < 60 or len(segments) <= 2:
            return (w, h, str(int(np.mean(xs))))

        # Simplify keyframes into major focal shifts
        keyframes = []
        for i, s in enumerate(segments):
            t = round(s["start_time"], 2)
            x = s["x"]
            if not keyframes:
                keyframes.append((t, x))
            else:
                # Keep significant changes or every 3 seconds to preserve smooth motion
                prev_t, prev_x = keyframes[-1]
                if abs(x - prev_x) >= 40 or (t - prev_t) >= 3.0:
                    keyframes.append((t, x))

        if len(keyframes) == 1:
            return (w, h, str(keyframes[0][1]))

        # Build nested FFmpeg conditional piecewise expression: if(lte(t, t1), interp1, if(lte(t, t2), ...))
        def build_expr(idx: int) -> str:
            if idx >= len(keyframes) - 1:
                return str(keyframes[-1][1])
            t0, x0 = keyframes[idx]
            t1, x1 = keyframes[idx + 1]
            span = max(0.2, t1 - t0)
            interp = f"{x0}+({x1}-{x0})*(t-{t0})/{span:.2f}"
            rest = build_expr(idx + 1)
            return f"if(lte(t\\,{t1:.2f})\\,{interp}\\,{rest})"

        expr = build_expr(0)
        return (w, h, expr)

    def get_split_screen_crops(
        self,
        video_path: str | Path,
        start_sec: float,
        duration_sec: float,
        sample_fps: int = 3
    ) -> Optional[Dict[str, Tuple[int, int, int, int]]]:
        """
        Detects dual speakers (e.g. podcast / interview) and calculates
        separate top and bottom half crops (aspect ratio 9:8 each for vertical 9:16).
        Returns {'top': (x, y, w, h), 'bottom': (x, y, w, h)} or None if only single speaker.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Each half has aspect ratio 9 / 8 (e.g. 1080x960)
        half_ratio = 9.0 / 8.0
        crop_h = int(orig_height * 0.95)
        crop_w = int(crop_h * half_ratio)
        if crop_w > orig_width:
            crop_w = orig_width
            crop_h = int(crop_w / half_ratio)

        max_x = max(0, orig_width - crop_w)

        start_frame = int(start_sec * orig_fps)
        end_frame = min(total_frames, int((start_sec + duration_sec) * orig_fps))
        frame_step = max(1, int(orig_fps / sample_fps))

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        current_frame_idx = start_frame

        left_faces = []
        right_faces = []
        midpoint = orig_width / 2.0

        while current_frame_idx <= end_frame:
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            faces = self.detect_faces(frame)
            if len(faces) >= 2:
                # Sort faces left to right
                sorted_faces = sorted(faces, key=lambda f: f[0])
                f_left = sorted_faces[0]
                f_right = sorted_faces[-1]
                # Verify they are well-separated
                if (f_right[0] - f_left[0]) >= (orig_width * 0.15):
                    left_faces.append(f_left[0] + (f_left[2] // 2))
                    right_faces.append(f_right[0] + (f_right[2] // 2))
            elif len(faces) == 1:
                fc = faces[0][0] + (faces[0][2] // 2)
                if fc < midpoint:
                    left_faces.append(fc)
                else:
                    right_faces.append(fc)

            current_frame_idx += frame_step

        cap.release()

        # Need enough detections on both sides
        if len(left_faces) >= 2 and len(right_faces) >= 2:
            avg_left_center = np.median(left_faces)
            avg_right_center = np.median(right_faces)

            left_x = int(max(0, min(max_x, avg_left_center - (crop_w // 2))))
            right_x = int(max(0, min(max_x, avg_right_center - (crop_w // 2))))

            crop_y = max(0, (orig_height - crop_h) // 4)

            return {
                "top": (left_x, crop_y, crop_w, crop_h),
                "bottom": (right_x, crop_y, crop_w, crop_h)
            }

        return None
