import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SERVER_URL = "http://localhost:8080/mcp"
TOOL_NAME = "pricing_api"


@dataclass
class TestCase:
    name: str
    payload: Dict[str, Any]
    expect: str  # "success" | "reject"
    expected_error: Optional[str] = None
    allow_validation_exception: bool = False

TEST_CASES = [
    TestCase(
        name="happy_path_base",
        payload={
            "codigo_postal": "28001",
            "edad": 55,
            "tipo_funeral": "inhumacion",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="success",
    ),
    TestCase(
        name="happy_path_cremacion_con_todo",
        payload={
            "codigo_postal": "28001",
            "edad": 70,
            "tipo_funeral": "cremacion",
            "velatorio": True,
            "ceremonia": True,
        },
        expect="success",
    ),
    TestCase(
        name="happy_path_sin_extras",
        payload={
            "codigo_postal": "28001",
            "edad": 60,
            "tipo_funeral": "inhumacion",
            "velatorio": False,
            "ceremonia": False,
        },
        expect="success",
    ),
    TestCase(
        name="cp_otra_zona",
        payload={
            "codigo_postal": "08001",
            "edad": 58,
            "tipo_funeral": "cremacion",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="success",
    ),
    TestCase(
        name="happy_path_incineracion_con_acento",
        payload={
            "codigo_postal": "28001",
            "edad": 55,
            "tipo_funeral": "incineración",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="success",
    ),
    TestCase(
        name="missing_required_field",
        payload={
            "codigo_postal": "28001",
            "edad": 55,
            "velatorio": True,
            "ceremonia": False,
        },
        expect="reject",
        allow_validation_exception=True,
    ),
    TestCase(
        name="invalid_tipo_funeral",
        payload={
            "codigo_postal": "28001",
            "edad": 55,
            "tipo_funeral": "entierro_rapido",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="reject",
        expected_error="INVALID_FUNERAL_TYPE",
    ),
    TestCase(
        name="edad_negativa",
        payload={
            "codigo_postal": "28001",
            "edad": -1,
            "tipo_funeral": "inhumacion",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="reject",
        expected_error="MIN_AGE_NOT_REACHED",
    ),
    TestCase(
        name="invalid_postal_code_max",
        payload={
            "codigo_postal": "99999",
            "edad": 55,
            "tipo_funeral": "inhumacion",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="reject",
        expected_error="INVALID_POSTAL_CODE",
    ),
    TestCase(
        name="invalid_postal_code_min",
        payload={
            "codigo_postal": "00001",
            "edad": 55,
            "tipo_funeral": "inhumacion",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="reject",
        expected_error="INVALID_POSTAL_CODE",
    ),
    TestCase(
        name="invalid_postal_code_less_numbers",
        payload={
            "codigo_postal": "0123",
            "edad": 55,
            "tipo_funeral": "inhumacion",
            "velatorio": True,
            "ceremonia": False,
        },
        expect="reject",
        expected_error="INVALID_POSTAL_CODE",
    ),
    TestCase(
        name="payload_vacio",
        payload={},
        expect="reject",
        allow_validation_exception=True,
    ),
]

def is_validation_error_payload(payload: Dict[str, Any]) -> bool:
    content_text = text_from_content(payload.get("content")).lower()

    validation_markers = [
        "validation error for call[pricing_api]",
        "validation errors for call[pricing_api]",
        "missing required argument",
        "type=missing_argument",
        "pydantic",
    ]
    return any(marker in content_text for marker in validation_markers)

def extract_error_code(payload: Dict[str, Any]) -> Optional[str]:
    structured = payload.get("structured_content")
    if isinstance(structured, dict):
        error = structured.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
    return None

def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return repr(obj)

def extract_result_payload(result: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "content": None,
        "structured_content": None,
        "meta": None,
    }

    for attr in ("content", "structured_content", "meta"):
        if hasattr(result, attr):
            data[attr] = getattr(result, attr)

    if data["structured_content"] is None and hasattr(result, "structuredContent"):
        data["structured_content"] = getattr(result, "structuredContent")

    return data

def text_from_content(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if hasattr(item, "text"):
                parts.append(str(item.text))
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    return str(content)

def is_business_error(payload: Dict[str, Any]) -> bool:
    structured = payload.get("structured_content")
    content_text = text_from_content(payload.get("content")).lower()

    if isinstance(structured, dict):
        if structured.get("ok") is False:
            return True
        if structured.get("error"):
            return True

    error_markers = [
        "limit_tries_reached",
        "min_age_not_reached",
        "invalid_funeral_type",
        "api_call_failed",
        "invalid_api_response",
        "unrecognized_api_response",
        "no he podido obtener la cotización",
    ]
    return any(marker in content_text for marker in error_markers)

def is_success_payload(payload: Dict[str, Any]) -> bool:
    structured = payload.get("structured_content")

    if not isinstance(structured, dict):
        return False

    return structured.get("ok") is True and not structured.get("error")


async def run_test(session: ClientSession, case: TestCase) -> bool:
    print("\n" + "=" * 90)
    print(f"TEST: {case.name}")
    print("PAYLOAD:")
    print(pretty(case.payload))

    start = time.perf_counter()

    try:
        result = await session.call_tool(TOOL_NAME, case.payload)
        elapsed = time.perf_counter() - start

        parsed = extract_result_payload(result)

        print(f"\nTIME: {elapsed:.2f}s")

        actual_error = extract_error_code(parsed)

        if case.expect == "success":
            success_ok = is_success_payload(parsed)
            business_error = is_business_error(parsed)
            passed = success_ok and not business_error
            actual_outcome = "success" if passed else "reject"

            print(f"DEBUG success_ok={success_ok} business_error={business_error}")

        else:
            business_error = is_business_error(parsed)
            validation_error = is_validation_error_payload(parsed)

            if case.expected_error is not None:
                passed = business_error and actual_error == case.expected_error
            elif case.allow_validation_exception:
                passed = business_error or validation_error
            else:
                passed = business_error

            actual_outcome = "reject" if (business_error or validation_error) else "success"

            print(
                f"DEBUG business_error={business_error} "
                f"validation_error={validation_error} "
                f"actual_error={actual_error} expected_error={case.expected_error}"
            )

        print(f"ACTUAL OUTCOME:   {actual_outcome}")
        print(f"ACTUAL ERROR:     {actual_error}")
        print(f"EXPECTED OUTCOME: {case.expect}")
        print(f"TEST STATUS:      {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        elapsed = time.perf_counter() - start
        error_text = repr(e)

        print(f"\nEXCEPTION after {elapsed:.2f}s:")
        print(error_text)

        if case.expect == "reject" and case.allow_validation_exception:
            passed = True
            actual_outcome = "reject"
        else:
            passed = False
            actual_outcome = "exception"

        print(f"ACTUAL OUTCOME:   {actual_outcome}")
        print("ACTUAL ERROR:     <validation_exception>")
        print(f"EXPECTED OUTCOME: {case.expect}")
        print(f"TEST STATUS:      {'PASS' if passed else 'FAIL'}")
        return passed

async def main() -> int:
    failed = 0
    passed = 0

    async with streamable_http_client(SERVER_URL) as transport:
        read_stream, write_stream, *_ = transport

        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print("TOOLS:", tool_names)

            if TOOL_NAME not in tool_names:
                print(f"La tool '{TOOL_NAME}' no está disponible")
                return 1

            for case in TEST_CASES:
                ok = await run_test(session, case)
                if ok:
                    passed += 1
                else:
                    failed += 1

    print("\n" + "#" * 90)
    print("RESUMEN FINAL")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"TOTAL:  {len(TEST_CASES)}")
    print("#" * 90)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    load_dotenv()
    exit_code = asyncio.run(main())
    raise SystemExit(exit_code)
