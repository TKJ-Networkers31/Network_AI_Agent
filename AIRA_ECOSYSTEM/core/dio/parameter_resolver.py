"""
core/dio/parameter_resolver.py — Dynamic Interaction Orchestrator (DIO)
Universal Parameter Resolution, Classification & Contract Validation Engine.

Enforces:
1. Seven-state parameter classification:
   - PROVIDED: Explicitly supplied with valid value.
   - CONTEXT_RESOLVED: Derived from authoritative verified context (e.g. single inventory node).
   - DEFAULTED: Populated from official tool schema defaults.
   - MISSING: Required parameter is absent -> HALTS execution, NEVER fabricates values.
   - INVALID: Value fails data type, range, enum, or constraint validation.
   - AMBIGUOUS: Multiple valid candidate values exist -> HALTS execution, requests clarification.
   - NOT_APPLICABLE: Unrecognized or optional omitted parameter -> stripped from kwargs.
2. Parameter Provenance Tracking (USER_INPUT, SESSION_CONTEXT, VERIFIED_DEVICE_INVENTORY, TOOL_SCHEMA_DEFAULT, etc.).
3. Truthy/Falsy preservation: False and 0 are valid inputs, NEVER treated as missing.
4. Automatic DIO interactive schema generation (forms/choice pickers) when required parameters are missing or ambiguous.
"""

from __future__ import annotations

from enum import Enum
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.dio.models import (
    InteractionPlan,
    InteractionSchema,
    MissingField,
    ChoiceOption,
    InteractionState,
)
from core.dio.builder import SchemaBuilder

logger = logging.getLogger("aira.dio.parameter_resolver")


class ParameterStatus(str, Enum):
    PROVIDED = "PROVIDED"
    CONTEXT_RESOLVED = "CONTEXT_RESOLVED"
    DEFAULTED = "DEFAULTED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ParameterSource(str, Enum):
    USER_INPUT = "USER_INPUT"
    SESSION_CONTEXT = "SESSION_CONTEXT"
    ORGANIZATION_CONTEXT = "ORGANIZATION_CONTEXT"
    VERIFIED_DEVICE_INVENTORY = "VERIFIED_DEVICE_INVENTORY"
    TOOL_SCHEMA_DEFAULT = "TOOL_SCHEMA_DEFAULT"
    TOOL_RESULT = "TOOL_RESULT"


class ResolvedParameter:
    def __init__(
        self,
        name: str,
        value: Any,
        status: ParameterStatus,
        source: Optional[ParameterSource] = None,
        confidence: float = 1.0,
        validated: bool = False,
        error: Optional[str] = None,
        expected_type: Optional[str] = None,
        description: Optional[str] = None,
        choices: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        self.value = value
        self.status = status
        self.source = source
        self.confidence = confidence
        self.validated = validated
        self.error = error
        self.expected_type = expected_type
        self.description = description
        self.choices = choices or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.name,
            "value": self.value,
            "status": self.status.value,
            "source": self.source.value if self.source else None,
            "confidence": self.confidence,
            "validated": self.validated,
            "error": self.error,
            "expected_type": self.expected_type,
            "choices": self.choices,
        }


