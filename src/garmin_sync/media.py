"""MP3 response construction; stream only verified immutable bytes."""
import re
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from .catalog import resolve_track, CatalogError


def media_response(db, track_id: str, range_header: str | None, head: bool = False):
    try:
        stream = resolve_track(db, track_id)
    except CatalogError as exc:
        raise HTTPException(404, str(exc)) from exc
    stream.seek(0, 2)
    size = stream.tell()
    start, end = 0, size - 1
    status = 200
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        try:
            if not match or not any(match.groups()):
                raise ValueError()
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(int(right), end) if right else end
            else:
                if int(right) <= 0:
                    raise ValueError()
                start = max(0, size - int(right))
            if start > end or start >= size:
                raise ValueError()
        except ValueError:
            stream.close()
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        status = 206
    headers["Content-Length"] = str(max(0, end - start + 1))
    if head:
        stream.close()
        return Response(status_code=status, headers=headers, media_type="audio/mpeg")

    def chunks():
        try:
            stream.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(chunks(), status_code=status, headers=headers, media_type="audio/mpeg")
