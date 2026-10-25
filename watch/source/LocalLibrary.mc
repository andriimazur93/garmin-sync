import Toybox.Application;
import Toybox.Lang;
import Toybox.Media;

// Cache IDs remain native values locally; only the wire representation is a string.
class LocalLibrary {
    private var _cache;

    function initialize(cache) {
        _cache = cache == null ? new NativeMediaCache() : cache;
    }

    function recordDownloaded(trackId, contentRef, filename) {
        var content = _cache.getContent(contentRef);
        if (content == null) {
            throw new Lang.InvalidValueException("Downloaded content is missing from the media cache");
        }
        var metadata = content.getMetadata();
        metadata.title = filename;
        content.setMetadata(metadata);
        Application.Storage.setValue(cacheKey(contentRef), {"track_id" => trackId, "filename" => filename});
    }

    function enumerateInventory() as Array<Dictionary> {
        var result = [];
        var refs = _cache.getRefs() as Array<Media.ContentRef>;
        for (var i = 0; i < refs.size(); i += 1) {
            var ref = refs[i];
            if (_cache.getContent(ref) != null) {
                var record = Application.Storage.getValue(cacheKey(ref)) as Dictionary?;
                result.add({
                    "track_id" => record == null ? null : record["track_id"],
                    "cache_id" => ref.getId().toString(),
                    "filename" => record == null ? null : record["filename"]
                });
            }
        }
        return result;
    }

    function getRefs() as Array<Media.ContentRef> {
        return _cache.getRefs();
    }

    function getContent(ref) {
        return _cache.getContent(ref);
    }

    function removeTrack(trackId) as Boolean {
        var refs = getRefs();
        for (var i = 0; i < refs.size(); i += 1) {
            var record = Application.Storage.getValue(cacheKey(refs[i])) as Dictionary?;
            // No inferred removal of unrecognized cache references.
            if (record != null && record["track_id"].equals(trackId)) {
                _cache.deleteContent(refs[i]);
                Application.Storage.deleteValue(cacheKey(refs[i]));
                return true;
            }
        }
        return false;
    }

    function removeCache(trackId, cacheId) as Boolean {
        var refs = getRefs();
        for (var i = 0; i < refs.size(); i += 1) {
            if (!refs[i].getId().toString().equals(cacheId)) { continue; }
            var record = Application.Storage.getValue(cacheKey(refs[i])) as Dictionary?;
            if (record == null || !record["track_id"].equals(trackId)) { return false; }
            _cache.deleteContent(refs[i]);
            Application.Storage.deleteValue(cacheKey(refs[i]));
            return true;
        }
        return false;
    }

    private function cacheKey(ref) as String {
        return "cache:" + ref.getId().toString();
    }
}

class NativeMediaCache {
    function initialize() {}

    function getRefs() as Array<Media.ContentRef> {
        var result = [];
        var iterator = nativeIterator();
        if (iterator == null) { return result; }
        var ref = advance(iterator);
        while (ref != null) {
            result.add(ref);
            ref = advance(iterator);
        }
        return result;
    }

    // Garmin's annotations declare non-null values, while the reference
    // example handles a missing iterator and next() documents a null end.
    // Preserve those optional values at the native boundary explicitly.
    private function nativeIterator() as Media.ContentRefIterator? {
        return Media.getContentRefIter({:contentType => Media.CONTENT_TYPE_AUDIO, :shuffle => false});
    }

    private function advance(iterator as Media.ContentRefIterator) as Media.ContentRef? {
        return iterator.next();
    }

    function getContent(ref) {
        // A cache failure must abort reconciliation, never publish false absence.
        return nativeContent(ref);
    }

    function nativeContent(ref) as Media.Content? {
        return Media.getCachedContentObj(ref);
    }

    function deleteContent(ref) { Media.deleteCachedItem(ref); }
}
