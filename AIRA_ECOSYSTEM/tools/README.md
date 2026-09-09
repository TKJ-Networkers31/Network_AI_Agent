# tools/

Folder ini berisi LOW-LEVEL CLIENT saja (paramiko SSH, pysnmp, requests
web_fetch, dsb) - TIDAK BOLEH ada logic keputusan/reasoning di sini, dan
TIDAK BOLEH dipanggil langsung dari `api/` atau `core/`.

Aturan akses: `agents/<nama>/*.py` adalah SATU-SATUNYA caller yang sah
untuk isi folder ini:

| Subfolder         | Dipanggil oleh          |
|--------------------|--------------------------|
| tools/ssh/         | agents/akane/network_tools.py |
| tools/snmp/        | agents/akane/network_tools.py |
| tools/mikrotik/    | agents/akane/network_tools.py |
| tools/network/     | agents/akane/network_tools.py |
| tools/inventory.py | agents/akane/network_tools.py |
| tools/vision/      | agents/hikari/vision.py |
| tools/web/         | agents/rei/ (web_search/web_fetch dianggap kemampuan riset REI, bukan network AKANE) |

TODO migrasi (lihat MIGRATION_PLAN.md Tahap 3-4):
    git mv tools/ssh        AIRA_ECOSYSTEM/tools/ssh
    git mv tools/snmp       AIRA_ECOSYSTEM/tools/snmp
    git mv tools/mikrotik   AIRA_ECOSYSTEM/tools/mikrotik
    git mv tools/network    AIRA_ECOSYSTEM/tools/network
    git mv tools/inventory.py AIRA_ECOSYSTEM/tools/inventory.py
    git mv tools/vision     AIRA_ECOSYSTEM/tools/vision
    git mv tools/web        AIRA_ECOSYSTEM/tools/web

`tools/registry.py` dan `tools/memory/` versi lama DIHAPUS setelah migrasi
(fungsinya digantikan `agents/*/registry.py` dan `core/memory.py`).
