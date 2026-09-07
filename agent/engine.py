import json
import time

from agent.ui import UI, Timer
from agent.logger import (
    log_tool_call,
    log_tool_result,
    log_error,
)
from tools.registry import (
    TOOL_MAP,
    TOOL_CATEGORY,
    DANGEROUS_TOOLS,
    execute_tool,
)
from agent.providers import call_model


MAX_TOOL_CALLS = 10


SYSTEM_PROMPT = """
Kamu adalah Network AI Agent.

Kamu adalah asisten umum yang bisa berbicara santai
dan membantu pengguna dalam berbagai hal.

Kamu juga memiliki tools untuk melakukan observasi
terhadap jaringan dan perangkat.

Gunakan tools hanya jika memang diperlukan.

Jangan menggunakan tool untuk pertanyaan umum yang
tidak membutuhkan data aktual.

Jika menggunakan tool, gunakan hasil tool sebagai
sumber fakta.

Jangan mengarang hasil observasi.

Bedakan:
- fakta dari perangkat
- kesimpulan berdasarkan fakta
- informasi yang belum diketahui

Untuk perangkat jaringan, jangan mengasumsikan fungsi
interface berdasarkan nama seperti ether1, ether5,
wlan1, sfp1, dan sebagainya.

Jika ingin menentukan fungsi interface, gunakan data
aktual seperti IP address, routing, DHCP, neighbor,
NAT, dan connectivity.

Jika kamu tidak yakin nama device yang valid, gunakan
tool 'list_devices' terlebih dahulu.

Kamu memiliki riwayat percakapan sebelumnya dalam sesi
ini. Gunakan konteks tersebut jika relevan, tapi jika
data observasi sebelumnya kemungkinan sudah usang
(misalnya status interface atau resource yang bisa
berubah), panggil tool lagi untuk data terbaru alih-alih
mengasumsikan data lama masih berlaku.

Jawablah secara natural.

Untuk hasil teknis, gunakan tabel jika memang membuat
informasi lebih mudah dibaca.

Gunakan uraian jika lebih cocok.

Jangan memaksakan tabel pada semua jawaban.

Jika pengguna hanya ingin ngobrol, jawab seperti
asisten biasa dan jangan menggunakan tools.

Kamu memiliki akses ke web_search dan web_fetch untuk
mencari informasi di internet.

Gunakan web_search hanya jika pertanyaan membutuhkan
informasi terkini, berita, atau fakta yang mungkin
berubah dari waktu ke waktu.

Jangan gunakan web_search untuk pertanyaan yang bisa
kamu jawab dari pengetahuan umum.

Setelah web_search, gunakan web_fetch hanya jika snippet
hasil pencarian belum cukup menjawab pertanyaan.

Selalu sebutkan sumber (url) ketika menjawab berdasarkan
hasil pencarian internet.

Kamu memiliki long-term memory yang tersimpan lintas sesi
lewat tool 'remember', 'recall', dan 'forget'.

Gunakan 'remember' jika user memberi informasi yang jelas
sebaiknya diingat untuk sesi mendatang, seperti preferensi,
threshold monitoring, atau konfigurasi standar.

Gunakan 'recall' jika user menanyakan sesuatu yang mungkin
pernah disimpan sebelumnya dan tidak ada di riwayat
percakapan saat ini.

Jangan gunakan 'remember' untuk hal sepele atau sementara
yang tidak perlu diingat lintas sesi.
"""


def build_tools():

    return [

        {
            "type": "function",
            "function": {
                "name": "ping",
                "description":
                    "Melakukan ping ICMP dari komputer agent "
                    "ke target jaringan (hostname atau IP).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Hostname atau IP address tujuan."
                        },
                        "count": {
                            "type": "integer",
                            "description": "Jumlah paket ping.",
                            "default": 4
                        }
                    },
                    "required": [
                        "target"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "nslookup",
                "description":
                    "Melakukan DNS lookup terhadap hostname "
                    "atau domain.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "target"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "traceroute",
                "description":
                    "Melakukan traceroute menuju target.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "target"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "list_devices",
                "description":
                    "Menampilkan semua perangkat jaringan "
                    "yang terdaftar di inventory.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_interfaces",
                "description":
                    "Mengambil interface dan status interface "
                    "dari MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_ip_addresses",
                "description":
                    "Mengambil IP address MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_routes",
                "description":
                    "Mengambil routing table MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_resources",
                "description":
                    "Mengambil resource (CPU, memory, uptime) MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_identity",
                "description":
                    "Mengambil identity/nama sistem MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_firewall",
                "description":
                    "Mengambil firewall filter rules MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_nat",
                "description":
                    "Mengambil aturan NAT MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_dns",
                "description":
                    "Mengambil konfigurasi DNS MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_dhcp_client",
                "description":
                    "Mengambil konfigurasi DHCP client MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_dhcp_server",
                "description":
                    "Mengambil konfigurasi DHCP server MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_neighbors",
                "description":
                    "Mengambil hasil neighbor discovery (MNDP/CDP) MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "get_arp",
                "description":
                    "Mengambil ARP table MikroTik.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "snmp_get_system_info",
                "description":
                    "Mengambil info sistem via SNMP: CPU load, "
                    "memory usage, uptime, nama sistem. Lebih "
                    "ringan daripada SSH untuk monitoring rutin.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "snmp_get_interface_traffic",
                "description":
                    "Mengambil traffic tiap interface via SNMP: "
                    "status up/down, bytes in/out. Cocok untuk "
                    "monitoring bandwidth per-interface.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "device_name"
                    ]
                }
            }
        },
                {
            "type": "function",
            "function": {
                "name": "web_search",
                "description":
                    "Mencari informasi terkini di internet. "
                    "Gunakan untuk pertanyaan tentang fakta yang "
                    "berubah-ubah, berita, atau hal di luar "
                    "pengetahuanmu.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Kata kunci pencarian."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Jumlah hasil (default 5).",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description":
                    "Mengambil isi teks dari sebuah URL. Gunakan "
                    "setelah web_search jika butuh detail lebih "
                    "dalam dari salah satu hasil pencarian.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL halaman yang ingin dibaca."
                        }
                    },
                    "required": ["url"]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "remember",
                "description":
                    "Simpan fakta penting yang harus diingat "
                    "lintas sesi, misalnya preferensi user, "
                    "threshold monitoring, atau konfigurasi "
                    "standar yang disebutkan user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Nama singkat fakta, misal 'threshold_cpu_r1'."
                        },
                        "value": {
                            "type": "string",
                            "description": "Isi fakta yang ingin diingat."
                        }
                    },
                    "required": ["key", "value"]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "recall",
                "description":
                    "Cari fakta yang pernah disimpan sebelumnya "
                    "berdasarkan kata kunci.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string"
                        }
                    },
                    "required": ["query"]
                }
            }
        },

        {
            "type": "function",
            "function": {
                "name": "forget",
                "description":
                    "Hapus fakta yang tersimpan berdasarkan key-nya.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string"
                        }
                    },
                    "required": ["key"]
                }
            }
        },

    ]


