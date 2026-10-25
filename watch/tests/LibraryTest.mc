import Toybox.Lang;

(:test)
function emptyProviderHasSafeIterator(logger) {
    var cache = new TestMediaCache("unit-empty");
    cache.references = [];
    var delegate = new LibraryContentDelegate(new LocalLibrary(cache), null);
    var iterator = delegate.getContentIterator();
    if (iterator == null) {
        logger.error("Native playback requires an iterator even for an empty library");
        return false;
    }
    return iterator.get() == null && iterator.next() == null && iterator.previous() == null;
}

(:test)
class TestMediaCache {
    var references as Array<Toybox.Media.ContentRef>;
    function initialize(id) {
        references = [new Toybox.Media.ContentRef(id, Toybox.Media.CONTENT_TYPE_AUDIO)];
    }
    function getRefs() { return references; }
    function getContent(ref) {
        for (var i = 0; i < references.size(); i += 1) {
            var item = references[i];
            if (item.getId().equals(ref.getId())) {
                return new TestCachedContent(ref);
            }
        }
        return null;
    }
    function deleteContent(ref) { references = []; }
}

// Native Content.setMetadata writes to Garmin's real media cache. Keep that
// external operation in the cache double rather than using a fabricated ID.
(:test)
class TestCachedContent {
    private var _ref;
    private var _metadata;
    function initialize(ref) {
        _ref = ref;
        _metadata = new Toybox.Media.ContentMetadata();
    }
    function getContentRef() { return _ref; }
    function getMetadata() { return _metadata; }
    function setMetadata(metadata) { _metadata = metadata; }
}

(:test)
function test_mapping_survives_reload(logger) {
    var cache = new TestMediaCache("unit-persist");
    var library = new LocalLibrary(cache);
    library.recordDownloaded("unit-track-persist", cache.references[0], "test.mp3");
    var result = new LocalLibrary(cache).enumerateInventory();
    var okay = result.size() == 1 && result[0]["track_id"].equals("unit-track-persist") && result[0]["cache_id"].equals("unit-persist");
    library.removeTrack("unit-track-persist");
    return okay;
}

(:test)
function test_missing_cache_reference_is_not_reported_present(logger) {
    var cache = new TestMediaCache("unit-missing");
    var library = new LocalLibrary(cache);
    library.recordDownloaded("unit-track-missing", cache.references[0], "missing.mp3");
    var initiallyPresent = library.enumerateInventory().size() == 1;
    cache.references = [];
    var okay = initiallyPresent && new LocalLibrary(cache).enumerateInventory().size() == 0;
    library.removeTrack("unit-track-missing");
    return okay;
}

(:test)
function test_player_iterator_does_not_advance_when_peeking(logger) {
    var cache = new TestMediaCache("unit-first");
    cache.references.add(new Toybox.Media.ContentRef("unit-second", Toybox.Media.CONTENT_TYPE_AUDIO));
    var iterator = new LibraryContentIterator(new LocalLibrary(cache));
    return iterator.get().getContentRef().getId().equals("unit-first") &&
        iterator.peekNext().getContentRef().getId().equals("unit-second") &&
        iterator.get().getContentRef().getId().equals("unit-first") &&
        iterator.previous() == null &&
        iterator.next().getContentRef().getId().equals("unit-second") &&
        iterator.next() == null &&
        iterator.previous().getContentRef().getId().equals("unit-first");
}

(:test)
function test_native_cache_enumeration_handles_end_of_iterator(logger) {
    // The actual simulator cache is necessary: the cache double cannot expose
    // native argument or end-of-iterator errors.
    logger.debug("Native cache bytes before enumeration: " + Toybox.Media.getCacheStatistics().size);
    var entries = new LocalLibrary(null).enumerateInventory();
    for (var i = 0; i < entries.size(); i += 1) {
        if (!(entries[i]["cache_id"] instanceof String)) { return false; }
    }
    return true;
}

(:test)
function test_remove_cache_requires_exact_known_mapping(logger) {
    var cache = new TestMediaCache("unit-exact-remove");
    var library = new LocalLibrary(cache);
    library.recordDownloaded("unit-exact-track", cache.references[0], "exact.mp3");
    if (library.removeCache("different-track", "unit-exact-remove")) { return false; }
    if (library.removeCache("unit-exact-track", "wrong-cache")) { return false; }
    if (cache.references.size() != 1) { return false; }
    return library.removeCache("unit-exact-track", "unit-exact-remove") && cache.references.size() == 0;
}

(:test)
function test_native_song_notification_does_not_require_cached_content(logger) {
    var cache = new TestMediaCache("unit-song-event");
    var delegate = new LibraryContentDelegate(new LocalLibrary(cache), null);
    delegate.method(:onSong).invoke("unit-song-event", Toybox.Media.SONG_EVENT_STOP, 0);
    return delegate.getContentIterator().get() != null;
}

(:test) class FailingNativeMediaCache extends NativeMediaCache {
    function initialize() { NativeMediaCache.initialize(); }
    function nativeContent(ref) {
        throw new Lang.InvalidValueException("Cache unavailable");
    }
}
(:test) function test_native_cache_failure_is_not_absent_content(logger) {
    var cache = new FailingNativeMediaCache();
    try { cache.getContent(new Toybox.Media.ContentRef("unit-failure", Toybox.Media.CONTENT_TYPE_AUDIO)); }
    catch (error) { return true; }
    return false;
}
