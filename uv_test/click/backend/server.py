import json
import queue
from pathlib import Path
from threading import Lock, Thread
from urllib import error, request

from flask import Flask, Response, send_from_directory
from werkzeug.serving import BaseWSGIServer, make_server

# 고정 포트: 첫 번째 인스턴스가 서버를 열고, 이후 인스턴스는 이 포트에 연결만 해서
# 모든 창이 하나의 서버를 공유한다 → SSE로 카운터 상태가 자동 동기화된다.
COUNTER_PORT = 49321

CounterPayload = dict[str, int]
CounterEventQueue = queue.Queue[CounterPayload]


class CounterApiServer:
    def __init__(self, frontend_dir: Path) -> None:
        self.frontend_dir = Path(frontend_dir).resolve()
        self.port = COUNTER_PORT
        self._count = 0
        self._lock = Lock()
        self._event_clients: list[CounterEventQueue] = []
        self._server: BaseWSGIServer | None = None
        self._thread: Thread | None = None
        self._owns_server = False

        self.app = Flask(__name__, static_folder=str(self.frontend_dir), static_url_path="")
        self.app.add_url_rule("/", "index", self._serve_index)
        self.app.add_url_rule("/api/counter", "counter", self._counter_payload)
        self.app.add_url_rule(
            "/api/counter/increase", "increase", self._increase_payload, methods=["POST"]
        )
        self.app.add_url_rule(
            "/api/counter/decrease", "decrease", self._decrease_payload, methods=["POST"]
        )
        self.app.add_url_rule("/api/counter/events", "events", self._stream_counter_events)

    def _serve_index(self):
        return send_from_directory(self.frontend_dir, "index.html")

    def _counter_payload(self) -> CounterPayload:
        with self._lock:
            return {"count": self._count}

    def _broadcast_counter(self, payload: CounterPayload) -> None:
        for client_queue in list(self._event_clients):
            client_queue.put(payload)

    def _increase_payload(self) -> CounterPayload:
        with self._lock:
            self._count += 1
            payload = {"count": self._count}
        self._broadcast_counter(payload)
        return payload

    def _decrease_payload(self) -> CounterPayload:
        with self._lock:
            self._count -= 1
            payload = {"count": self._count}
        self._broadcast_counter(payload)
        return payload

    def _stream_counter_events(self) -> Response:
        client_queue: CounterEventQueue = queue.Queue()
        with self._lock:
            self._event_clients.append(client_queue)
            client_queue.put({"count": self._count})

        def eventStream():
            try:
                while True:
                    payload = client_queue.get()
                    yield f"data: {json.dumps(payload)}\n\n"
            finally:
                with self._lock:
                    if client_queue in self._event_clients:
                        self._event_clients.remove(client_queue)

        return Response(eventStream(), mimetype="text/event-stream")

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _isServerReady(self) -> bool:
        try:
            with request.urlopen(f"{self.base_url}/api/counter", timeout=1) as resp:
                return resp.status == 200
        except (OSError, error.URLError):
            return False

    def start(self) -> None:
        # 이미 서버가 실행 중이면 이 인스턴스는 서버를 시작하지 않는다.
        if self._isServerReady():
            return

        try:
            self._server = make_server("127.0.0.1", self.port, self.app, threaded=True)
        except OSError as exc:
            # 포트 충돌 직후 다른 프로세스가 먼저 바인딩했을 경우
            if exc.errno in {10048, 98} and self._isServerReady():
                return
            raise

        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._owns_server = True

    def stop(self) -> None:
        if not self._owns_server or self._server is None or self._thread is None:
            return
        self._server.shutdown()
        self._thread.join(timeout=1)