class ParameterResolutionResult:
    def __init__(
        self,
        tool_name: str,
        is_valid: bool,
        can_execute: bool,
        resolved_arguments: Dict[str, Any],
        parameters: Dict[str, ResolvedParameter],
        missing_required: List[str],
        invalid_parameters: List[str],
        ambiguous_parameters: List[str],
        stripped_parameters: List[str],
        provenance: List[Dict[str, Any]],
        interaction_schema: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        contract_defect: bool = False,
    ):
        self.tool_name = tool_name
        self.is_valid = is_valid
        self.can_execute = can_execute
        self.resolved_arguments = resolved_arguments
        self.parameters = parameters
        self.missing_required = missing_required
        self.invalid_parameters = invalid_parameters
        self.ambiguous_parameters = ambiguous_parameters
        self.stripped_parameters = stripped_parameters
        self.provenance = provenance
        self.interaction_schema = interaction_schema
        self.error_message = error_message
        self.contract_defect = contract_defect

    def to_early_tool_result(self) -> Dict[str, Any]:
        """Formats the resolution result for early return from Orchestrator / Planner."""
        if self.interaction_schema:
            return {
                "success": True,
                "tool": self.tool_name,
                "interaction_schema": self.interaction_schema,
                "missing_fields": self.missing_required,
                "message": (
                    "Parameter yang diperlukan belum lengkap atau membutuhkan klarifikasi. "
                    "Form interaktif DIO telah ditampilkan ke pengguna."
                ),
            }
        return {
            "success": False,
            "tool": self.tool_name,
            "error": self.error_message or "Validasi parameter gagal.",
            "invalid_parameters": self.invalid_parameters,
            "missing_parameters": self.missing_required,
        }


