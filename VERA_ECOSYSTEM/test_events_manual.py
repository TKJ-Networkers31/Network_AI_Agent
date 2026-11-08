"""
test_events_manual.py — validasi cepat core/events.py.

CARA PAKAI:
    1. Taruh file ini SEJAJAR dengan folder core/ di AIRA_ECOSYSTEM/
       (yaitu: AIRA_ECOSYSTEM/test_events_manual.py)
    2. Jalankan dari root AIRA_ECOSYSTEM/:
           cd AIRA_ECOSYSTEM
           python test_events_manual.py
    3. Kalau semua benar, muncul "SEMUA TEST LULUS" di baris terakhir.
       Kalau ada yang salah, AssertionError akan muncul dan berhenti di
       baris yang gagal.

Tidak butuh pytest/library tambahan - cukup Python biasa.
"""

import time

from core.events import event_bus, EventNames, Event

received = []


def handler(event: Event):
    received.append(event.event)


async def async_handler(event: Event):
    received.append(f"async:{event.event}")


def broken_handler(event: Event):
    raise RuntimeError("sengaja error untuk test isolasi subscriber")


def test_1_subscribe_publish_wildcard():
    event_bus.subscribe(EventNames.TOOL_START, handler)
    event_bus.subscribe("*", async_handler)

    event_bus.publish(
        EventNames.TOOL_START,
        agent="AKANE",
        tool="ssh",
        data={"device": "R1"},
    )

    time.sleep(0.2)  # beri waktu dispatch async selesai

    assert EventNames.TOOL_START in received, "handler sync tidak terpanggil"
    assert f"async:{EventNames.TOOL_START}" in received, "handler wildcard async tidak terpanggil"

    print("[1/4] OK - subscribe + publish + wildcard bekerja:", received)


def test_2_unsubscribe():
    token = event_bus.subscribe(EventNames.SYSTEM_ERROR, handler)
    ok = event_bus.unsubscribe(EventNames.SYSTEM_ERROR, token)

    assert ok is True, "unsubscribe seharusnya berhasil (token valid)"

    ok_lagi = event_bus.unsubscribe(EventNames.SYSTEM_ERROR, token)
    assert ok_lagi is False, "unsubscribe token yang sudah dihapus harus return False"

    print("[2/4] OK - unsubscribe bekerja")


def test_3_subscriber_error_terisolasi():
    before = len(received)

    event_bus.subscribe(EventNames.MEMORY_SAVED, broken_handler)
    event_bus.subscribe(EventNames.MEMORY_SAVED, handler)

    event_bus.publish(EventNames.MEMORY_SAVED, agent="core.memory")

    time.sleep(0.2)

    after = len(received)

    assert after > before, "handler normal harus tetap terpanggil walau ada subscriber lain error"
    assert EventNames.MEMORY_SAVED in received

    print("[3/4] OK - subscriber error tidak mengganggu subscriber lain")


def test_4_payload_shape():
    captured = {}

    def capture(event: Event):
        captured["event"] = event.to_dict()

    event_bus.subscribe(EventNames.RESPONSE_READY, capture)
    event_bus.publish(
        EventNames.RESPONSE_READY,
        agent="AIRA",
        data={"answer": "hai"},
    )

    time.sleep(0.2)

    payload = captured.get("event")
    assert payload is not None, "payload tidak pernah diterima"

    for key in ("event", "agent", "tool", "timestamp", "data"):
        assert key in payload, f"payload harus punya key '{key}'"

    assert payload["event"] == EventNames.RESPONSE_READY
    assert payload["agent"] == "AIRA"
    assert payload["data"] == {"answer": "hai"}

    print("[4/4] OK - bentuk payload sesuai standar:", payload)


def main():
    test_1_subscribe_publish_wildcard()
    test_2_unsubscribe()
    test_3_subscriber_error_terisolasi()
    test_4_payload_shape()

    event_bus.clear()
    print("\nSEMUA TEST LULUS")


if __name__ == "__main__":
    main()