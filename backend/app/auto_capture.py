"""Short-lived, process-local stability checks. This is not liveness/PAD."""
import hashlib
import hmac
import secrets
import threading
from time import monotonic


def check_frame(quality):
    width, height = quality.get("frame_width", 0), quality.get("frame_height", 0)
    box = quality.get("box")
    if not width or not height or not box or len(box) != 4:
        return False, "Chưa xác định được vị trí khuôn mặt. Nhìn về camera và giữ mặt trong khung."
    if abs(width/height-4/3) > .01:
        return False, "Tỷ lệ hình camera chưa đúng khung 4:3. Hãy tải lại trang camera."
    x, y, face_width, face_height = box
    if face_width / width > .44 or face_height / height > .76:
        return False, "Khuôn mặt đang quá gần. Lùi nhẹ để toàn bộ mặt nằm trong khung oval."
    if face_width / width < .20 or face_height / height < .32:
        return False, "Khuôn mặt còn nhỏ. Đến gần camera hơn để vừa khung oval."
    dx,dy=abs((x+face_width/2)/width-.5),abs((y+face_height/2)/height-.5)
    if dx > .09 or dy > .12 or dx+face_width/(2*width) > .225 or dy+face_height/(2*height) > .40:
        return False, "Khuôn mặt đang lệch khung. Điều chỉnh vị trí để mặt nằm giữa khung oval."
    return True, "Khuôn mặt đã ở trong khung."


class StabilityTracker:
    required_frames = 3
    minimum_seconds = .85

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.entries = {}
        self.lock = threading.Lock()

    @staticmethod
    def geometry(quality):
        x, y, width, height = quality["box"]
        return ((x+width/2)/quality["frame_width"], (y+height/2)/quality["frame_height"],
                width/quality["frame_width"], quality["yaw_ratio"], quality["pitch_ratio"])

    def discard(self, collection_id):
        with self.lock:
            self.entries.pop(collection_id, None)

    def observe(self, signature, quality, fingerprint):
        now = self.clock()
        geometry = self.geometry(quality)
        with self.lock:
            self.entries = {key: row for key, row in self.entries.items() if now-row["last"] < 5}
            previous = self.entries.get(signature[0])
            moved = previous and any(abs(a-b) > limit for a, b, limit in zip(geometry, previous["geometry"], (.035, .035, .035, .05, .06), strict=True))
            if not previous or previous["signature"] != signature or now-previous["last"] > 2 or moved:
                previous = {"signature": signature, "geometry": geometry, "first": now, "last": now,
                            "fingerprints": {fingerprint}, "count": 1}
                if len(self.entries) >= 256:
                    self.entries.pop(min(self.entries, key=lambda key: self.entries[key]["last"]))
                self.entries[signature[0]] = previous
            elif now-previous["last"] >= .2 and fingerprint not in previous["fingerprints"]:
                previous["count"] = min(previous["count"]+1, self.required_frames)
                if len(previous["fingerprints"]) < self.required_frames:
                    previous["fingerprints"].add(fingerprint)
                previous["last"] = now
            ready = previous["count"] >= self.required_frames and now-previous["first"] >= self.minimum_seconds
            token = None
            if ready:
                token = secrets.token_urlsafe(32)
                previous.update(token_hash=hashlib.sha256(token.encode()).hexdigest(), fingerprint=fingerprint, expires=now+3)
            return {"ready": ready, "stable_frames": min(previous["count"], self.required_frames),
                    "required_frames": self.required_frames, "capture_token": token}

    def consume(self, signature, fingerprint, token):
        if not token or len(token) > 100:
            return False
        with self.lock:
            row = self.entries.get(signature[0])
            if not row or row["signature"] != signature or row.get("fingerprint") != fingerprint or self.clock() > row.get("expires", 0):
                return False
            if not hmac.compare_digest(row.get("token_hash", ""), hashlib.sha256(token.encode()).hexdigest()):
                return False
            self.entries.pop(signature[0], None)
            return True


tracker = StabilityTracker()