def build_device_registration_schema(
    initial_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generates a canonical, schema-driven device registration DIO form."""
    vals = initial_values or {}
    device_type_options = [
        ChoiceOption(value="mikrotik", label="MikroTik RouterOS"),
        ChoiceOption(value="linux", label="Linux Server"),
        ChoiceOption(value="switch", label="Managed Switch"),
        ChoiceOption(value="server", label="Generic Server"),
        ChoiceOption(value="other", label="Other / Unknown"),
    ]

    missing_fields = [
        MissingField(
            key="name",
            data_type="string",
            label="Device Name",
            required=True,
            default=vals.get("name", ""),
            placeholder="R1",
            helper_text="Nama unik untuk perangkat di inventory.",
        ),
        MissingField(
            key="host",
            data_type="string",
            label="Host / IP Address",
            required=True,
            default=vals.get("host", ""),
            placeholder="192.168.88.1",
            helper_text="Alamat IP atau hostname perangkat.",
        ),
        MissingField(
            key="username",
            data_type="string",
            label="SSH Username",
            required=True,
            default=vals.get("username", "admin"),
            placeholder="admin",
            helper_text="Username untuk login SSH.",
        ),
        MissingField(
            key="password",
            data_type="password",
            label="SSH Password",
            required=False,
            default=vals.get("password", ""),
            placeholder="••••••••",
            helper_text="Password SSH (opsional jika tanpa password).",
        ),
        MissingField(
            key="device_type",
            data_type="choice",
            label="Device Type",
            required=True,
            default=vals.get("device_type", "mikrotik"),
            options=device_type_options,
            helper_text="Tipe perangkat jaringan.",
        ),
        MissingField(
            key="port",
            data_type="integer",
            label="SSH Port",
            required=False,
            default=vals.get("port", 22),
            placeholder="22",
            helper_text="Port SSH standar (22).",
        ),
        MissingField(
            key="note",
            data_type="long_text",
            label="Notes",
            required=False,
            default=vals.get("note", ""),
            placeholder="Catatan bebas (lokasi, fungsi rak, dll)...",
            helper_text="Catatan operasional tambahan.",
        ),
    ]

    plan = InteractionPlan(
        intent="add_device",
        confidence=1.0,
        known_data={},
        missing_data=missing_fields,
        priority="normal",
    )

    builder = SchemaBuilder()
    schema = builder.build_schema(
        plan,
        title="Register Network Device",
        description="Masukkan informasi perangkat yang akan ditambahkan ke inventory.",
    )
    schema_dict = schema.to_dict()
    schema_dict["requested_for"] = "add_device"
    schema_dict["form_id"] = "device_registration"
    schema_dict["type"] = "interactive_form"
    schema_dict["submit"] = {"label": "Register Device"}
    schema_dict["actions"] = [
        {"id": "cancel", "label": "Batal", "style": "ghost", "disabled": False},
        {"id": "submit", "label": "Register Device", "style": "primary", "disabled": False},
    ]

    # Provide flat fields for any consumer reading schema.fields
    flat_fields = []
    for mf in missing_fields:
        component = "text"
        if mf.data_type in ("password", "secret"):
            component = "password"
        elif mf.data_type in ("integer", "number"):
            component = "number"
        elif mf.data_type == "choice":
            component = "select"
        elif mf.data_type == "long_text":
            component = "textarea"

        f_dict = {
            "name": mf.key,
            "id": mf.key,
            "label": mf.label,
            "type": component,
            "required": mf.required,
            "placeholder": mf.placeholder,
            "default": mf.default,
            "helper_text": mf.helper_text,
        }
        if mf.options:
            f_dict["options"] = [{"value": o.value, "label": o.label} for o in mf.options]
        flat_fields.append(f_dict)

    schema_dict["fields"] = flat_fields
    return schema_dict


class DIOParameterResolver:
    """Universal Parameter Resolution & Schema Validation Engine for AIRA DIO."""

    def __init__(self, schemas: Optional[List[Dict[str, Any]]] = None):
        self.schemas_by_name: Dict[str, Dict[str, Any]] = {}
        if schemas:
            self.register_schemas(schemas)

    def register_schemas(self, schemas: List[Dict[str, Any]]) -> None:
        """Indexes schemas by tool function name."""
        for entry in schemas:
            func = entry.get("function") if isinstance(entry, dict) else None
            if func and func.get("name"):
                self.schemas_by_name[func["name"]] = func

    def resolve(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        inventory_devices: Optional[List[Dict[str, Any]]] = None,
    ) -> ParameterResolutionResult:
        """
        Resolves, verifies, and classifies arguments for a tool call.
        Guarantees that missing required parameters trigger DIO interactive forms,
        invalid parameters are rejected, and unknown arguments are stripped.
        """
        context = context or {}
        func_schema = self.schemas_by_name.get(tool_name)

        if not func_schema:
            # Schema not registered -> contract defect
            return ParameterResolutionResult(
                tool_name=tool_name,
                is_valid=False,
                can_execute=False,
                resolved_arguments=arguments,
                parameters={},
                missing_required=[],
                invalid_parameters=[],
                ambiguous_parameters=[],
                stripped_parameters=[],
                provenance=[],
                error_message=f"Contract Defect: Skema untuk tool '{tool_name}' tidak ditemukan di registry DIO.",
                contract_defect=True,
            )

        params_schema = func_schema.get("parameters") or {}
        properties = params_schema.get("properties") or {}
        required_keys = set(params_schema.get("required") or [])

        resolved_args: Dict[str, Any] = {}
        parameters: Dict[str, ResolvedParameter] = {}
        missing_required: List[str] = []
        invalid_parameters: List[str] = []
        ambiguous_parameters: List[str] = []
        stripped_parameters: List[str] = []
        provenance_list: List[Dict[str, Any]] = []

        # 1. Process defined properties
        for prop_name, prop_spec in properties.items():
            expected_type = prop_spec.get("type", "string")
            is_req = prop_name in required_keys
            prop_desc = prop_spec.get("description", "")
            has_default = "default" in prop_spec
            default_val = prop_spec.get("default")

            if prop_name in arguments:
                raw_val = arguments[prop_name]

                # Check for explicit None or empty string on required fields
                if raw_val is None or (isinstance(raw_val, str) and raw_val.strip() == ""):
                    if is_req:
                        if has_default:
                            rp = ResolvedParameter(
                                name=prop_name,
                                value=default_val,
                                status=ParameterStatus.DEFAULTED,
                                source=ParameterSource.TOOL_SCHEMA_DEFAULT,
                                confidence=1.0,
                                validated=True,
                                expected_type=expected_type,
                                description=prop_desc,
                            )
                            resolved_args[prop_name] = default_val
                        else:
                            rp = ResolvedParameter(
                                name=prop_name,
                                value=None,
                                status=ParameterStatus.MISSING,
                                source=None,
                                confidence=0.0,
                                validated=False,
                                error="Parameter wajib ini belum diisi.",
                                expected_type=expected_type,
                                description=prop_desc,
                            )
                            missing_required.append(prop_name)
                    else:
                        # Optional parameter with empty/None value
                        if has_default:
                            rp = ResolvedParameter(
                                name=prop_name,
                                value=default_val,
                                status=ParameterStatus.DEFAULTED,
                                source=ParameterSource.TOOL_SCHEMA_DEFAULT,
                                confidence=1.0,
                                validated=True,
                                expected_type=expected_type,
                            )
                            resolved_args[prop_name] = default_val
                        else:
                            rp = ResolvedParameter(
                                name=prop_name,
                                value=None,
                                status=ParameterStatus.NOT_APPLICABLE,
                                confidence=1.0,
                                validated=True,
                            )
                    parameters[prop_name] = rp
                    provenance_list.append(rp.to_dict())
                    continue

                # Device resolution check (device_name / device_id)
                if prop_name in ("device_name", "device_id") and inventory_devices is not None:
                    dev_res = self._resolve_device_parameter(
                        prop_name=prop_name,
                        raw_value=raw_val,
                        inventory_devices=inventory_devices,
                        is_required=is_req,
                    )
                    parameters[prop_name] = dev_res
                    provenance_list.append(dev_res.to_dict())
                    if dev_res.status in (ParameterStatus.PROVIDED, ParameterStatus.CONTEXT_RESOLVED):
                        resolved_args[prop_name] = dev_res.value
                    elif dev_res.status == ParameterStatus.AMBIGUOUS:
                        ambiguous_parameters.append(prop_name)
                    elif dev_res.status == ParameterStatus.MISSING:
                        missing_required.append(prop_name)
                    elif dev_res.status == ParameterStatus.INVALID:
                        invalid_parameters.append(prop_name)
                    continue

                # Strict type and constraint validation
                val_ok, coerced_val, err = self._validate_and_coerce(raw_val, prop_spec)
                if val_ok:
                    rp = ResolvedParameter(
                        name=prop_name,
                        value=coerced_val,
                        status=ParameterStatus.PROVIDED,
                        source=ParameterSource.USER_INPUT,
                        confidence=1.0,
                        validated=True,
                        expected_type=expected_type,
                        description=prop_desc,
                    )
                    resolved_args[prop_name] = coerced_val
                else:
                    rp = ResolvedParameter(
                        name=prop_name,
                        value=raw_val,
                        status=ParameterStatus.INVALID,
                        source=ParameterSource.USER_INPUT,
                        confidence=0.0,
                        validated=False,
                        error=err,
                        expected_type=expected_type,
                        description=prop_desc,
                    )
                    invalid_parameters.append(prop_name)

                parameters[prop_name] = rp
                provenance_list.append(rp.to_dict())

            else:
                # Key is absent from arguments
                # Special device resolution if required device_name is missing
                if prop_name in ("device_name", "device_id") and inventory_devices is not None:
                    dev_res = self._resolve_device_parameter(
                        prop_name=prop_name,
                        raw_value=None,
                        inventory_devices=inventory_devices,
                        is_required=is_req,
                    )
                    parameters[prop_name] = dev_res
                    provenance_list.append(dev_res.to_dict())
                    if dev_res.status == ParameterStatus.CONTEXT_RESOLVED:
                        resolved_args[prop_name] = dev_res.value
                    elif dev_res.status == ParameterStatus.AMBIGUOUS:
                        ambiguous_parameters.append(prop_name)
                    elif dev_res.status == ParameterStatus.MISSING:
                        missing_required.append(prop_name)
                    continue

                # Check default in schema
                if has_default:
                    rp = ResolvedParameter(
                        name=prop_name,
                        value=default_val,
                        status=ParameterStatus.DEFAULTED,
                        source=ParameterSource.TOOL_SCHEMA_DEFAULT,
                        confidence=1.0,
                        validated=True,
                        expected_type=expected_type,
                        description=prop_desc,
                    )
                    resolved_args[prop_name] = default_val
                elif is_req:
                    rp = ResolvedParameter(
                        name=prop_name,
                        value=None,
                        status=ParameterStatus.MISSING,
                        source=None,
                        confidence=0.0,
                        validated=False,
                        error="Parameter wajib ini belum tersedia.",
                        expected_type=expected_type,
                        description=prop_desc,
                    )
                    missing_required.append(prop_name)
                else:
                    # Optional parameter omitted
                    rp = ResolvedParameter(
                        name=prop_name,
                        value=None,
                        status=ParameterStatus.NOT_APPLICABLE,
                        source=None,
                        confidence=1.0,
                        validated=True,
                        expected_type=expected_type,
                    )

                parameters[prop_name] = rp
                provenance_list.append(rp.to_dict())

        # 2. Check for unknown/unrecognized arguments
        for arg_key in arguments.keys():
            if arg_key not in properties:
                stripped_parameters.append(arg_key)
                rp = ResolvedParameter(
                    name=arg_key,
                    value=arguments[arg_key],
                    status=ParameterStatus.NOT_APPLICABLE,
                    source=ParameterSource.USER_INPUT,
                    confidence=0.0,
                    validated=False,
                    error=f"Parameter '{arg_key}' tidak tercantum dalam kontrak tool '{tool_name}'.",
                )
                parameters[arg_key] = rp
                provenance_list.append(rp.to_dict())

        # 3. Formulate outcome & DIO schema if required inputs are missing or ambiguous
        has_missing = len(missing_required) > 0
        has_invalid = len(invalid_parameters) > 0
        has_ambiguous = len(ambiguous_parameters) > 0

        can_execute = not has_missing and not has_invalid and not has_ambiguous
        is_valid = not has_invalid

        interaction_schema: Optional[Dict[str, Any]] = None
        error_message: Optional[str] = None

        if has_invalid:
            err_details = [
                f"{p}: {parameters[p].error}"
                for p in invalid_parameters
                if parameters[p].error
            ]
            error_message = (
                f"Validasi parameter gagal untuk tool '{tool_name}': " + "; ".join(err_details)
            )

        elif has_missing or has_ambiguous:
            # Build interactive DIO schema
            interaction_schema = self._build_dio_interaction_schema(
                tool_name=tool_name,
                parameters=parameters,
                missing_keys=missing_required,
                ambiguous_keys=ambiguous_parameters,
            )

        return ParameterResolutionResult(
            tool_name=tool_name,
            is_valid=is_valid,
            can_execute=can_execute,
            resolved_arguments=resolved_args,
            parameters=parameters,
            missing_required=missing_required,
            invalid_parameters=invalid_parameters,
            ambiguous_parameters=ambiguous_parameters,
            stripped_parameters=stripped_parameters,
            provenance=provenance_list,
            interaction_schema=interaction_schema,
            error_message=error_message,
        )

    def _validate_and_coerce(self, value: Any, spec: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
        """Validates and coerces a value against its JSON schema specification."""
        target_type = spec.get("type", "string")

        # 1. Boolean
        if target_type == "boolean":
            if isinstance(value, bool):
                return True, value, None
            if isinstance(value, str):
                s = value.strip().lower()
                if s in ("true", "1", "yes"):
                    return True, True, None
                if s in ("false", "0", "no"):
                    return True, False, None
            return False, value, "Harus berupa nilai boolean (true/false)."

        # 2. Integer
        if target_type == "integer":
            if isinstance(value, bool):
                return False, value, "Nilai boolean tidak diizinkan untuk integer."
            if isinstance(value, int):
                coerced = value
            elif isinstance(value, str) and re.match(r"^-?\d+$", value.strip()):
                coerced = int(value.strip())
            else:
                return False, value, f"Harus berupa bilangan bulat (integer), diterima: {type(value).__name__}."

            if "minimum" in spec and coerced < spec["minimum"]:
                return False, coerced, f"Nilai {coerced} kurang dari batas minimum {spec['minimum']}."
            if "maximum" in spec and coerced > spec["maximum"]:
                return False, coerced, f"Nilai {coerced} melebihi batas maksimum {spec['maximum']}."
            return True, coerced, None

        # 3. Number / Float
        if target_type in ("number", "float"):
            if isinstance(value, bool):
                return False, value, "Nilai boolean tidak diizinkan untuk number."
            if isinstance(value, (int, float)):
                coerced = float(value)
            elif isinstance(value, str):
                try:
                    coerced = float(value.strip())
                except ValueError:
                    return False, value, f"Harus berupa angka (number), diterima: '{value}'."
            else:
                return False, value, "Harus berupa angka."

            if "minimum" in spec and coerced < spec["minimum"]:
                return False, coerced, f"Nilai {coerced} kurang dari batas minimum {spec['minimum']}."
            if "maximum" in spec and coerced > spec["maximum"]:
                return False, coerced, f"Nilai {coerced} melebihi batas maksimum {spec['maximum']}."
            return True, coerced, None

        # 4. String
        if target_type == "string":
            if not isinstance(value, str):
                # Safe string coercion for simple scalars
                if isinstance(value, (int, float)):
                    value = str(value)
                else:
                    return False, value, f"Harus berupa string, diterima: {type(value).__name__}."

            # Check Enum constraints
            if "enum" in spec and value not in spec["enum"]:
                valid_options = ", ".join(f"'{o}'" for o in spec["enum"])
                return False, value, f"Nilai '{value}' tidak valid. Pilihan yang diizinkan: [{valid_options}]."

            if "pattern" in spec:
                try:
                    if not re.search(spec["pattern"], value):
                        return False, value, f"Nilai tidak memenuhi pola regex format yang ditentukan."
                except Exception:
                    pass
            return True, value, None

        # 5. Array
        if target_type == "array":
            if isinstance(value, (list, tuple)):
                return True, list(value), None
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return True, parsed, None
                except Exception:
                    pass
            return False, value, f"Harus berupa array/list, diterima: {type(value).__name__}."

        # 6. Object / Dict
        if target_type == "object":
            if isinstance(value, dict):
                return True, value, None
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return True, parsed, None
                except Exception:
                    pass
            return False, value, f"Harus berupa object/JSON dictionary, diterima: {type(value).__name__}."

        # Default fallback
        return True, value, None

    def _resolve_device_parameter(
        self,
        prop_name: str,
        raw_value: Optional[str],
        inventory_devices: List[Dict[str, Any]],
        is_required: bool,
    ) -> ResolvedParameter:
        """Resolves device target against verified inventory records."""
        if not inventory_devices:
            return ResolvedParameter(
                name=prop_name,
                value=None,
                status=ParameterStatus.MISSING if is_required else ParameterStatus.NOT_APPLICABLE,
                source=None,
                confidence=0.0,
                validated=False,
                error="Tidak ada perangkat terdaftar dalam inventory jaringan.",
            )

        given = str(raw_value or "").strip()
        name_map = {str(d.get("name") or "").lower(): str(d.get("name") or "") for d in inventory_devices}

        # Exact match
        if given and given.lower() in name_map:
            canon_name = name_map[given.lower()]
            return ResolvedParameter(
                name=prop_name,
                value=canon_name,
                status=ParameterStatus.PROVIDED,
                source=ParameterSource.USER_INPUT,
                confidence=1.0,
                validated=True,
            )

        # Partial match candidates
        if given:
            matches = [
                d for d in inventory_devices
                if given.lower() in str(d.get("name", "")).lower() or given in str(d.get("host", ""))
            ]
            if len(matches) == 1:
                canon_name = matches[0]["name"]
                return ResolvedParameter(
                    name=prop_name,
                    value=canon_name,
                    status=ParameterStatus.CONTEXT_RESOLVED,
                    source=ParameterSource.VERIFIED_DEVICE_INVENTORY,
                    confidence=0.9,
                    validated=True,
                )
            if len(matches) > 1:
                choices = [
                    {"value": d["name"], "label": f"{d['name']} ({d.get('host', '')})"}
                    for d in matches
                ]
                return ResolvedParameter(
                    name=prop_name,
                    value=None,
                    status=ParameterStatus.AMBIGUOUS,
                    source=ParameterSource.VERIFIED_DEVICE_INVENTORY,
                    confidence=0.5,
                    validated=False,
                    choices=choices,
                    error=f"Terdapat beberapa perangkat yang cocok dengan '{given}'.",
                )

        # If not given and only 1 device in inventory -> auto-resolve
        if not given and len(inventory_devices) == 1:
            single = inventory_devices[0]["name"]
            return ResolvedParameter(
                name=prop_name,
                value=single,
                status=ParameterStatus.CONTEXT_RESOLVED,
                source=ParameterSource.VERIFIED_DEVICE_INVENTORY,
                confidence=1.0,
                validated=True,
            )

        # If multiple devices in inventory and not given -> Ambiguous clarification required
        choices = [
            {"value": d["name"], "label": f"{d['name']} ({d.get('host', '')})"}
            for d in inventory_devices
        ]
        return ResolvedParameter(
            name=prop_name,
            value=None,
            status=ParameterStatus.AMBIGUOUS if is_required else ParameterStatus.NOT_APPLICABLE,
            source=ParameterSource.VERIFIED_DEVICE_INVENTORY,
            confidence=0.0,
            validated=False,
            choices=choices,
            error="Pilih perangkat target dari daftar inventory.",
        )



    def _build_dio_interaction_schema(
        self,
        tool_name: str,
        parameters: Dict[str, ResolvedParameter],
        missing_keys: List[str],
        ambiguous_keys: List[str],
    ) -> Dict[str, Any]:
        """Constructs an interactive DIO form/picker for missing or ambiguous inputs."""
        # Special-case canonical device registration to return full schema-driven form
        if tool_name == "add_device":
            init_vals = {k: rp.value for k, rp in parameters.items() if rp.value is not None}
            return build_device_registration_schema(init_vals)

        missing_fields: List[MissingField] = []

        # Handle ambiguous keys with choice options
        for amb_key in ambiguous_keys:
            rp = parameters.get(amb_key)
            if rp and rp.choices:
                opts = [ChoiceOption(value=c["value"], label=c["label"]) for c in rp.choices]
                missing_fields.append(
                    MissingField(
                        key=amb_key,
                        data_type="choice",
                        label=f"Pilih {amb_key.replace('_', ' ').title()}",
                        required=True,
                        options=opts,
                        helper_text=rp.error or "Tentukan nilai yang dimaksud dari opsi di atas.",
                    )
                )

        # Handle missing required keys
        for miss_key in missing_keys:
            rp = parameters.get(miss_key)
            dtype = rp.expected_type if rp and rp.expected_type else "string"
            missing_fields.append(
                MissingField(
                    key=miss_key,
                    data_type=dtype,
                    label=miss_key.replace("_", " ").title(),
                    required=True,
                    placeholder=f"Masukkan {miss_key}...",
                    helper_text=rp.description if rp else None,
                )
            )

        plan = InteractionPlan(
            intent=f"resolve_{tool_name}",
            confidence=0.9,
            known_data={},
            missing_data=missing_fields,
            priority="normal",
        )

        builder = SchemaBuilder()
        title = f"Parameter Diperlukan: {tool_name}"
        desc = (
            f"Untuk menjalankan operasi '{tool_name}', AIRA membutuhkan informasi tambahan berikut. "
            "Silakan lengkapi form atau pilih opsi di bawah:"
        )
        schema = builder.build_schema(plan, title=title, description=desc)
        schema_dict = schema.to_dict()
        schema_dict["requested_for"] = tool_name
        return schema_dict
