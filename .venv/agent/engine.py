import json
import time
import requests

from agent.ui import UI, Timer
from tools.registry import (
    TOOL_MAP,
    TOOL_CATEGORY,
    execute_tool,
)


OLLAMA_URL = (
    "http://localhost:11434/api/chat"
)

MODEL = "qwen3:1.7b"

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

Jawablah secara natural.

Untuk hasil teknis, gunakan tabel jika memang membuat
informasi lebih mudah dibaca.

Gunakan uraian jika lebih cocok.

Jangan memaksakan tabel pada semua jawaban.

Jika pengguna hanya ingin ngobrol, jawab seperti
asisten biasa dan jangan menggunakan tools.
"""


def build_tools():

    return [

        {
            "type": "function",
            "function": {
                "name": "ping",
                "description":
                    "Melakukan ping dari komputer agent "
                    "ke target jaringan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string"
                        },
                        "count": {
                            "type": "integer"
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
                    "Mengambil resource MikroTik.",
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
                    "Mengambil firewall filter MikroTik.",
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
                    "Mengambil NAT MikroTik.",
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
                    "Mengambil DHCP client MikroTik.",
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
                    "Mengambil neighbor discovery MikroTik.",
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
                "name": "list_devices",
                "description": "Menampilkan semua perangkat jaringan yang terdaftar di inventory.",
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
                "name": "ping",
                "description": "Melakukan ping ICMP ke sebuah hostname atau IP address.",
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
                    "required": ["target"]
                }
            }
        }
    ]


TOOLS = build_tools()


def call_ollama(messages):

    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
    }

    return requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300
    ).json()


def run(user_input):

    start = time.perf_counter()

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_input
        }
    ]

    tool_count = 0
    tool_names = []

    # ========================================================
    # ANALYSIS
    # ========================================================

    analysis_timer = Timer(
        "Menganalisis permintaan"
    )

    analysis_timer.start()

    response = call_ollama(
        messages
    )

    analysis_timer.stop()

    # ========================================================
    # AGENT LOOP
    # ========================================================

    while True:

        message = response.get(
            "message",
            {}
        )

        messages.append(
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

            UI.tool(
                name,
                category
            )

            tool_names.append(
                name
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

            tool_count += 1

            # ----------------------------------------------
            # TOOL RESULT
            # ----------------------------------------------

            messages.append({

                "role": "tool",

                "content": json.dumps(
                    result,
                    ensure_ascii=False
                )

            })

        # ====================================================
        # DECISION / FINALIZATION
        # ====================================================

        decision_timer = Timer(
            "Menganalisis hasil tools"
        )

        decision_timer.start()

        response = call_ollama(
            messages
        )

        decision_timer.stop()