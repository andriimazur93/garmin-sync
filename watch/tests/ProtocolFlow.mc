// Private integration entry point: production engine and adapters, test lifecycle log.
import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

(:test) class ProtocolFlowApp extends App {
    private var _timer;
    private var _flowDelegate;
    function initialize() { App.initialize(); }
    function onStart(state) {
        var run = WatchUi.loadResource(Rez.Strings.SmokeRunId);
        if (Application.Storage.getValue("flow:run") != null && Application.Storage.getValue("flow:run").equals(run)) {
            System.println("FLOW_RESTART_INVENTORY count=" + new LocalLibrary(null).enumerateInventory().size());
            return;
        }
        Application.Properties.setValue("ServerUrl", WatchUi.loadResource(Rez.Strings.SmokeBaseUrl));
        Application.Properties.setValue("DeviceToken", WatchUi.loadResource(Rez.Strings.SmokeToken));
        Application.Storage.setValue("flow:run", run);
        _timer = new Timer.Timer(); _timer.start(method(:begin), 500, false);
    }
    function begin() as Void { System.println("FLOW_BEGIN"); Communications.startSync(); }
    function getSyncDelegate() {
        if (_flowDelegate == null) { _flowDelegate = new ProtocolFlowDelegate(); }
        return _flowDelegate;
    }
}
(:test) class ProtocolFlowDelegate extends Communications.SyncDelegate {
    private var _engine;
    function initialize() { SyncDelegate.initialize(); }
    function isSyncNeeded() { return true; }
    function onStartSync() {
        if (_engine != null && _engine.isActive()) { return; }
        var api = new ProtocolFlowApi({"url" => Application.Properties.getValue("ServerUrl"),
                                 "token" => Application.Properties.getValue("DeviceToken")});
        _engine = new SyncEngine(api, new LocalLibrary(null), new NativeSyncStore(), new NativeSyncClock(), new ProtocolFlowLifecycle());
        _engine.start();
    }
    function onStopSync() { if (_engine != null) { _engine.cancel(); } }
}
(:test) class ProtocolFlowLifecycle extends NativeSyncLifecycle {
    function initialize() { NativeSyncLifecycle.initialize(); }
    function complete(error) {
        System.println(error == null ? "FLOW_COMPLETE_OK" : "FLOW_COMPLETE_ERROR " + error);
        NativeSyncLifecycle.complete(error);
    }
}

(:test) class ProtocolFlowApi extends ApiClient {
    function initialize(config) { ApiClient.initialize(config); }
    function request(verb, path, payload, callback) {
        System.println("FLOW_REQUEST " + verb + " " + path);
        ApiClient.request(verb, path, payload, new ProtocolFlowCallback(callback).method(:receive));
    }
    function download(path, sessionId, callback, progress) {
        System.println("FLOW_AUDIO_REQUEST");
        ApiClient.download(path, sessionId, new ProtocolFlowCallback(callback).method(:receive), progress);
    }
}
(:test) class ProtocolFlowCallback {
    private var _callback;
    function initialize(callback) { _callback = callback; }
    function receive(code, data) {
        System.println("FLOW_RESPONSE " + code);
        _callback.invoke(code, data);
    }
}
