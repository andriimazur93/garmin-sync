import Toybox.Application;
import Toybox.Communications;
import Toybox.Cryptography;
import Toybox.System;

class ProviderSyncDelegate extends Communications.SyncDelegate {
    private var _engine;
    function initialize() { SyncDelegate.initialize(); }
    // PC choices may have changed even when the local cache has not.
    function isSyncNeeded() { return true; }
    function onStartSync() {
        if (_engine != null && _engine.isActive()) { return; }
        try {
            var api = new ApiClient({"url" => Application.Properties.getValue("ServerUrl"),
                                     "token" => Application.Properties.getValue("DeviceToken")});
            _engine = new SyncEngine(api, new LocalLibrary(null), new NativeSyncStore(), new NativeSyncClock(), new NativeSyncLifecycle());
            _engine.start();
        } catch (error) { Communications.notifySyncComplete("Configure server URL and token in Settings"); }
    }
    function onStopSync() { if (_engine != null) { _engine.cancel(); } }
}
class NativeSyncStore {
    function initialize() {}
    function get(key) { return Application.Storage.getValue(key); }
    function put(key, value) { Application.Storage.setValue(key, value); }
    function drop(key) { Application.Storage.deleteValue(key); }
    function newId() {
        var bytes = Cryptography.randomBytes(16);
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        var result = "";
        for (var i = 0; i < 16; i += 1) {
            if (i == 4 || i == 6 || i == 8 || i == 10) { result += "-"; }
            result += bytes[i].format("%02x");
        }
        return result;
    }
}
class NativeSyncClock {
    function initialize() {}
    function now() { return System.getTimer().toFloat() / 1000; }
}
class NativeSyncLifecycle {
    function initialize() {}
    function progress(value) { Communications.notifySyncProgress(value); }
    function complete(error) { Communications.notifySyncComplete(error); }
}
