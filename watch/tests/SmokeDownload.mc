// Every class in this file is excluded from ordinary release builds.
import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.Media;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

(:test)
class SmokeApp extends App {
    private var _timer;
    function initialize() { App.initialize(); }
    function onStart(state) as Void {
        var runId = WatchUi.loadResource(Rez.Strings.SmokeRunId);
        var previousRun = Application.Storage.getValue("smoke:run");
        if (previousRun == null || !previousRun.equals(runId)) {
            Application.Storage.setValue("smoke:run", runId);
            Application.Storage.setValue("smoke:result", "requested");
            _timer = new Timer.Timer();
            _timer.start(method(:beginSync), 500, false);
        } else {
            var inventory = new LocalLibrary(null).enumerateInventory();
            System.println("SMOKE_RESTART_INVENTORY count=" + inventory.size());
        }
    }
    function beginSync() as Void {
        System.println("SMOKE_BEGIN_SYNC");
        Communications.startSync();
    }
    function getSyncDelegate() {
        return new SmokeSyncDelegate({
            "url" => WatchUi.loadResource(Rez.Strings.SmokeUrl),
            "token" => WatchUi.loadResource(Rez.Strings.SmokeToken),
            "track_id" => WatchUi.loadResource(Rez.Strings.SmokeTrackId),
            "session_id" => WatchUi.loadResource(Rez.Strings.SmokeSessionId)
        }, new LocalLibrary(null), new SmokeTransport(), new SmokeLifecycle());
    }
    function getContentDelegate(args) {
        System.println("SMOKE_NATIVE_PLAYER_HANDOFF");
        return App.getContentDelegate(args);
    }
}

(:test)
class SmokeSyncDelegate extends Communications.SyncDelegate {
    private var _config as Dictionary;
    private var _library;
    private var _transport;
    private var _lifecycle;
    private var _finished as Boolean;
    function initialize(config, library, transport, lifecycle) {
        SyncDelegate.initialize();
        _config = config;
        _library = library;
        _transport = transport;
        _lifecycle = lifecycle;
        _finished = false;
    }
    function isSyncNeeded() { return true; }
    function onStartSync() {
        var inventory = _library.enumerateInventory() as Array<Dictionary>;
        for (var i = 0; i < inventory.size(); i += 1) {
            if (inventory[i]["track_id"] != null && inventory[i]["track_id"].equals(_config["track_id"])) {
                finish(null);
                return;
            }
        }
        _transport.download(_config, method(:onDownload), method(:onProgress));
    }
    function onProgress(bytesTransferred, fileSize) as Void {
        if (!_finished && fileSize != null && fileSize > 0) {
            _lifecycle.progress((99 * bytesTransferred.toFloat() / fileSize).toNumber());
        }
    }
    function onDownload(code, data) as Void {
        if (_finished) { return; }
        if (code != 200 || !(data instanceof Media.ContentRef)) {
            finish("Download failed: " + code);
            return;
        }
        try {
            _library.recordDownloaded(_config["track_id"], data, "440 Hz test tone");
            finish(null);
        } catch (error) {
            finish("Downloaded media could not be registered");
        }
    }
    function onStopSync() {
        if (_finished) { return; }
        _finished = true;
        _transport.cancel();
        _lifecycle.complete("Cancelled");
    }
    private function finish(error) {
        if (_finished) { return; }
        _finished = true;
        if (error == null) { _lifecycle.progress(100); }
        _lifecycle.complete(error);
    }
}

(:test)
class SmokeTransport {
    function initialize() {}
    function download(config as Dictionary, callback, progress) {
        Communications.makeWebRequest(config["url"], null, {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :headers => {"Authorization" => "Bearer " + config["token"],
                         "X-Sync-Session" => config["session_id"]},
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_AUDIO,
            :mediaEncoding => Media.ENCODING_MP3,
            :fileDownloadProgressCallback => progress
        }, callback);
    }
    function cancel() { Communications.cancelAllRequests(); }
}

(:test)
class SmokeLifecycle {
    function initialize() {}
    function progress(value) { Communications.notifySyncProgress(value); }
    function complete(error) {
        Application.Storage.setValue("smoke:result", error == null ? "downloaded" : "failed");
        System.println(error == null ? "SMOKE_DOWNLOAD_OK" : "SMOKE_DOWNLOAD_FAILED " + error);
        Communications.notifySyncComplete(error);
    }
}
