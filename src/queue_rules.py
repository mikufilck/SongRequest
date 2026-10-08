"""Song queue rules and persistence, independent of transport and account identity."""
import re
import time
import uuid
from datetime import datetime


class QueueRejected(ValueError):
    """A request cannot enter the queue under the current rules."""


def song_key(text):
    """Ignore edition brackets, spacing and separators when comparing titles."""
    stripped = re.sub(r"[（(\[【][^)）\]】]*[)）\]】]", "", str(text or ""))
    return re.sub(r"[\s·・\-_—、,，]", "", stripped).lower()


def waiting_entries(items):
    return [item for item in items if item.get("status") in ("waiting", "playing")]


def check_queue_rules(config, waiting, song, kind="song_request"):
    if kind == "singalong" and not config.get("accept_singalong", True):
        raise QueueRejected("主播当前没有开放点唱")
    if config.get("block_duplicate_song", True):
        key = song_key(song)
        if any(song_key(item.get("song")) == key for item in waiting):
            raise QueueRejected(f"《{song}》已经在队列里了")
    if len(waiting) >= int(config.get("queue_limit", 500) or 500):
        raise QueueRejected("队列已满，等播完几首再点")


def check_requester_limit(config, waiting, requester):
    limit = int(config.get("per_viewer_limit", 0) or 0)
    if limit > 0 and requester != "匿名":
        used = sum(1 for item in waiting if item.get("requester") == requester)
        if used >= limit:
            raise QueueRejected(f"你已点过 {limit} 首，等播完再点")


def make_queue_item(request, song, requester, kind="song_request"):
    try:
        fee = max(0, int(request.get("fee", 0)))
    except (TypeError, ValueError):
        fee = 0
    return {
        "id": uuid.uuid4().hex[:12],
        "song": song,
        "artist": str(request.get("artist", ""))[:200],
        "requester": requester,
        "type": kind,
        "status": "waiting",
        "time": datetime.now().strftime("%H:%M:%S"),
        "platform": str(request.get("platform", ""))[:40],
        "fee": fee,
    }


def enqueue_song(items, item, save, cooldowns, *, cooldown=0, requester_key=None, now=None):
    """Persist before accepting; restore both queue and cooldown if saving fails.

    `save` is a caller-supplied persistence function. Requests are serialized by
    the caller, so UI, network and identity handling stay outside this module.
    """
    key = requester_key if requester_key is not None else item["requester"]
    previous = cooldowns.get(key)
    if cooldown > 0:
        timestamp = time.time() if now is None else now
        if timestamp - cooldowns.get(key, 0) < cooldown:
            raise QueueRejected("点歌太频繁了，稍等一下")
        cooldowns[key] = timestamp
    items.append(item)
    try:
        save(items)
    except (OSError, ValueError, TypeError):
        items.remove(item)
        if cooldown > 0:
            if previous is None:
                cooldowns.pop(key, None)
            else:
                cooldowns[key] = previous
        raise
    return item
