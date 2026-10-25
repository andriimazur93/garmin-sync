import Toybox.Media;

class LibraryContentDelegate extends Media.ContentDelegate {
    private var _library;
    private var _selected;
    private var _iterator;
    function initialize(library, selected) {
        ContentDelegate.initialize();
        _library = library == null ? new LocalLibrary(null) : library;
        _selected = selected;
        _iterator = null;
    }
    function getContentIterator() {
        if (_iterator == null) { resetContentIterator(); }
        return _iterator;
    }
    function resetContentIterator() {
        _iterator = new LibraryContentIterator(_library);
        _iterator.selectCacheId(_selected);
        return _iterator;
    }
}
