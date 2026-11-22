"""A stand-in for the ML LiveManager (multi-session) so API tests do not need cameras or models."""
import queue
import types


class StubCameraError(RuntimeError):
    pass


class StubSessionLimitError(RuntimeError):
    pass


class StubCameraInUseError(RuntimeError):
    pass


class StubAlreadyMonitoredError(RuntimeError):
    pass


class StubManager:
    def __init__(self, registry=None, max_sessions=3):
        self.registry = registry
        self.max_sessions = max_sessions
        self.sessions = {}
        self.starts = []          # (room_id, source, patient_id)
        self.stops = []           # patient ids stopped (None = stop-all)
        self.fail = None
        self.last_patient_id = None
        self._order = []
        self.subscribers = []

    # ── starting / finding ──
    def start(self, room_id, source, patient_id=None, **kw):
        self.last_patient_id = patient_id
        if self.fail:
            raise self.fail
        key = patient_id or f"room:{room_id}"
        if key in self.sessions and self.sessions[key].running:
            raise StubAlreadyMonitoredError("This patient is already being monitored.")
        if len(self.running_sessions()) >= self.max_sessions:
            raise StubSessionLimitError(f"At most {self.max_sessions} cameras can be monitored at once.")
        parsed = int(source) if str(source).isdigit() else source
        if isinstance(parsed, int) and any(s.source == parsed for s in self.running_sessions()):
            raise StubCameraInUseError("That camera is already used by another monitored patient.")
        self.starts.append((room_id, source, patient_id))
        sess = types.SimpleNamespace(running=True, patient_id=patient_id, source=parsed, room_id=room_id)
        sess.status = lambda s=sess: {"state": "live" if s.running else "stopped", "patient_id": s.patient_id,
                                       "source": str(s.source), "job_id": f"job-{id(s)}"}
        sess.next_jpeg = lambda last, timeout=1.0, s=sess: _one_frame(s, last)
        self.sessions[key] = sess
        self._order.append(key)
        return sess

    def get(self, patient_id):
        s = self.sessions.get(patient_id)
        return s if s is not None and s.running else None

    def running_sessions(self):
        return [s for s in self.sessions.values() if s.running]

    @property
    def session(self):
        running = [self.sessions[k] for k in self._order if self.sessions[k].running]
        return running[-1] if running else (self.sessions[self._order[-1]] if self._order else None)

    # ── stopping ──
    def stop(self, patient_id=None):
        targets = [self.sessions[patient_id]] if patient_id in self.sessions else ([] if patient_id else self.running_sessions())
        targets = [s for s in targets if s.running]
        for s in targets:
            s.running = False
            if isinstance(s.source, str) and s.source.startswith("phone:") and self.registry is not None:
                self.registry.remove(s.source[len("phone:"):])
        self.stops.append(patient_id)
        return bool(targets)

    # ── status / events ──
    def status(self):
        running = self.running_sessions()
        if not running:
            return {"state": "idle", "sessions": []}
        items = [s.status() for s in running]
        return {**items[-1], "sessions": items}

    def subscribe(self):
        q = queue.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        if q in self.subscribers:
            self.subscribers.remove(q)


def _one_frame(sess, last):
    sess.running = False                      # one frame, then end the stream
    return b"\xff\xd8stubjpeg", last + 1


def module_for(manager):
    """What live_routes / patient_routes expect from the ML module."""
    return types.SimpleNamespace(
        get_manager=lambda: manager,
        CameraError=StubCameraError,
        SessionLimitError=StubSessionLimitError,
        CameraInUseError=StubCameraInUseError,
        AlreadyMonitoredError=StubAlreadyMonitoredError,
        grab_snapshot=lambda i: b"\xff\xd8snap" + str(i).encode(),
    )
