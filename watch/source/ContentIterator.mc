import Toybox.Lang;
import Toybox.Media;

class LibraryContentIterator extends Media.ContentIterator {
    private var _library;
    private var _refs as Array<Media.ContentRef>;
    private var _position as Number;

    function initialize(library) {
        ContentIterator.initialize();
        _library = library;
        _refs = library.getRefs();
        _position = 0;
    }

    function selectCacheId(cacheId) {
        if (cacheId instanceof String) {
            for (var i = 0; i < _refs.size(); i += 1) {
                if (_refs[i].getId().toString().equals(cacheId)) { _position = i; }
            }
        }
    }

    function get() { return at(_position); }
    function peekNext() { return at(_position + 1); }
    function peekPrevious() { return at(_position - 1); }
    function next() {
        if (_position + 1 >= _refs.size()) { return null; }
        _position += 1;
        return get();
    }
    function previous() {
        if (_position <= 0) { return null; }
        _position -= 1;
        return get();
    }
    function canSkip() { return true; }
    function shuffling() { return false; }
    function getPlaybackProfile() {
        var profile = new Media.PlaybackProfile();
        profile.playbackControls = [Media.PLAYBACK_CONTROL_PLAYBACK, Media.PLAYBACK_CONTROL_PREVIOUS, Media.PLAYBACK_CONTROL_NEXT];
        profile.requirePlaybackNotification = false;
        return profile;
    }
    private function at(index) {
        if (index < 0 || index >= _refs.size()) { return null; }
        return _library.getContent(_refs[index]);
    }
}
