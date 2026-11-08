"""
tests/test_streaming.py — unit test backend streaming (Sprint 2.5).

Cakupan:
  1. Provider client   : Ollama NDJSON + OpenAI-compatible SSE (fragmen tool_calls,
                         usage, komentar keep-alive, stream terpotong, error di tengah,
                         stream_options ditolak, provider mengabaikan stream, Stop).
  2. Streaming NYATA   : server HTTP lokal ber-chunked yang MENAHAN sisa respons
                         sampai client sudah menerima chunk pertama. Kalau client
                         membuffer seluruh respons lalu memotongnya, test ini gagal
                         (deadlock -> gate timeout).
  3. call_model        : sink start/delta, retry, fallback, stream_unsupported ->
                         non-streaming, cancelled tanpa fallback, jalur lama utuh.
  4. Planner           : event stream.* di Event Bus, nomor call/attempt, tool loop,
                         error, cancelled, jalur non-streaming tidak berubah.
  5. Urutan + isolasi  : Planner -> Event Bus -> WS bridge, dua sesi paralel.
  6. Flag & event      : stream_enabled_for_turn, EventNames, peta WS.
  7. Brain             : flag stream diteruskan hanya kalau True (kompatibel dengan
                         orchestrator lama), BrainResponse.streamed.
  8. Runtime State     : event stream.* tidak mengubah state.

Semua test berjalan offline (server hanya 127.0.0.1) dan memakai DB sementara.
Test yang butuh Planner/Brain asli di-skip (bukan gagal) kalau dependency
runtime-nya tidak terpasang.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_streaming -v
"""

import asyncio
import copy
import json
import os
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import requests

import agents.rei.provider_client as pc
from agents.rei.provider_client import ProviderClient, call_model, EMPTY_RESPONSE_MARKER
from api.ws_bridge import (
    DEFAULT_WS_EVENT_MAP, STREAM_WS_EVENT_MAP, WebSocketEventBridge, stream_enabled_for_turn,
)
from core.events import EventBus, EventNames, STANDARD_EVENTS, event_bus, event_scope
from core.model_types import TaskClassification
from tests.test_model_router import EventCapture, make_env

MODEL = {"id": "glm", "display_name": "GLM 5.2", "provider": "openrouter", "fallback_from": None}


# ============================================================ fake HTTP (requests.post)

class FakeStreamResponse:
    """Meniru requests.Response(stream=True). Item Exception di `lines` di-raise saat dibaca."""

    def __init__(self, lines=(), status=200, headers=None, body=b""):
        self.status_code = status
        self.headers = headers or {}
        self._lines = list(lines)
        self._body = body
        self.closed = False
        self.read_lines = 0

    @property
    def content(self):
        return self._body

    @property
    def text(self):
        return self._body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self._body)

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)

    def iter_lines(self, chunk_size=None, decode_unicode=False):
        for line in self._lines:
            if isinstance(line, Exception):
                raise line
            self.read_lines += 1
            yield line if isinstance(line, bytes) else line.encode("utf-8")


def nd(*objs):
    """NDJSON Ollama: satu objek per baris."""
    return [json.dumps(o).encode() for o in objs]


def sse(*objs, done=True):
    """SSE OpenAI-compatible: 'data: {...}' + baris kosong; opsional [DONE]."""
    lines = []
    for obj in objs:
        lines += [b"data: " + json.dumps(obj).encode(), b""]
    if done:
        lines += [b"data: [DONE]", b""]
    return lines


