"""
Deteksi objek dari webcam menggunakan YOLO11n (nano - model
paling ringan dari keluarga YOLO11, cocok untuk CPU-only seperti
X270).

Desain "aktif saat dibutuhkan": webcam CUMA dibuka saat fungsi ini
dipanggil, ambil satu frame, jalankan deteksi, langsung release
kamera. Tidak ada stream/loop terus-menerus yang makan resource
di background.

Model yolo11n.pt didownload OTOMATIS oleh ultralytics saat
pertama kali dipakai (~5-6MB, jauh lebih kecil dari model YOLO
lain), lalu di-cache lokal dan dipakai offline setelahnya.
"""

import time
from pathlib import Path

import cv2

from agent.core.logger import log_error, logger


MODEL_NAME = "yolo11n.pt"  # nano - paling ringan untuk CPU
CONFIDENCE_THRESHOLD = 0.5

BASE_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = BASE_DIR / "data" / "vision_snapshots"

_model_instance = None


def _get_model():
    """
    Lazy-load model YOLO - baru diimport & di-load saat PERTAMA
    kali dipanggil, bukan saat modul ini di-import. Ini penting
    karena import ultralytics/torch cukup berat (beberapa detik),
    jangan sampai membebani startup agent kalau fitur ini tidak
    dipakai di sesi tersebut.
    """

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


def detect_objects(camera_index=0, save_snapshot=True):
    """
    Buka webcam, ambil satu frame, jalankan deteksi objek, lalu
    tutup webcam. Return dict hasil deteksi (format konsisten
    dengan tool lain di project ini - selalu ada key 'success').
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

    # cv2.CAP_DSHOW mempercepat startup webcam di Windows -
    # tanpa ini, OpenCV kadang butuh beberapa detik ekstra untuk
    # buka device di Windows.
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

    try:

        # Ambil beberapa frame dulu dan buang - banyak webcam butuh
        # "warm-up" beberapa frame sebelum exposure/white-balance
        # stabil, kalau langsung ambil frame pertama hasilnya
        # sering gelap/blur.
        for _ in range(5):
            cap.read()
            time.sleep(0.05)

        success, frame = cap.read()

        if not success or frame is None:

            return {
                "success": False,
                "tool": "detect_objects",
                "error": "Gagal mengambil frame dari webcam.",
            }

        results = model.predict(
            frame,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,
        )

        detections = []

        for result in results:

            for box in result.boxes:

                class_id = int(box.cls[0])
                class_name = model.names[class_id]
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = [round(v, 1) for v in box.xyxy[0].tolist()]

                detections.append({
                    "label": class_name,
                    "confidence": round(confidence, 3),
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                })

        snapshot_path = None

        if save_snapshot and detections:

            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

            annotated = results[0].plot()  # frame dengan bbox digambar
            filename = f"snapshot_{int(time.time())}.jpg"
            full_path = SNAPSHOT_DIR / filename

            cv2.imwrite(str(full_path), annotated)

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

        # WAJIB dilepas di sini (bukan cuma di jalur sukses) supaya
        # webcam tidak "nyangkut" ke proses ini kalau terjadi error
        # di tengah - kalau tidak, webcam bisa jadi tidak bisa
        # dipakai aplikasi lain sampai proses Python di-restart.
        cap.release()