// Included only by the private smoke build, after its authenticated download.
import Toybox.Lang;
import Toybox.WatchUi;

(:test)
function smokeFixtureSurvivesRestartAndFeedsPlayer(logger) {
    var expected = WatchUi.loadResource(Rez.Strings.SmokeTrackId);
    var library = new LocalLibrary(null);
    var inventory = library.enumerateInventory();
    for (var i = 0; i < inventory.size(); i += 1) {
        if (inventory[i]["track_id"] != null && inventory[i]["track_id"].equals(expected)) {
            var delegate = new LibraryContentDelegate(library, inventory[i]["cache_id"]);
            var content = delegate.getContentIterator().get();
            if (content == null) { return false; }
            var matches = content.getContentRef().getId().toString().equals(inventory[i]["cache_id"]) &&
                inventory[i]["filename"] != null && content.getMetadata().title.equals(inventory[i]["filename"]);
            if (matches) { logger.debug("Persisted fixture reference and native-player metadata verified"); }
            return matches;
        }
    }
    logger.error("The authenticated fixture download is not in the real media cache");
    return false;
}