def oa(content=None, tool_calls=None, finish=None, usage=None):
    """Satu chunk chat.completion.chunk."""
    chunk = {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
    if content is not None:
        chunk["choices"][0]["delta"]["content"] = content
    if tool_calls is not None:
        chunk["choices"][0]["delta"]["tool_calls"] = tool_calls
    if usage is not None:
        chunk["usage"] = usage
    return chunk


def patch_post(*responses):
    """Ganti requests.post dengan antrean response palsu; kembalikan (patcher, calls)."""
    calls, queue = [], list(responses)

    def fake_post(url, json=None, headers=None, timeout=None, stream=False, **kwargs):
        calls.append({"url": url, "json": copy.deepcopy(json), "headers": headers, "stream": stream})
        return queue.pop(0)

    return mock.patch.object(pc.requests, "post", fake_post), calls


class Collector:
    def __init__(self):
        self.deltas = []

    def __call__(self, text):
        self.deltas.append(text)


ENV_KEY = mock.patch.dict(os.environ, {"OPENROUTER_API": "test-key"})


# ============================================================ 1. PROVIDER: OLLAMA

class TestOllamaStream(unittest.TestCase):

    def stream(self, response, **kwargs):
        patcher, calls = patch_post(*response) if isinstance(response, tuple) else patch_post(response)
        sink = Collector()
        with patcher:
            result = ProviderClient.chat_stream(
                "ollama", "qwen3:1.7b", [{"role": "user", "content": "hi"}], [{"type": "function"}],
                on_delta=sink, **kwargs,
            )
        return result, sink, calls

    def test_deltas_arrive_in_order_and_are_joined(self):
        response = FakeStreamResponse(nd(
            {"message": {"role": "assistant", "content": "Ha"}, "done": False},
            {"message": {"role": "assistant", "content": "lo"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True,
             "prompt_eval_count": 10, "eval_count": 3},
        ))

        result, sink, calls = self.stream(response)

        self.assertEqual(sink.deltas, ["Ha", "lo"])
        self.assertEqual(result["message"]["content"], "Halo")
        self.assertEqual(result["message"]["tool_calls"], [])
        self.assertEqual(result["usage"], {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13})
        self.assertTrue(result["streamed"])
        self.assertTrue(calls[0]["json"]["stream"])
        self.assertTrue(calls[0]["stream"])
        self.assertTrue(response.closed)

    def test_tool_calls_are_collected_and_thinking_is_not_a_delta(self):
        call = {"function": {"name": "ping", "arguments": {"target": "1.1.1.1"}}}
        response = FakeStreamResponse(nd(
            {"message": {"role": "assistant", "content": "", "thinking": "mikir dulu"}, "done": False},
            {"message": {"role": "assistant", "content": "Cek ya", "tool_calls": [call]}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        ))

        result, sink, _ = self.stream(response)

        self.assertEqual(sink.deltas, ["Cek ya"])
        self.assertEqual(result["message"]["tool_calls"], [call])
        self.assertNotIn("mikir", json.dumps(result))

    def test_stream_without_done_is_a_connection_error(self):
        response = FakeStreamResponse(nd({"message": {"content": "sebagian"}, "done": False}))

        result, sink, _ = self.stream(response)

        self.assertEqual(result["error_type"], "connection")
        self.assertNotIn("message", result)
        self.assertEqual(sink.deltas, ["sebagian"])          # sudah terlanjur diteruskan

    def test_error_line_and_invalid_json(self):
        result, _, _ = self.stream(FakeStreamResponse(nd({"error": "model not found"})))
        self.assertIn("model not found", result["error"])
        self.assertEqual(result["error_type"], "other")

        result, _, _ = self.stream(FakeStreamResponse([b"{bukan json"]))
        self.assertEqual(result["error_type"], "other")

    def test_connection_dropped_midway_is_transient_connection_error(self):
        response = FakeStreamResponse(
            nd({"message": {"content": "sebagi"}, "done": False})
            + [requests.exceptions.ChunkedEncodingError("putus")]
        )

        result, _, _ = self.stream(response)

        self.assertEqual(result["error_type"], "connection")
        self.assertIn(result["error_type"], pc.TRANSIENT_ERROR_TYPES)

    def test_model_without_tools_support_is_retried_without_tools(self):
        first = FakeStreamResponse(status=400, body=b'{"error":"registry.ollama.ai/x does not support tools"}')
        second = FakeStreamResponse(nd({"message": {"content": "ok"}, "done": True}))

        result, sink, calls = self.stream((first, second))

        self.assertIn("tools", calls[0]["json"])
        self.assertNotIn("tools", calls[1]["json"])
        self.assertEqual(sink.deltas, ["ok"])
        self.assertTrue(result["streamed"])

    def test_http_errors_are_classified(self):
        result, _, _ = self.stream(FakeStreamResponse(status=429, body=b"slow down"))
        self.assertEqual(result["error_type"], "rate_limit")

        result, _, _ = self.stream(FakeStreamResponse(status=500, body=b"boom"))
        self.assertEqual(result["error_type"], "other")

    def test_stream_unsupported_is_reported_distinctly(self):
        result, _, _ = self.stream(FakeStreamResponse(status=400, body=b'{"error":"streaming is not supported"}'))
        self.assertEqual(result["error_type"], "stream_unsupported")

    def test_cancel_stops_reading_and_closes_connection(self):
        cancel = threading.Event()
        response = FakeStreamResponse(nd(
            {"message": {"content": "a"}, "done": False},
            {"message": {"content": "b"}, "done": False},
            {"message": {"content": "c"}, "done": False},
            {"message": {"content": ""}, "done": True},
        ))
        seen = []

        def on_delta(text):
            seen.append(text)
            cancel.set()

        patcher, _ = patch_post(response)
        with patcher:
            result = ProviderClient.chat_stream(
                "ollama", "m", [], None, on_delta=on_delta, cancel_event=cancel,
            )

        self.assertTrue(result["cancelled"])
        self.assertEqual(result["error_type"], "cancelled")
        self.assertEqual(seen, ["a"])                       # tidak ada delta baru sesudah Stop
        self.assertLessEqual(response.read_lines, 2)        # Stop dicek saat chunk berikutnya tiba; sisanya tidak dibaca
        self.assertTrue(response.closed)

    def test_broken_sink_does_not_break_the_call(self):
        response = FakeStreamResponse(nd({"message": {"content": "x"}, "done": True}))
        patcher, _ = patch_post(response)

        def bad(text):
            raise RuntimeError("sink rusak")

        with patcher, self.assertLogs("aira.rei.provider_client", level="ERROR"):
            result = ProviderClient.chat_stream("ollama", "m", [], None, on_delta=bad)

        self.assertEqual(result["message"]["content"], "x")

    def test_payload_of_non_streaming_call_is_unchanged(self):
        # _chat_ollama memakai helper payload yang sama: bentuknya harus tetap.
        payload = pc._ollama_payload("m", [{"role": "user", "content": "x"}], None, None, None, None, stream=False)
        self.assertEqual(payload, {"model": "m", "messages": [{"role": "user", "content": "x"}], "stream": False})

        payload = pc._ollama_payload("m", [], [{"t": 1}], 0.2, 50, False, stream=True)
        self.assertEqual(payload, {
            "model": "m", "messages": [], "stream": True, "tools": [{"t": 1}],
            "options": {"temperature": 0.2, "num_predict": 50}, "think": False,
        })


# ============================================================ 1b. PROVIDER: OPENAI-COMPATIBLE SSE

class TestOpenAIStream(unittest.TestCase):

    def setUp(self):
        ENV_KEY.start()
        self.addCleanup(ENV_KEY.stop)

    def stream(self, *responses, provider="openrouter", tools=None, **kwargs):
        patcher, calls = patch_post(*responses)
        sink = Collector()
        with patcher:
            result = ProviderClient.chat_stream(
                provider, "test/model", [{"role": "user", "content": "hi"}], tools,
                on_delta=sink, **kwargs,
            )
        return result, sink, calls

    def sse_response(self, *lines, **kwargs):
        return FakeStreamResponse(lines, headers={"Content-Type": "text/event-stream"}, **kwargs)

    def test_deltas_comments_and_usage(self):
        lines = [b": OPENROUTER PROCESSING", b""] + sse(
            oa(content="Ha"), oa(content="lo"), oa(finish="stop"),
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}},
        )

        result, sink, calls = self.stream(self.sse_response(*lines))

        self.assertEqual(sink.deltas, ["Ha", "lo"])
        self.assertEqual(result["message"]["content"], "Halo")
        self.assertEqual(result["usage"]["total_tokens"], 9)
        self.assertTrue(result["streamed"])
        self.assertTrue(calls[0]["json"]["stream"])
        self.assertEqual(calls[0]["json"]["stream_options"], {"include_usage": True})
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer test-key")

    def test_tool_call_fragments_are_merged_per_index(self):
        lines = sse(
            oa(tool_calls=[{"index": 0, "id": "call_a", "function": {"name": "ping", "arguments": ""}}]),
            oa(tool_calls=[{"index": 0, "function": {"arguments": '{"tar'}}]),
            oa(tool_calls=[{"index": 0, "function": {"arguments": 'get":"1.1.1.1"}'}}]),
            oa(tool_calls=[{"index": 1, "id": "call_b", "function": {"name": "get_routes", "arguments": '{"device_name":"R1"}'}}]),
            oa(finish="tool_calls"),
        )

        result, sink, _ = self.stream(self.sse_response(*lines))

        calls = result["message"]["tool_calls"]
        self.assertEqual([c["id"] for c in calls], ["call_a", "call_b"])
        self.assertEqual([c["function"]["name"] for c in calls], ["ping", "get_routes"])
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"target": "1.1.1.1"})
        self.assertEqual(json.loads(calls[1]["function"]["arguments"]), {"device_name": "R1"})
        self.assertEqual(sink.deltas, [])
        self.assertEqual(result["message"]["content"], "")          # bukan marker kosong: ada tool_calls

    def test_tool_calls_without_index_are_split_by_id(self):
        lines = sse(
            oa(tool_calls=[{"id": "x1", "function": {"name": "ping", "arguments": '{"target":"a"}'}}]),
            oa(tool_calls=[{"id": "x2", "function": {"name": "nslookup", "arguments": '{"target":"b"}'}}]),
            oa(finish="tool_calls"),
        )

        result, _, _ = self.stream(self.sse_response(*lines))

        self.assertEqual([c["function"]["name"] for c in result["message"]["tool_calls"]], ["ping", "nslookup"])

    def test_finish_reason_is_enough_without_done_marker(self):
        result, sink, _ = self.stream(self.sse_response(*sse(oa(content="ok"), oa(finish="stop"), done=False)))

        self.assertEqual(result["message"]["content"], "ok")
        self.assertTrue(result["streamed"])

    def test_truncated_stream_is_a_transient_error_not_a_partial_answer(self):
        result, sink, _ = self.stream(self.sse_response(*sse(oa(content="sebagian"), done=False)))

        self.assertEqual(result["error_type"], "connection")
        self.assertNotIn("message", result)

    def test_error_chunk_mid_stream(self):
        lines = sse({"error": {"code": 429, "message": "limit"}}, done=False)
        result, _, _ = self.stream(self.sse_response(*lines))
        self.assertEqual(result["error_type"], "rate_limit")

        lines = sse({"error": {"code": 500, "message": "x"}}, done=False)
        result, _, _ = self.stream(self.sse_response(*lines))
        self.assertEqual(result["error_type"], "other")

        result, _, _ = self.stream(self.sse_response(*sse(oa(finish="error"), done=False)))
        self.assertEqual(result["error_type"], "other")

    def test_invalid_json_chunk(self):
        result, _, _ = self.stream(self.sse_response(b"data: {rusak", b""))
        self.assertEqual(result["error_type"], "other")

    def test_provider_rejecting_stream_options_is_retried_without_them(self):
        first = FakeStreamResponse(status=400, body=b'{"error":"Unknown field: stream_options"}')
        second = self.sse_response(*sse(oa(content="ok"), oa(finish="stop")))

        result, sink, calls = self.stream(first, second)

        self.assertIn("stream_options", calls[0]["json"])
        self.assertNotIn("stream_options", calls[1]["json"])
        self.assertEqual(sink.deltas, ["ok"])
        self.assertIsNone(result["usage"])

    def test_provider_ignoring_stream_returns_honest_non_streamed_result(self):
        body = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "utuh"}}],
            "usage": {"total_tokens": 5},
        }).encode()
        response = FakeStreamResponse(headers={"Content-Type": "application/json"}, body=body)

        result, sink, _ = self.stream(response)

        self.assertFalse(result["streamed"])
        self.assertEqual(result["message"]["content"], "utuh")
        self.assertEqual(sink.deltas, [])                    # tidak ada delta palsu

    def test_stream_unsupported_error(self):
        result, _, _ = self.stream(FakeStreamResponse(status=400, body=b"stream is not supported for this model"))
        self.assertEqual(result["error_type"], "stream_unsupported")

    def test_missing_key_and_unknown_provider(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API": ""}):
            result, _, _ = self.stream()
        self.assertEqual(result["error_type"], "other")
        self.assertIn("OPENROUTER_API", result["error"])

        result = ProviderClient.chat_stream("tidak-ada", "m", [], on_delta=Collector())
        self.assertEqual(result["error_type"], "other")

    def test_cancel_closes_the_connection(self):
        cancel = threading.Event()
        response = self.sse_response(*sse(oa(content="a"), oa(content="b"), oa(finish="stop")))
        seen = []

        def on_delta(text):
            seen.append(text)
            cancel.set()

        patcher, _ = patch_post(response)
        with patcher:
            result = ProviderClient.chat_stream(
                "openrouter", "m", [], None, on_delta=on_delta, cancel_event=cancel,
            )

        self.assertTrue(result["cancelled"])
        self.assertEqual(seen, ["a"])
        self.assertTrue(response.closed)


# ============================================================ 2. STREAMING NYATA (server HTTP lokal)

class GatedServer:
    """
    Server chunked 127.0.0.1. Item `script` berupa bytes (dikirim sebagai satu
    HTTP chunk lalu di-flush) atau threading.Event ("gate": server MENUNGGU
    sampai test men-set-nya). Hasil tiap gate dicatat di `gates`.
    """

    def __init__(self, content_type, script):
        outer = self
        self.gates, self.body = [], None

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.body = json.loads(self.rfile.read(length))
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

                for item in script:
                    if isinstance(item, threading.Event):
                        outer.gates.append(item.wait(3))
                        continue
                    self.wfile.write(f"{len(item):x}\r\n".encode() + item + b"\r\n")
                    self.wfile.flush()

                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class TestRealIncrementalDelivery(unittest.TestCase):
    """Bukti bahwa chunk sampai ke client SELAGI respons masih berjalan."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {
            "OPENROUTER_API": "test-key", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
        })
        env.start()
        self.addCleanup(env.stop)

    def endpoints(self, port):
        patcher = mock.patch.dict(pc.DEFAULT_ENDPOINTS, {
            "ollama": f"http://127.0.0.1:{port}", "openrouter": f"http://127.0.0.1:{port}/v1",
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ollama_first_chunk_is_delivered_before_server_sends_the_rest(self):
        gate = threading.Event()
        script = [
            json.dumps({"message": {"content": "Halo "}, "done": False}).encode() + b"\n",
            gate,                                                    # server tahan sampai delta 1 diterima
            json.dumps({"message": {"content": "dunia"}, "done": False}).encode() + b"\n",
            json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 4, "eval_count": 2}).encode() + b"\n",
        ]
        deltas = []

        def on_delta(text):
            deltas.append(text)
            gate.set()

        with GatedServer("application/x-ndjson", script) as server:
            self.endpoints(server.port)
            result = ProviderClient.chat_stream("ollama", "m", [{"role": "user", "content": "hi"}], None, on_delta=on_delta)

        self.assertEqual(server.gates, [True], "client membuffer respons: delta pertama tidak tiba sebelum respons selesai")
        self.assertEqual(deltas, ["Halo ", "dunia"])
        self.assertEqual(result["message"]["content"], "Halo dunia")
        self.assertTrue(result["streamed"])
        self.assertTrue(server.body["stream"])

    def test_sse_first_chunk_is_delivered_before_server_sends_the_rest(self):
        gate = threading.Event()

        def frame(obj):
            return b"data: " + json.dumps(obj).encode() + b"\n\n"

        script = [
            b": OPENROUTER PROCESSING\n\n",
            frame(oa(content="Ha")),
            gate,
            frame(oa(content="lo")),
            frame(oa(finish="stop")),
            b"data: [DONE]\n\n",
        ]
        deltas = []

        def on_delta(text):
            deltas.append(text)
            gate.set()

        with GatedServer("text/event-stream", script) as server:
            self.endpoints(server.port)
            result = ProviderClient.chat_stream(
                "openrouter", "m", [{"role": "user", "content": "hi"}], None, on_delta=on_delta,
            )

        self.assertEqual(server.gates, [True], "client membuffer respons: delta pertama tidak tiba sebelum respons selesai")
        self.assertEqual(deltas, ["Ha", "lo"])
        self.assertEqual(result["message"]["content"], "Halo")
        self.assertTrue(result["streamed"])

    def test_call_model_streams_through_the_real_http_stack(self):
        gate = threading.Event()
        script = [
            b"data: " + json.dumps(oa(content="A")).encode() + b"\n\n",
            gate,
            b"data: " + json.dumps(oa(content="B")).encode() + b"\n\n",
            b"data: " + json.dumps(oa(finish="stop")).encode() + b"\n\n",
            b"data: [DONE]\n\n",
        ]
        events = []

        class Sink:
            def start(self, model):
                events.append(("start", model["id"]))

            def delta(self, text):
                events.append(("delta", text))
                gate.set()

        with tempfile.TemporaryDirectory() as tmp, GatedServer("text/event-stream", script) as server:
            self.endpoints(server.port)
            _, policy, router = make_env(tmp)
            glm = router.select(TaskClassification(primary_label="coding"))

            result = call_model([{"role": "user", "content": "hi"}], [], glm, policy=policy, router=router, stream=Sink())

        self.assertEqual(server.gates, [True])
        self.assertEqual(events, [("start", "glm"), ("delta", "A"), ("delta", "B")])
        self.assertEqual(result["message"]["content"], "AB")
        self.assertEqual(result["model"]["id"], "glm")
        self.assertTrue(result["streamed"])


# ============================================================ 3. call_model

class RecordingSink:
    def __init__(self):
        self.events = []

    def start(self, model):
        self.events.append(("start", model["id"], model["fallback_from"]))

    def delta(self, text):
        self.events.append(("delta", text))


def stream_ok(*chunks):
    def step(on_delta):
        for chunk in chunks:
            on_delta(chunk)
        return {
            "message": {"role": "assistant", "content": "".join(chunks), "tool_calls": []},
            "usage": None, "streamed": True,
        }
    return step


def stream_fail(*chunks, error="putus", error_type="connection", **extra):
    def step(on_delta):
        for chunk in chunks:
            on_delta(chunk)
        return {"error": error, "error_type": error_type, **extra}
    return step


def scripted_stream(*steps):
    calls = []

    def fake(**kwargs):
        step = steps[len(calls)]
        calls.append(kwargs)
        return step(kwargs["on_delta"])

    return fake, calls


class TestCallModelStreaming(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store, self.policy, self.router = make_env(self._tmp.name)
        self.glm = self.router.select(TaskClassification(primary_label="coding"))

        sleep = mock.patch.object(pc.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

        forbidden = mock.patch.object(ProviderClient, "chat", side_effect=AssertionError("jalur non-streaming dipakai"))
        self.chat = forbidden.start()
        self.addCleanup(forbidden.stop)

    def run_call(self, *steps, sink="default", cancel_event=None):
        fake, calls = scripted_stream(*steps)
        sink = RecordingSink() if sink == "default" else sink

        with mock.patch.object(ProviderClient, "chat_stream", fake):
            result = call_model(
                [{"role": "user", "content": "hi"}], [], self.glm,
                policy=self.policy, router=self.router, stream=sink, cancel_event=cancel_event,
            )

        return result, sink, calls

    def test_success_emits_start_then_deltas_and_reports_model(self):
        result, sink, calls = self.run_call(stream_ok("Ha", "lo"))

        self.assertEqual(sink.events, [("start", "glm", None), ("delta", "Ha"), ("delta", "lo")])
        self.assertEqual(result["message"]["content"], "Halo")
        self.assertEqual(result["model"]["id"], "glm")
        self.assertTrue(result["streamed"])
        self.assertEqual(calls[0]["model"], "test/glm-5.2")
        self.assertIsNone(calls[0]["cancel_event"])

    def test_without_sink_the_old_non_streaming_path_is_used_unchanged(self):
        self.chat.side_effect = None
        self.chat.return_value = {"message": {"role": "assistant", "content": "ok", "tool_calls": []}, "usage": None}

        with mock.patch.object(ProviderClient, "chat_stream", side_effect=AssertionError("stream dipakai")):
            result = call_model([{"role": "user", "content": "hi"}], [], self.glm, policy=self.policy, router=self.router)

        self.assertEqual(result["message"]["content"], "ok")
        self.assertNotIn("streamed", result)
        self.assertEqual(self.chat.call_args.kwargs["model"], "test/glm-5.2")

    def test_transient_error_retries_and_restarts_the_stream(self):
        self.assertTrue(self.store.set_policy(retry_provider=1)["success"])

        result, sink, calls = self.run_call(stream_fail("sebagi"), stream_ok("Halo"))

        self.assertEqual(len(calls), 2)
        self.assertEqual(sink.events, [
            ("start", "glm", None), ("delta", "sebagi"),
            ("start", "glm", None), ("delta", "Halo"),         # start baru = buffer client dikosongkan
        ])
        self.assertEqual(result["message"]["content"], "Halo")

    def test_provider_failure_falls_back_to_policy_model_and_streams_from_it(self):
        with EventCapture("model.failed", "model.fallback") as cap:
            result, sink, calls = self.run_call(
                stream_fail("par", error="boom", error_type="other"), stream_ok("dari fallback"),
            )

        self.assertEqual(sink.events, [
            ("start", "glm", None), ("delta", "par"),
            ("start", "gemma3", "glm"), ("delta", "dari fallback"),
        ])
        self.assertEqual(result["model"]["id"], "gemma3")
        self.assertEqual([c["model"] for c in calls], ["test/glm-5.2", "test/gemma3"])
        self.assertEqual(len(cap.of("model.failed")), 1)
        self.assertEqual(cap.of("model.fallback")[0]["to"], "gemma3")

    def test_all_models_failing_returns_error_without_cancelled_flag(self):
        result, sink, _ = self.run_call(
            stream_fail(error="satu", error_type="other"), stream_fail(error="dua", error_type="other"),
        )

        self.assertEqual(result, {"error": "dua"})
        self.assertEqual([e[0] for e in sink.events], ["start", "start"])

    def test_stream_unsupported_falls_back_to_non_streaming_on_same_model(self):
        self.chat.side_effect = None
        self.chat.return_value = {"message": {"role": "assistant", "content": "utuh", "tool_calls": []}, "usage": None}

        result, sink, calls = self.run_call(
            stream_fail(error="no stream", error_type="stream_unsupported"),
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(self.chat.call_args.kwargs["model"], "test/glm-5.2")
        self.assertEqual(sink.events, [("start", "glm", None)])          # tanpa delta palsu
        self.assertEqual(result["message"]["content"], "utuh")
        self.assertFalse(result["streamed"])
        self.assertEqual(result["model"]["id"], "glm")

    def test_cancelled_returns_immediately_without_retry_fallback_or_failed_event(self):
        self.assertTrue(self.store.set_policy(retry_provider=3)["success"])
        cancel = threading.Event()

        with EventCapture("model.failed", "model.fallback") as cap:
            result, sink, calls = self.run_call(
                stream_fail(error="Dibatalkan", error_type="cancelled", cancelled=True),
                cancel_event=cancel,
            )

        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]["cancel_event"], cancel)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["error_type"], "cancelled")
        self.assertEqual(cap.events, [])

    def test_broken_sink_never_breaks_the_call(self):
        class Bad:
            def start(self, model):
                raise RuntimeError("start rusak")

            def delta(self, text):
                raise RuntimeError("delta rusak")

        with self.assertLogs("aira.rei.provider_client", level="ERROR"):
            result, _, _ = self.run_call(stream_ok("a", "b"), sink=Bad())

        self.assertEqual(result["message"]["content"], "ab")


# ============================================================ 4. PLANNER

try:
    import agents.rei.planner as planner_module
    from agents.rei.planner import Planner
    PLANNER_ERROR = None
except ImportError as exc:                       # dependency runtime belum terpasang
    planner_module, Planner, PLANNER_ERROR = None, None, exc


class FakeTracker:
    last_usage = None

    def add(self, usage):
        self.last_usage = usage

    def as_dict(self):
        return {}


class FakeMemory:
    def __init__(self, session_id="s-test"):
        self.session_id = session_id
        self.history = []
        self.token_tracker = FakeTracker()

    def add_user(self, content):
        self.history.append({"role": "user", "content": content})

    def add_message(self, message):
        self.history.append(message)

    def add_tool_result(self, content, tool_call_id=None):
        self.history.append({"role": "tool", "content": content, "tool_call_id": tool_call_id})

    def get_messages(self, system_prompt):
        return [{"role": "system", "content": system_prompt}] + self.history


CONTEXT = types.SimpleNamespace(system_prompt="SYS")
PING = {"id": "c1", "function": {"name": "ping", "arguments": {"target": "1.1.1.1"}}}


def say(*chunks, tool_calls=None):
    """Langkah call_model palsu yang bersikap seperti provider streaming."""
    def step(sink, messages):
        if sink is not None:
            sink.start(MODEL)
            for chunk in chunks:
                sink.delta(chunk)
        return {
            "message": {"role": "assistant", "content": "".join(chunks), "tool_calls": tool_calls or []},
            "usage": None, "streamed": sink is not None,
        }
    return step


def fail_with(error, *chunks, **extra):
    def step(sink, messages):
        if sink is not None:
            sink.start(MODEL)
            for chunk in chunks:
                sink.delta(chunk)
        return {"error": error, **extra}
    return step


def scripted_call_model(*steps):
    calls = []

    def fake(*args, **kwargs):
        step = steps[len(calls)]
        calls.append({"args": args, "kwargs": kwargs})
        return step(kwargs.get("stream"), args[0])

    return fake, calls


class BusRecorder:
    """Subscriber wildcard di Event Bus GLOBAL, difilter per session_id."""

    def __init__(self, bus=event_bus, session_id=None):
        self.bus, self.session_id, self.events, self._token = bus, session_id, [], None

    def __enter__(self):
        from core.events import WILDCARD
        self._token = self.bus.subscribe(WILDCARD, self._on)
        return self

    def __exit__(self, *exc):
        from core.events import WILDCARD
        self.bus.unsubscribe(WILDCARD, self._token)

    def _on(self, event):
        if self.session_id is None or event.metadata.get("session_id") == self.session_id:
            self.events.append(event)

    def names(self, *prefixes):
        return [e.event for e in self.events if not prefixes or e.event.startswith(prefixes)]

    def of(self, name):
        return [e for e in self.events if e.event == name]


@unittest.skipIf(Planner is None, f"Planner tidak bisa diimpor: {PLANNER_ERROR}")
class TestPlannerStreaming(unittest.TestCase):

    def setUp(self):
        self.saved = []
        patch_extract = mock.patch.object(
            planner_module, "extract_and_save_facts_async", lambda *a, **k: self.saved.append(a),
        )
        patch_extract.start()
        self.addCleanup(patch_extract.stop)

    def run_planner(self, *steps, stream=True, cancel_event=None, executor=None, session="s1", run="r1", memory=None):
        fake, calls = scripted_call_model(*steps)
        planner = Planner(tool_schemas=[], tool_category={"ping": "network"})
        executor = executor or (lambda name, args: {"success": True, "output": "ok"})

        with mock.patch.object(planner_module, "call_model", fake), \
                BusRecorder(session_id=session) as recorder, \
                event_scope(correlation_id=f"turn-{session}-{run}", session_id=session, run_id=run):
            result = planner.run(
                "halo", memory or FakeMemory(session), executor,
                cancel_event=cancel_event, selected_model=None, context=CONTEXT, stream=stream,
            )

        return result, recorder, calls

    def test_single_call_publishes_start_then_ordered_deltas(self):
        result, recorder, calls = self.run_planner(say("Halo ", "dunia"))

        self.assertEqual(result["answer"], "Halo dunia")
        self.assertTrue(result["streamed"])
        self.assertFalse(result["error"])
        self.assertEqual(recorder.names("stream."), ["stream.start", "stream.delta", "stream.delta"])

        start = recorder.of("stream.start")[0]
        self.assertEqual(start.data["call"], 1)
        self.assertEqual(start.data["attempt"], 1)
        self.assertEqual(start.data["model"]["display_name"], "GLM 5.2")

        deltas = recorder.of("stream.delta")
        self.assertEqual([d.data["seq"] for d in deltas], [1, 2])
        self.assertEqual("".join(d.data["text"] for d in deltas), result["answer"])
        self.assertTrue(all(d.metadata["run_id"] == "r1" for d in deltas))       # session/run/correlation ikut scope
        self.assertEqual(len({d.correlation_id for d in recorder.events}), 1)
        self.assertEqual(calls[0]["kwargs"]["stream"].call, 1)

    def test_tool_loop_streams_each_llm_call_and_answer_is_only_the_last(self):
        result, recorder, _ = self.run_planner(
            say("Saya cek dulu.", tool_calls=[PING]), say("Hasil: ", "OK"),
        )

        self.assertEqual(result["answer"], "Hasil: OK")                          # tanpa teks pengantar call 1
        self.assertEqual(
            recorder.names("stream.", "tool."),
            ["stream.start", "stream.delta", "tool.start", "tool.progress", "tool.finish",
             "stream.start", "stream.delta", "stream.delta"],
        )
        self.assertEqual([e.data["call"] for e in recorder.of("stream.start")], [1, 2])
        self.assertEqual([e.data["seq"] for e in recorder.of("stream.delta")], [1, 1, 2])
        self.assertTrue(result["streamed"])

    def test_retry_or_fallback_inside_one_call_bumps_attempt_and_resets_seq(self):
        def two_attempts(sink, messages):
            sink.start(MODEL)
            sink.delta("sebagian")
            sink.start({**MODEL, "id": "gemma3", "fallback_from": "glm"})
            sink.delta("lengkap")
            return {"message": {"role": "assistant", "content": "lengkap", "tool_calls": []}, "usage": None, "streamed": True}

        result, recorder, _ = self.run_planner(two_attempts)

        starts = recorder.of("stream.start")
        self.assertEqual([(s.data["call"], s.data["attempt"]) for s in starts], [(1, 1), (1, 2)])
        self.assertEqual(starts[1].data["model"]["fallback_from"], "glm")
        self.assertEqual(
            [(d.data["attempt"], d.data["seq"], d.data["text"]) for d in recorder.of("stream.delta")],
            [(1, 1, "sebagian"), (2, 1, "lengkap")],
        )
        self.assertEqual(result["answer"], "lengkap")

    def test_empty_response_retry_reuses_the_same_sink_with_a_new_attempt(self):
        empty = {"message": {"role": "assistant", "content": EMPTY_RESPONSE_MARKER, "tool_calls": []},
                 "usage": None, "streamed": True}

        def first(sink, messages):
            sink.start(MODEL)
            return empty

        result, recorder, calls = self.run_planner(first, say("baru"))

        self.assertIs(calls[0]["kwargs"]["stream"], calls[1]["kwargs"]["stream"])
        self.assertEqual([(s.data["call"], s.data["attempt"]) for s in recorder.of("stream.start")], [(1, 1), (1, 2)])
        self.assertEqual(result["answer"], "baru")

    def test_non_streaming_turn_is_exactly_the_old_behaviour(self):
        result, recorder, calls = self.run_planner(say("Halo"), stream=False)

        self.assertEqual(result["answer"], "Halo")
        self.assertFalse(result["streamed"])
        self.assertEqual(recorder.names("stream."), [])
        self.assertEqual(len(calls[0]["args"]), 3)                # (messages, tool_schemas, selected_model)
        self.assertEqual(calls[0]["kwargs"], {})                  # tanpa stream/cancel_event

    def test_default_run_is_non_streaming(self):
        fake, calls = scripted_call_model(say("Halo"))
        planner = Planner(tool_schemas=[])

        with mock.patch.object(planner_module, "call_model", fake):
            result = planner.run("halo", FakeMemory(), lambda n, a: {}, context=CONTEXT)

        self.assertEqual(calls[0]["kwargs"], {})
        self.assertFalse(result["streamed"])

    def test_provider_error_after_partial_text_reports_error_and_answer_replaces_buffer(self):
        result, recorder, _ = self.run_planner(fail_with("Semua model gagal", "sebagian"))

        self.assertTrue(result["error"])
        self.assertTrue(result["answer"].startswith("Terjadi error saat menghubungi model"))
        self.assertFalse(result["streamed"])
        self.assertEqual(recorder.names("stream.", "system."), ["stream.start", "stream.delta", "system.error"])
        self.assertIsNone(result["token_usage"])

    def test_cancelled_stream_returns_cancelled_without_error_event_or_memory_extraction(self):
        cancel = threading.Event()
        result, recorder, calls = self.run_planner(
            fail_with("Dibatalkan", "sebagian", error_type="cancelled", cancelled=True), cancel_event=cancel,
        )

        self.assertTrue(result["cancelled"])
        self.assertEqual(result["answer"], "")
        self.assertNotIn("system.error", recorder.names())
        self.assertEqual(self.saved, [])
        self.assertIs(calls[0]["kwargs"]["cancel_event"], cancel)

    def test_cancel_during_second_call_is_also_handled(self):
        result, recorder, _ = self.run_planner(
            say("cek", tool_calls=[PING]),
            fail_with("Dibatalkan", "sebagian", error_type="cancelled", cancelled=True),
        )

        self.assertTrue(result["cancelled"])
        self.assertNotIn("system.error", recorder.names())

    def test_session_id_is_still_injected_for_session_aware_tools_while_streaming(self):
        seen = []

        def executor(name, args):
            seen.append((name, args))
            return {"success": True}

        location = {"id": "c9", "function": {"name": "request_location_permission", "arguments": {"original_request": "aku dmn"}}}

        self.run_planner(say("x", tool_calls=[location]), say("selesai"), executor=executor, session="sess-42")

        self.assertEqual(seen[0][1]["session_id"], "sess-42")


# ============================================================ 5. URUTAN + ISOLASI SESI (Planner -> Event Bus -> WS bridge)

class FakeSender:
    def __init__(self):
        self.sent = []

    async def __call__(self, session_id, payload):
        self.sent.append((session_id, payload))

    def of(self, session_id):
        return [p for sid, p in self.sent if sid == session_id]


class TestBridgeProtocol(unittest.TestCase):

    def translate(self, name, data=None, **scope):
        bus = EventBus()
        bridge = WebSocketEventBridge(bus=bus, sender=FakeSender())
        with event_scope(**scope):
            event = bus.publish(name, data=data)
        return bridge.translate(event)

    def test_stream_events_map_to_underscore_ws_types(self):
        self.assertEqual(STREAM_WS_EVENT_MAP, {
            EventNames.STREAM_START: "stream_start", EventNames.STREAM_DELTA: "stream_delta",
        })

        session_id, payload = self.translate(
            EventNames.STREAM_DELTA, {"call": 1, "attempt": 1, "seq": 3, "text": "Halo"},
            session_id="s1", run_id="r1", correlation_id="c1",
        )

        self.assertEqual(session_id, "s1")
        self.assertEqual(payload["type"], "stream_delta")
        self.assertEqual(payload["data"], {
            "call": 1, "attempt": 1, "seq": 3, "text": "Halo", "session_id": "s1", "run_id": "r1",
        })
        self.assertEqual(payload["correlation_id"], "c1")

    def test_legacy_map_is_untouched(self):
        self.assertNotIn(EventNames.STREAM_START, DEFAULT_WS_EVENT_MAP)
        self.assertNotIn(EventNames.STREAM_DELTA, DEFAULT_WS_EVENT_MAP)

    def test_custom_event_map_can_exclude_streaming(self):
        bus = EventBus()
        bridge = WebSocketEventBridge(bus=bus, sender=FakeSender(), event_map=DEFAULT_WS_EVENT_MAP)
        with event_scope(session_id="s1", run_id="r1"):
            event = bus.publish(EventNames.STREAM_DELTA, data={"text": "x"})
        self.assertIsNone(bridge.translate(event))

    def test_rest_turn_without_run_id_never_streams_to_a_socket(self):
        self.assertIsNone(self.translate(EventNames.STREAM_DELTA, {"text": "x"}, session_id="s1"))

    def test_stream_events_are_standard_events(self):
        self.assertEqual(EventNames.STREAM_START, "stream.start")
        self.assertEqual(EventNames.STREAM_DELTA, "stream.delta")
        self.assertTrue({"stream.start", "stream.delta"} <= STANDARD_EVENTS)


@unittest.skipIf(Planner is None, f"Planner tidak bisa diimpor: {PLANNER_ERROR}")
class TestOrderingAndSessionIsolation(unittest.IsolatedAsyncioTestCase):

    CHUNKS = 120

    def fake_call_model(self, messages, tools, selected_model=None, **kwargs):
        sink = kwargs["stream"]
        tag = messages[-1]["content"]                       # "S1" / "S2"
        sink.start(MODEL)
        for i in range(self.CHUNKS):
            sink.delta(f"{tag}-{i};")
            if i % 7 == 0:
                time.sleep(0.001)                          # beri kesempatan thread lain menyela
        return {
            "message": {"role": "assistant", "content": f"{tag}-selesai", "tool_calls": []},
            "usage": None, "streamed": True,
        }

    def run_turn(self, session_id, run_id, tag):
        planner = Planner(tool_schemas=[])
        with event_scope(session_id=session_id, run_id=run_id):
            return planner.run(tag, FakeMemory(session_id), lambda n, a: {}, context=CONTEXT, stream=True)

    async def test_two_parallel_sessions_get_their_own_ordered_streams(self):
        sender = FakeSender()
        bridge = WebSocketEventBridge(bus=event_bus, sender=sender)
        bridge.start(asyncio.get_running_loop())

        try:
            with mock.patch.object(planner_module, "call_model", self.fake_call_model), \
                    mock.patch.object(planner_module, "extract_and_save_facts_async", lambda *a, **k: None):
                r1, r2 = await asyncio.gather(
                    asyncio.to_thread(self.run_turn, "s1", "r1", "S1"),
                    asyncio.to_thread(self.run_turn, "s2", "r2", "S2"),
                )

            await bridge.flush()

            # meniru ws.py: "response" (complete) dikirim SETELAH flush
            await sender("s1", {"type": "response", "data": {"answer": r1["answer"]}})
            await sender("s2", {"type": "response", "data": {"answer": r2["answer"]}})
        finally:
            await bridge.stop()

        for sid, tag in (("s1", "S1"), ("s2", "S2")):
            payloads = sender.of(sid)
            types_ = [p["type"] for p in payloads]

            self.assertEqual(types_[0], "thinking")
            self.assertEqual(types_[1], "stream_start")
            self.assertEqual(types_[2:-1], ["stream_delta"] * self.CHUNKS)
            self.assertEqual(types_[-1], "response")                       # complete paling akhir

            deltas = [p["data"] for p in payloads if p["type"] == "stream_delta"]
            self.assertEqual([d["seq"] for d in deltas], list(range(1, self.CHUNKS + 1)))
            self.assertEqual([d["text"] for d in deltas], [f"{tag}-{i};" for i in range(self.CHUNKS)])
            self.assertTrue(all(d["session_id"] == sid for d in deltas))
            self.assertEqual({d["run_id"] for d in deltas}, {"r1" if sid == "s1" else "r2"})

    async def test_stream_events_precede_tool_events_and_response(self):
        sender = FakeSender()
        bridge = WebSocketEventBridge(bus=event_bus, sender=sender)
        bridge.start(asyncio.get_running_loop())

        steps = [say("Cek dulu.", tool_calls=[PING]), say("Selesai.")]
        fake, _ = scripted_call_model(*steps)

        try:
            with mock.patch.object(planner_module, "call_model", fake), \
                    mock.patch.object(planner_module, "extract_and_save_facts_async", lambda *a, **k: None):
                result = await asyncio.to_thread(self.run_turn, "s1", "r1", "S1")

            await bridge.flush()
            await sender("s1", {"type": "response", "data": {"answer": result["answer"]}})
        finally:
            await bridge.stop()

        types_ = [p["type"] for p in sender.of("s1")]
        interesting = [t for t in types_ if t.startswith(("stream_", "tool_")) or t == "response"]

        self.assertEqual(interesting, [
            "stream_start", "stream_delta", "tool_start", "tool_progress", "tool_finish",
            "stream_start", "stream_delta", "response",
        ])


# ============================================================ 6. FLAG STREAM

class TestStreamFlag(unittest.TestCase):

    def setUp(self):
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("AIRA_STREAMING", None)

    def test_default_is_on(self):
        self.assertTrue(stream_enabled_for_turn({"message": "hi"}))
        self.assertTrue(stream_enabled_for_turn({"message": "hi", "stream": None}))

    def test_client_can_opt_out_or_in(self):
        self.assertFalse(stream_enabled_for_turn({"stream": False}))
        self.assertTrue(stream_enabled_for_turn({"stream": True}))

    def test_voice_turns_never_stream(self):
        self.assertFalse(stream_enabled_for_turn({"stream": True}, is_voice_turn=True))

    def test_server_kill_switch_overrides_the_client(self):
        for value in ("0", "false", "OFF", " no "):
            with mock.patch.dict(os.environ, {"AIRA_STREAMING": value}):
                self.assertFalse(stream_enabled_for_turn({"stream": True}), value)

        with mock.patch.dict(os.environ, {"AIRA_STREAMING": "1"}):
            self.assertTrue(stream_enabled_for_turn({}))

    def test_garbage_payload_is_safe(self):
        self.assertTrue(stream_enabled_for_turn(None))
        self.assertTrue(stream_enabled_for_turn("bukan-dict"))


# ============================================================ 7. BRAIN

try:
    import core.brain as brain_module
    BRAIN_ERROR = None
except ImportError as exc:
    brain_module, BRAIN_ERROR = None, exc


class FakeClassifier:
    def classify(self, prompt):
        return TaskClassification(primary_label="networking", confidence=0.9)


class FakeRouter:
    def select(self, classification):
        return None


def make_orchestrator(accepts_stream, result=None):
    calls = []
    payload = result or {"answer": "ok", "steps": [], "error": False, "duration": 0.0}

    if accepts_stream:
        class Orchestrator:
            def route(self, user_input, memory, cancel_event=None, selected_model=None, context=None, stream=False):
                calls.append({"stream": stream})
                return dict(payload)
    else:
        class Orchestrator:   # orchestrator/test double LAMA: tidak mengenal 'stream'
            def route(self, user_input, memory, cancel_event=None, selected_model=None, context=None):
                calls.append({})
                return dict(payload)

    Orchestrator.calls = calls
    return Orchestrator


@unittest.skipIf(brain_module is None, f"core.brain tidak bisa diimpor: {BRAIN_ERROR}")
class TestBrainStreamFlag(unittest.TestCase):

    def make_brain(self, orchestrator):
        memory = types.SimpleNamespace(session_id="sess-1", history=[])
        builder = types.SimpleNamespace(build=lambda *a, **k: None)

        with mock.patch.multiple(
            "core.brain", Orchestrator=orchestrator,
            get_task_classifier=lambda: FakeClassifier(), get_model_router=lambda: FakeRouter(),
        ):
            return self.brain_module.Brain(memory, context_builder=builder)

    brain_module = brain_module

    def test_old_orchestrator_signature_still_works_and_stream_is_not_forced(self):
        orchestrator = make_orchestrator(accepts_stream=False)
        brain = self.make_brain(orchestrator)

        response = brain.think("halo")

        self.assertEqual(response.answer, "ok")
        self.assertFalse(response.streamed)
        self.assertEqual(orchestrator.calls, [{}])

    def test_stream_false_is_not_passed_down(self):
        orchestrator = make_orchestrator(accepts_stream=True)
        brain = self.make_brain(orchestrator)

        brain.think("halo", cancel_event=threading.Event(), stream=False)

        self.assertEqual(orchestrator.calls, [{"stream": False}])       # default orchestrator, bukan diteruskan Brain

    def test_stream_true_is_forwarded_and_streamed_flag_comes_back(self):
        orchestrator = make_orchestrator(
            accepts_stream=True, result={"answer": "utuh", "steps": [], "streamed": True, "duration": 0.1},
        )
        brain = self.make_brain(orchestrator)

        response = brain.think("halo", stream=True)

        self.assertEqual(orchestrator.calls, [{"stream": True}])
        self.assertTrue(response.streamed)
        self.assertEqual(response.answer, "utuh")                       # BrainResponse tetap utuh

    def test_brain_response_stays_backward_compatible(self):
        legacy = self.brain_module.BrainResponse("a", [], None, None, False, 0.0)
        self.assertFalse(legacy.streamed)
        self.assertFalse(self.brain_module.BrainResponse(answer="x").streamed)

    def test_positional_think_call_used_by_ws_still_works(self):
        orchestrator = make_orchestrator(accepts_stream=True)
        brain = self.make_brain(orchestrator)

        brain.think("halo", threading.Event(), True)                     # brain.think(msg, cancel_event, use_stream)

        self.assertEqual(orchestrator.calls, [{"stream": True}])


# ============================================================ 8. RUNTIME STATE

try:
    from core.runtime_state import RuntimeStateEngine, SUBSCRIBED_EVENTS
    RUNTIME_ERROR = None
except ImportError as exc:
    RuntimeStateEngine, SUBSCRIBED_EVENTS, RUNTIME_ERROR = None, (), exc


@unittest.skipIf(RuntimeStateEngine is None, f"Runtime State tidak tersedia: {RUNTIME_ERROR}")
class TestRuntimeStateUnaffected(unittest.TestCase):

    def test_stream_events_are_not_subscribed_by_the_engine(self):
        self.assertFalse([name for name in SUBSCRIBED_EVENTS if name.startswith("stream.")])

    @unittest.skipIf(Planner is None, f"Planner tidak bisa diimpor: {PLANNER_ERROR}")
    def test_streaming_turn_goes_thinking_then_idle_and_nothing_else(self):
        bus = EventBus()
        engine = RuntimeStateEngine(bus)
        engine.start()
        changes = []
        bus.subscribe("runtime.state_changed", lambda e: changes.append(e.data["state"]))
        seen = []
        bus.subscribe("*", lambda e: seen.append(e.event))

        fake, _ = scripted_call_model(say("a", "b", "c"))
        planner = Planner(tool_schemas=[])

        with mock.patch.object(planner_module, "event_bus", bus), \
                mock.patch.object(planner_module, "call_model", fake), \
                mock.patch.object(planner_module, "extract_and_save_facts_async", lambda *a, **k: None), \
                event_scope(correlation_id="turn-1", session_id="s1", run_id="r1"):
            planner.run("halo", FakeMemory(), lambda n, a: {}, context=CONTEXT, stream=True)
            self.assertEqual(engine.state, "THINKING")
            bus.publish(EventNames.THINKING_FINISH)                       # ditutup Brain di kode asli

        self.assertEqual(changes, ["THINKING", "IDLE"])
        self.assertEqual(engine.state, "IDLE")
        self.assertEqual(engine.stats()["transitions"], 2)
        self.assertEqual(seen.count("stream.delta"), 3)                    # event stream benar-benar lewat bus


if __name__ == "__main__":
    unittest.main()
