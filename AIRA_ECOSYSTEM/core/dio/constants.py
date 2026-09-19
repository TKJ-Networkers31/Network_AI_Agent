"""
core/dio/constants.py — konstanta & daftar dukungan untuk Dynamic
Interaction Orchestrator (DIO), Phase 2.0.

Tidak ada logic di sini — murni daftar nilai yang sah, dipakai oleh
reasoning.py, builder.py, dan validator.py supaya "apa yang didukung"
punya SATU sumber kebenaran (single source of truth).
"""

SCHEMA_VERSION = "1.0"

MODE_DISPLAY = "display"
MODE_TEXT = "text"
MODE_CHOICE = "choice"
MODE_MIXED = "mixed"
MODE_FORM = "form"
MODE_WIZARD = "wizard"
MODE_APPROVAL = "approval"
MODE_REVIEW = "review"

SUPPORTED_MODES = frozenset({
    MODE_DISPLAY, MODE_TEXT, MODE_CHOICE, MODE_MIXED,
    MODE_FORM, MODE_WIZARD, MODE_APPROVAL, MODE_REVIEW,
})

COMPONENT_TEXT = "text"
COMPONENT_NUMBER = "number"
COMPONENT_PASSWORD = "password"
COMPONENT_TEXTAREA = "textarea"
COMPONENT_SELECT = "select"
COMPONENT_RADIO = "radio"
COMPONENT_CHECKBOX = "checkbox"
COMPONENT_SWITCH = "switch"
COMPONENT_SLIDER = "slider"
COMPONENT_DATE = "date"
COMPONENT_TIME = "time"
COMPONENT_FILE = "file"
COMPONENT_TABLE = "table"
COMPONENT_INFO = "info"
COMPONENT_DIVIDER = "divider"
COMPONENT_BUTTON = "button"
COMPONENT_SECTION = "section"

SUPPORTED_COMPONENTS = frozenset({
    COMPONENT_TEXT, COMPONENT_NUMBER, COMPONENT_PASSWORD, COMPONENT_TEXTAREA,
    COMPONENT_SELECT, COMPONENT_RADIO, COMPONENT_CHECKBOX, COMPONENT_SWITCH,
    COMPONENT_SLIDER, COMPONENT_DATE, COMPONENT_TIME, COMPONENT_FILE,
    COMPONENT_TABLE, COMPONENT_INFO, COMPONENT_DIVIDER, COMPONENT_BUTTON,
    COMPONENT_SECTION,
})

# Field type yang TIDAK wajib punya 'label' (murni dekoratif/struktural).
LABEL_OPTIONAL_COMPONENTS = frozenset({COMPONENT_DIVIDER, COMPONENT_INFO, COMPONENT_BUTTON})

# Field type yang WAJIB punya 'options' non-kosong.
OPTION_REQUIRED_COMPONENTS = frozenset({COMPONENT_SELECT, COMPONENT_RADIO})

ACTION_STYLES = frozenset({"primary", "secondary", "danger", "ghost"})

# Nama event Event Bus yang dipublish DIO (Phase 2.0). BUKAN bagian dari
# core/events.py::STANDARD_EVENTS (file itu tidak diubah) - event_bus
# menerima string event apa pun lewat publish().
EVENT_INTERACTION_STARTED = "interaction.started"
EVENT_INTERACTION_GENERATED = "interaction.generated"
EVENT_INTERACTION_COMPLETED = "interaction.completed"
EVENT_INTERACTION_CANCELLED = "interaction.cancelled"

DEFAULT_INTERACTION_MEMORY_TTL_SECONDS = 24 * 60 * 60  # 24 jam

# Mapping tipe data abstrak -> component default, dipakai builder.py
# kalau REI Planner hanya menyebut tipe generik (mis. "string", "int")
# tanpa component spesifik.
DATA_TYPE_TO_COMPONENT = {
    "string": COMPONENT_TEXT,
    "text": COMPONENT_TEXT,
    "long_text": COMPONENT_TEXTAREA,
    "number": COMPONENT_NUMBER,
    "integer": COMPONENT_NUMBER,
    "float": COMPONENT_NUMBER,
    "boolean": COMPONENT_SWITCH,
    "secret": COMPONENT_PASSWORD,
    "password": COMPONENT_PASSWORD,
    "date": COMPONENT_DATE,
    "time": COMPONENT_TIME,
    "file": COMPONENT_FILE,
    "choice": COMPONENT_SELECT,
    "enum": COMPONENT_SELECT,
}

MODE_LOCATION_PERMISSION = "location_permission"

SUPPORTED_MODES = frozenset({
    MODE_DISPLAY, MODE_TEXT, MODE_CHOICE, MODE_MIXED,
    MODE_FORM, MODE_WIZARD, MODE_APPROVAL, MODE_REVIEW,
    MODE_LOCATION_PERMISSION,
})

COMPONENT_LOCATION_PERMISSION = "location_permission"

SUPPORTED_COMPONENTS = frozenset({
    COMPONENT_TEXT, COMPONENT_NUMBER, COMPONENT_PASSWORD, COMPONENT_TEXTAREA,
    COMPONENT_SELECT, COMPONENT_RADIO, COMPONENT_CHECKBOX, COMPONENT_SWITCH,
    COMPONENT_SLIDER, COMPONENT_DATE, COMPONENT_TIME, COMPONENT_FILE,
    COMPONENT_TABLE, COMPONENT_INFO, COMPONENT_DIVIDER, COMPONENT_BUTTON,
    COMPONENT_SECTION, COMPONENT_LOCATION_PERMISSION,
})

LABEL_OPTIONAL_COMPONENTS = frozenset({
    COMPONENT_DIVIDER, COMPONENT_INFO, COMPONENT_BUTTON, COMPONENT_LOCATION_PERMISSION,
})

EVENT_INTERACTION_STARTED = "interaction.started"
EVENT_INTERACTION_GENERATED = "interaction.generated"
EVENT_INTERACTION_COMPLETED = "interaction.completed"
EVENT_INTERACTION_CANCELLED = "interaction.cancelled"
EVENT_INTERACTION_REQUESTED = "interaction.requested"