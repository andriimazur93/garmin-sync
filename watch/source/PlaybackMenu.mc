import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.Media;
import Toybox.WatchUi;

class PlaybackMenu extends WatchUi.Menu2 {
    function initialize() {
        Menu2.initialize({:title => "Local Music Sync"});
        addItem(new WatchUi.MenuItem("Sync", "Apply PC choices", "sync", {}));
        addItem(new WatchUi.MenuItem("Settings", null, "settings", {}));
        var library = new LocalLibrary(null);
        var inventory = library.enumerateInventory();
        if (inventory.size() == 0) {
            addItem(new WatchUi.MenuItem("No music downloaded", null, "empty", {}));
        } else {
            addItem(new WatchUi.MenuItem("Play all", null, "all", {}));
            for (var i = 0; i < inventory.size(); i += 1) {
                var record = inventory[i];
                var title = record["filename"] == null ? "Downloaded track" : record["filename"];
                addItem(new WatchUi.MenuItem(title, null, record["cache_id"], {}));
            }
        }
    }
}

class PlaybackMenuDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() { Menu2InputDelegate.initialize(); }
    function onSelect(item) {
        if (item.getId().equals("sync")) { Communications.startSync(); return; }
        if (item.getId().equals("settings")) {
            WatchUi.pushView(new ProviderSettingsMenu(), new ProviderSettingsDelegate(), WatchUi.SLIDE_UP);
            return;
        }
        if (!item.getId().equals("empty")) { Media.startPlayback(item.getId()); }
    }
}

class ProviderSettingsMenu extends WatchUi.Menu2 {
    private var _urlItem;
    private var _tokenItem;
    function initialize() {
        Menu2.initialize({:title => "Settings"});
        _urlItem = new WatchUi.MenuItem("HTTPS server URL", null, "ServerUrl", {});
        _tokenItem = new WatchUi.MenuItem("Device token", null, "DeviceToken", {});
        addItem(_urlItem); addItem(_tokenItem);
    }
    function onShow() {
        _urlItem.setSubLabel(Application.Properties.getValue("ServerUrl") as String);
        _tokenItem.setSubLabel(validDeviceToken(Application.Properties.getValue("DeviceToken")) ? "Configured" : "Not configured");
    }
}
class ProviderSettingsDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() { Menu2InputDelegate.initialize(); }
    function onSelect(item) {
        var key = item.getId() as String;
        var initial = key.equals("DeviceToken") ? "" : (Application.Properties.getValue(key) as String);
        WatchUi.pushView(new WatchUi.TextPicker(initial), new ProviderSettingText(key), WatchUi.SLIDE_UP);
    }
}
class ProviderSettingText extends WatchUi.TextPickerDelegate {
    private var _key as String;
    function initialize(key as String) { TextPickerDelegate.initialize(); _key = key; }
    function onTextEntered(text, changed) {
        var valid = _key.equals("ServerUrl") ? validServerUrl(text) : validDeviceToken(text);
        if (valid) { Application.Properties.setValue(_key, text); }
        // Invalid edits leave the working configuration in place.
        Application.Storage.setValue("sync:lastError", valid ? null : "Invalid setting; previous value retained");
        return true;
    }
    function onCancel() { return true; }
}
