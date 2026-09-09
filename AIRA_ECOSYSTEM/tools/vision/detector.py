"""
Deteksi + tracking objek dari webcam menggunakan YOLO11n, dengan
window live preview supaya user bisa melihat langsung apa yang
sedang "dilihat" AI saat kamera aktif.

OPTIMASI UNTUK CPU LEMAH (X270, 2-core/4-thread):
1. Resolusi capture diturunkan ke 640x480 - webcam sering default
   ke resolusi native yang jauh lebih besar (misal 1280x720+),
   makin besar frame makin berat di-resize+infer tiap kali.
2. imgsz inferensi diturunkan ke 320 (dari default YOLO 640) -
   YOLO resize internal ke ukuran ini sebelum diproses jaringan
   neural, jadi ini pengaruh besar ke kecepatan. Trade-off: objek
   kecil/jauh dari kamera mungkin kurang akurat terdeteksi, tapi
   untuk kebutuhan "lihat apa yang di depan kamera" jarak dekat
   biasanya masih cukup andal.
3. Frame skipping - inferensi PENUH cuma dijalankan tiap
   INFER_EVERY_N_FRAMES, frame di antaranya cuma menggambar ulang
   box terakhir yang diketahui (tanpa infer baru). Ini bikin window
   terasa jauh lebih smooth secara visual walau "mata" AI sebenarnya
   tidak secepat itu mikir - mirip prinsip interpolasi frame.

Desain "aktif saat dibutuhkan" tetap dipertahankan: webcam CUMA
dibuka selama durasi tracking berjalan, setelah itu langsung
di-release.
"""

import time
from pathlib import Path

import cv2

import logging

logger = logging.getLogger("aira.tools.vision")


def log_error(context, exc):
    logger.error(f"ERROR | context={context} | detail={exc}")


MODEL_NAME = "yolo11n.pt"
CONFIDENCE_THRESHOLD = 0.5

# --- Parameter optimasi CPU - sesuaikan kalau masih terasa lag ---
CAPTURE_WIDTH = 640
CAPTURE_HEIGHT = 480
INFER_IMG_SIZE = 320          # turunkan lagi ke 224 kalau masih lag
INFER_EVERY_N_FRAMES = 3      # infer 1 dari tiap N frame yang ditampilkan
# -------------------------------------------------------------

WINDOW_NAME = "AI Vision - apa yang dilihat AI"
DEFAULT_LIVE_DURATION = 4.0
FUSION_LIVE_DURATION = 2.0

BASE_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = BASE_DIR / "database" / "vision_snapshots"

_model_instance = None


def _get_model():

    global _model_instance

    if _model_instance is not None:
        return _model_instance

    try:

        from ultralytics import YOLO

        logger.info(f"VISION | loading model {MODEL_NAME}...")

        _model_instance = YOLO(MODEL_NAME)

        logger.info("VISION | model berhasil di-load.")

        return _model_instance

    except Exception as exc:

        log_error("vision.detector._get_model", exc)
        return None


def detect_objects(
    camera_index=0,
    duration=DEFAULT_LIVE_DURATION,
    show_window=True,
    save_snapshot=True,
):
    """
    Buka webcam, jalankan tracking objek selama `duration` detik
    (menampilkan window live preview kalau show_window=True), lalu
    tutup webcam. Return ringkasan objek unik yang terlacak selama
    durasi tersebut.

    Window bisa ditutup lebih awal dengan menekan 'q'.
    """

    model = _get_model()

    if model is None:

        return {
            "success": False,
            "tool": "detect_objects",
            "error": (
                "Model YOLO gagal di-load. Cek koneksi internet "
                "untuk download pertama kali, atau paket "
                "'ultralytics' belum ter-install."
            ),
        }

    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

    if not cap.isOpened():

        return {
            "success": False,
            "tool": "detect_objects",
            "error": (
                f"Tidak bisa membuka webcam index {camera_index}. "
                f"Cek apakah webcam sedang dipakai aplikasi lain "
                f"atau index-nya salah."
            ),
        }

    # Minta resolusi lebih kecil ke driver kamera. Catatan: tidak
    # semua webcam menghormati resolusi custom - kalau webcam kamu
    # abaikan ini, frame yang masuk tetap resolusi native-nya, dan
    # imgsz di bawah tetap jadi penyelamat utama kecepatan.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

    tracked_objects = {}
    last_annotated_frame = None
    last_plot_result = None  # dipakai untuk re-draw di frame skip
    frame_counter = 0

    try:

        for _ in range(5):
            cap.read()
            time.sleep(0.03)

        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) < duration:

            success, frame = cap.read()

            if not success or frame is None:
                continue

            frame_counter += 1
            run_inference = (frame_counter % INFER_EVERY_N_FRAMES == 0)

            if run_inference or last_plot_result is None:

                results = model.track(
                    frame,
                    conf=CONFIDENCE_THRESHOLD,
                    imgsz=INFER_IMG_SIZE,
                    persist=True,
                    tracker="bytetrack.yaml",
                    verbose=False,
                )

                result = results[0]
                last_plot_result = result

                if result.boxes is not None and result.boxes.id is not None:

                    for box, track_id in zip(result.boxes, result.boxes.id):

                        class_id = int(box.cls[0])
                        label = model.names[class_id]
                        confidence = float(box.conf[0])
                        tid = int(track_id)

                        existing = tracked_objects.get(tid)

                        if existing is None or confidence > existing["best_confidence"]:
                            tracked_objects[tid] = {
                                "label": label,
                                "best_confidence": round(confidence, 3),
                            }

                last_annotated_frame = last_plot_result.plot()

            else:

                # Frame skip: tidak infer ulang, cuma tampilkan frame
                # kamera TERBARU tapi dengan box dari hasil inferensi
                # terakhir yang di-plot ulang. Ini murah secara
                # komputasi (cuma re-plot, bukan infer neural network
                # baru) dan bikin window terasa lebih hidup daripada
                # freeze menunggu inferensi berikutnya.
                if last_plot_result is not None:
                    last_annotated_frame = last_plot_result.plot()
                else:
                    last_annotated_frame = frame

            if show_window and last_annotated_frame is not None:

                cv2.imshow(WINDOW_NAME, last_annotated_frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        detections = [
            {
                "track_id": tid,
                "label": info["label"],
                "confidence": info["best_confidence"],
            }
            for tid, info in tracked_objects.items()
        ]

        snapshot_path = None

        if save_snapshot and detections and last_annotated_frame is not None:

            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

            filename = f"snapshot_{int(time.time())}.jpg"
            full_path = SNAPSHOT_DIR / filename

            cv2.imwrite(str(full_path), last_annotated_frame)

            snapshot_path = str(full_path)

        return {
            "success": True,
            "tool": "detect_objects",
            "count": len(detections),
            "detections": detections,
            "snapshot_path": snapshot_path,
        }

    except Exception as exc:

        log_error("vision.detector.detect_objects", exc)

        return {
            "success": False,
            "tool": "detect_objects",
            "error": str(exc),
        }

    finally:

        cap.release()

        if show_window:
            cv2.destroyWindow(WINDOW_NAME)