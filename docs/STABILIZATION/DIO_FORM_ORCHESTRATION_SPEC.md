# AIRA OS — DIO Form Orchestration Specification

**Dokumen:** `docs/STABILIZATION/DIO_FORM_ORCHESTRATION_SPEC.md`  
**Status:** DIVERIFIKASI & SELESAI  
**Komponen:** `core/dio/models.py`, `agents/rei/dio_tools.py`, `tests/test_dio_orchestration.py`

---

## 1. Spesifikasi Status Interaksi (`InteractionState`)

```python
class InteractionState(str, Enum):
    PENDING_INPUT = "PENDING_INPUT"          # AI Planner mengidentifikasi kekurangan parameter
    FORM_PRESENTED = "FORM_PRESENTED"        # Skema formulir dibuat dan ditampilkan di frontend
    SUBMITTED = "SUBMITTED"                  # Pengguna mengirimkan data formulir
    VALIDATING = "VALIDATING"                # Backend memvalidasi tipe data dan batasan keamanan
    READY_TO_CONTINUE = "READY_TO_CONTINUE"  # Nilai valid tersimpan di interaction memory
    COMPLETED = "COMPLETED"                  # Interaksi selesai dan efek samping dieksekusi
    CANCELLED = "CANCELLED"                  # Pengguna menolak/membatalkan formulir
```

---

## 2. Diagram Alur Transisi State

```
[ PENDING_INPUT ]
       │
       ▼ (generate_schema)
[ FORM_PRESENTED ]
       │
       ├─── (action: cancel / reject) ───► [ CANCELLED ] (Final)
       │
       ▼ (action: submit)
[ SUBMITTED ]
       │
       ▼ (schema validation)
[ VALIDATING ]
       │
       ▼ (sanitize & store in memory)
[ READY_TO_CONTINUE ]
       │
       ▼ (trigger pipeline / resume agent)
[ COMPLETED ] (Final)
```

---

## 3. Perlindungan Idempotensi & Anti-Replay

Pada `agents/rei/dio_tools.py::submit_structured_input()`:
```python
state_key = f"dio_state:{schema_id}"
curr_state = memory.load(state_key)

# Penjaga Idempoten
if curr_state in (InteractionState.COMPLETED.value, InteractionState.CANCELLED.value):
    return {
        "success": True,
        "schema_id": schema_id,
        "already_processed": True,
        "cancelled": curr_state == InteractionState.CANCELLED.value,
        "state": curr_state,
        "saved_keys": [],
        "pending_location": None,
        "location_result": None,
    }
```

---

## 4. Resolusi Pemilihan Perangkat Cerdas (`request_device_choice`)

Fungsi `request_device_choice()` secara dinamis mengubah daftar perangkat inventaris menjadi opsi form:
- Menampilkan nama perangkat beserta alamat host: `f"{name} ({host})"`.
- Jika perangkat hanya ada 1 (`CHR`), orchestrator melewati form interaktif dan langsung mengarahkan diagnostik ke router tersebut.
- Jika ada banyak perangkat, form disajikan secara rapi dengan tombol submit yang memicu alur validasi.

---

## 5. Hasil Pengujian Unit

Seluruh skenario pengujian pada `tests/test_dio_orchestration.py` (5 passed) memvalidasi kepatuhan spesifikasi ini tanpa regresi.