TOOLS = build_tools()


def run(user_input, memory):

    start = time.perf_counter()

    memory.add_user(
        user_input
    )

    tool_count = 0
    tool_names = []

    # ========================================================
    # ANALYSIS
    # ========================================================

    analysis_timer = Timer(
        "Menganalisis permintaan"
    )

    analysis_timer.start()

    response = call_model(
        memory.get_messages(),
        TOOLS
    )

    analysis_timer.stop()

    if "error" in response:

        UI.error(
            response["error"]
        )

        return (
            f"Terjadi error saat menghubungi model: "
            f"{response['error']}"
        )

    # ========================================================
    # AGENT LOOP
    # ========================================================

    while True:

        message = response.get(
            "message",
            {}
        )

        memory.add_message(
            message
        )

        tool_calls = message.get(
            "tool_calls",
            []
        )

        # ====================================================
        # NO TOOL
        # ====================================================

        if not tool_calls:

            answer = message.get(
                "content",
                ""
            )

            total = (
                time.perf_counter()
                - start
            )

            UI.result(
                answer
            )

            UI.summary(
                total,
                tool_count
            )

            return answer

        # ====================================================
        # TOOL PHASE
        # ====================================================

        UI.phase(
            f"Menggunakan tools ({len(tool_calls)})"
        )

        for call in tool_calls:

            if tool_count >= MAX_TOOL_CALLS:

                UI.error(
                    "Batas tool call tercapai."
                )

                return (
                    "Saya menghentikan proses karena "
                    "jumlah observasi sudah mencapai batas."
                )

            function = call.get(
                "function",
                {}
            )

            name = function.get(
                "name"
            )

            arguments = function.get(
                "arguments",
                {}
            )

            if isinstance(
                arguments,
                str
            ):

                try:
                    arguments = json.loads(
                        arguments
                    )

                except json.JSONDecodeError:

                    arguments = {}

            category = TOOL_CATEGORY.get(
                name,
                "tool"
            )

            # ----------------------------------------------
            # KONFIRMASI UNTUK TOOL BERBAHAYA
            # ----------------------------------------------

            if name in DANGEROUS_TOOLS:

                approved = UI.confirm(
                    name,
                    arguments
                )

                if not approved:

                    UI.tool(
                        name,
                        category,
                        status=False
                    )

                    memory.add_tool_result(
                        json.dumps({
                            "success": False,
                            "error": "Dibatalkan oleh user."
                        }),
                        tool_call_id=call.get("id")
                    )

                    tool_count += 1
                    continue

            UI.tool(
                name,
                category
            )

            tool_names.append(
                name
            )

            device_name = arguments.get(
                "device_name"
            )

            log_tool_call(
                name,
                arguments,
                device_name
            )

            # ----------------------------------------------
            # EXECUTE
            # ----------------------------------------------

            tool_timer = Timer(
                f"Menjalankan {name}"
            )

            tool_timer.start()

            result = execute_tool(
                name,
                arguments
            )

            tool_timer.stop()

            log_tool_result(
                name,
                result
            )

            tool_count += 1

            # ----------------------------------------------
            # TOOL RESULT
            # ----------------------------------------------

            memory.add_tool_result(
                json.dumps(
                    result,
                    ensure_ascii=False
                ),
                tool_call_id=call.get("id")
            )

        # ====================================================
        # DECISION / FINALIZATION
        # ====================================================

        decision_timer = Timer(
            "Menganalisis hasil tools"
        )

        decision_timer.start()

        response = call_model(
            memory.get_messages(),
            TOOLS
        )

        decision_timer.stop()

        if "error" in response:

            UI.error(
                response["error"]
            )

            return (
                f"Terjadi error saat menghubungi model: "
                f"{response['error']}"
            )