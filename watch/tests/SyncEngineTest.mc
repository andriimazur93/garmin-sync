import Toybox.Lang;
import Toybox.Media;

(:test) class FakeSyncStore {
    var values as Dictionary = {};
    var counter = 0;
    function initialize() {}
    function get(key) { return values[key]; }
    function put(key, value) { values[key] = value; }
    function drop(key) { values.remove(key); }
    function newId() {
        counter += 1;
        return "00000000-0000-4000-8000-" + counter.format("%012x");
    }
}
(:test) class FakeSyncClock {
    var value = 1000;
    function initialize() {}
    function now() { return value; }
}
(:test) class FakeSyncLifecycle {
    var completions = 0;
    var error = null;
    var progressCount = 0;
    function initialize() {}
    function progress(value) { progressCount += 1; }
    function complete(message) { completions += 1; error = message; }
}
(:test) class FakeSyncApi {
    var path = "";
    var payload as Dictionary?;
    var callback;
    var requests = 0;
    var downloads = 0;
    var cancellations = 0;
    var progressCallback;
    function initialize() {}
    function request(verb, relativePath, body, handler) {
        path = relativePath; payload = body; callback = handler; requests += 1;
    }
    function download(relativePath, sessionId, handler, progress) {
        progressCallback = progress;
        downloads += 1; request("AUDIO", relativePath, null, handler);
    }
    function cancel() { cancellations += 1; }
    function reply(code, data) {
        var handler = callback;
        callback = null;
        handler.invoke(code, data);
    }
}
(:test) class FakeSyncLibrary {
    var entries as Array<Dictionary> = [];
    var removals = 0;
    var mappings = 0;
    var failRemoval = false;
    function initialize() {}
    function enumerateInventory() { return entries; }
    function recordDownloaded(track, ref, filename) {
        mappings += 1;
        entries.add({"track_id" => track, "cache_id" => ref.getId(), "filename" => filename});
    }
    function removeCache(track, cacheId) {
        if (failRemoval) { return false; }
        for (var i = 0; i < entries.size(); i += 1) {
            if (entries[i]["cache_id"].equals(cacheId) && entries[i]["track_id"] != null && entries[i]["track_id"].equals(track)) {
                entries.remove(entries[i]); removals += 1; return true;
            }
        }
        return false;
    }
}
(:test) class SyncHarness {
    var api; var store; var clock; var library; var life; var engine;
    function initialize() {
        api = new FakeSyncApi(); store = new FakeSyncStore(); clock = new FakeSyncClock();
        library = new FakeSyncLibrary(); life = new FakeSyncLifecycle();
        engine = new SyncEngine(api, library, store, clock, life);
    }
    function restart() {
        api = new FakeSyncApi(); life = new FakeSyncLifecycle();
        engine = new SyncEngine(api, library, store, clock, life);
    }
    function beforePlan() {
        engine.start();
        api.reply(200, {"server_id" => "11111111-1111-4111-8111-111111111111", "protocol_version" => 1});
        if (api.path.find("/finish") != null) { api.reply(200, {"accepted" => true}); }
        var opened = api.payload as Dictionary;
        api.reply(200, {"server_id" => opened["server_id"], "session_id" => opened["session_id"],
            "device_epoch" => opened["device_epoch"], "protocol_version" => 1,
            "desired_revision" => null, "remaining_seconds" => 3600});
        acknowledgeReport();
    }
    function acknowledgeReport() {
        while (api.path.find("/pages/") != null) { api.reply(200, {"accepted" => true}); }
        var request = api.payload as Dictionary;
        var path = api.path;
        var session = store.get("sync:session") as Dictionary;
        api.reply(200, {"phase" => request["phase"], "pages" => request["expected_pages"],
            "entries" => request["expected_entries"], "session_id" => session["session_id"],
            "generation_id" => path.substring(path.length() - 43, path.length() - 7)});
    }
    function plan(items, confirmed, total, cursor) {
        var session = store.get("sync:session") as Dictionary;
        return {"server_id" => session["server_id"], "session_id" => session["session_id"],
            "device_epoch" => session["device_epoch"], "protocol_version" => 1,
            "desired_revision" => 1, "remaining_seconds" => 3500, "association_confirmed" => confirmed,
            "items" => items, "offset" => 0, "total_operations" => total, "next_cursor" => cursor};
    }
    function finishOkay() {
        acknowledgeReport();
        api.reply(200, {"accepted" => true});
    }
}
(:test) module SyncFixtures {
function unitTrack() { return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"; }
function downloadOperation() {
    return {"operation_id" => "44444444-4444-4444-8444-444444444444", "action" => "download",
        "track_id" => unitTrack(), "filename" => "unit.mp3", "size_bytes" => 10,
        "media_path" => "/api/v1/media/" + unitTrack()};
}
function removeOperation() {
    return {"operation_id" => "55555555-5555-4555-8555-555555555555", "action" => "remove",
        "track_id" => unitTrack(), "cache_id" => "unit-cache"};
}
}
(:test) function test_lost_result_ack_does_not_redownload(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    h.api.reply(200, new Media.ContentRef("unit-cache", Media.CONTENT_TYPE_AUDIO));
    h.api.reply(-1, null); // Media mapping persisted, result response lost.
    if (h.api.downloads != 1 || h.library.mappings != 1 || h.life.completions != 1) { return false; }
    h.restart(); h.beforePlan();
    h.api.reply(200, h.plan([], false, 0, null)); h.finishOkay();
    return h.api.downloads == 0 && h.library.entries.size() == 1 && h.life.completions == 1 && h.life.error == null;
}
(:test) function test_incomplete_plan_cannot_remove(logger) {
    var h = new SyncHarness();
    h.library.entries = [{"track_id" => SyncFixtures.unitTrack(), "cache_id" => "unit-cache", "filename" => "unit.mp3"}];
    h.beforePlan(); h.api.reply(200, h.plan([SyncFixtures.removeOperation()], true, 2, "next-page"));
    if (h.library.removals != 0) { return false; }
    h.api.reply(-1, null);
    return h.library.removals == 0 && h.life.completions == 1 && h.life.error != null;
}
(:test) function test_late_callback_after_cancel_does_nothing(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    var late = h.api.callback;
    h.engine.cancel(); var count = h.api.requests;
    late.invoke(200, new Media.ContentRef("late-cache", Media.CONTENT_TYPE_AUDIO));
    h.engine.cancel();
    return h.api.requests == count && h.api.cancellations == 1 && h.library.mappings == 0 && h.life.completions == 1;
}
(:test) function test_expired_session_stops_before_removal(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.clock.value += 3601;
    h.api.reply(200, h.plan([SyncFixtures.removeOperation()], true, 1, null));
    return h.library.removals == 0 && h.life.error != null && h.life.completions == 1;
}
(:test) function test_new_server_requires_confirmation(logger) {
    var h = new SyncHarness();
    h.store.put("sync:server", "99999999-9999-4999-8999-999999999999");
    h.library.entries = [{"track_id" => SyncFixtures.unitTrack(), "cache_id" => "unit-cache", "filename" => "unit.mp3"}];
    h.beforePlan(); h.api.reply(200, h.plan([SyncFixtures.removeOperation()], false, 1, null));
    return h.library.removals == 0 && h.life.completions == 1 && h.life.error != null;
}
(:test) function test_unmapped_cache_is_retained(logger) {
    var h = new SyncHarness();
    h.library.entries = [{"track_id" => null, "cache_id" => "unit-cache", "filename" => null}];
    h.beforePlan(); h.api.reply(200, h.plan([SyncFixtures.removeOperation()], true, 1, null));
    return h.library.removals == 0 && h.library.entries.size() == 1 && h.life.error != null;
}
(:test) function test_confirmed_removal_reports_then_finishes(logger) {
    var h = new SyncHarness();
    h.library.entries = [{"track_id" => SyncFixtures.unitTrack(), "cache_id" => "unit-cache", "filename" => "unit.mp3"}];
    h.beforePlan(); h.api.reply(200, h.plan([SyncFixtures.removeOperation()], true, 1, null));
    h.api.reply(200, {"accepted" => true}); h.finishOkay();
    return h.library.removals == 1 && h.life.error == null && h.life.completions == 1;
}
(:test) function test_server_outage_completes_once(logger) {
    var h = new SyncHarness(); h.engine.start(); h.api.reply(-1, null); h.engine.cancel();
    return h.life.completions == 1 && h.life.error != null && h.library.removals == 0;
}
(:test) function test_repeat_present_plan_does_not_download(logger) {
    var h = new SyncHarness();
    h.library.entries = [{"track_id" => SyncFixtures.unitTrack(), "cache_id" => "unit-cache", "filename" => "unit.mp3"}];
    h.beforePlan(); h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    h.api.reply(200, {"accepted" => true}); h.finishOkay();
    return h.api.downloads == 0 && h.library.mappings == 0 && h.life.error == null;
}
(:test) function test_failed_download_reports_error_and_reconciles(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    h.api.reply(-1, null);
    if (h.api.payload == null || !(h.api.payload as Dictionary)["status"].equals("failed")) { return false; }
    h.api.reply(200, {"accepted" => true}); h.acknowledgeReport();
    if (!(h.api.payload as Dictionary)["outcome"].equals("failed")) { return false; }
    h.api.reply(200, {"accepted" => true});
    return h.life.completions == 1 && h.life.error != null && h.library.entries.size() == 0;
}
(:test) function test_plan_budget_and_native_storage_checkpoint(logger) {
    var store = new NativeSyncStore();
    var id = store.newId();
    if (!validUuid(id) || id.equals(store.newId())) { return false; }
    // Reserve and reload the full conservative plan allowance in this simulator.
    var block = "0123456789abcdef";
    while (block.length() < 16000) { block += "0123456789abcdef"; }
    try {
        store.put("unit:plan-budget", block);
        var reloaded = store.get("unit:plan-budget");
        store.drop("unit:plan-budget");
        logger.debug("Accepted and reloaded 16000-byte checkpoint; free heap=" + Toybox.System.getSystemStats().freeMemory);
        return reloaded != null && reloaded.equals(block) && wireSize({"entries" => []}) < 8192;
    } catch (error) { store.drop("unit:plan-budget"); return false; }
}

(:test) function test_old_progress_callback_is_ignored_after_restart(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    var lateProgress = h.api.progressCallback;
    h.engine.cancel(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    var count = h.life.progressCount;
    lateProgress.invoke(50, 100);
    h.engine.cancel();
    return h.life.progressCount == count;
}
(:test) function test_utf8_page_budget_counts_codepoints_and_json_separators(logger) {
    return wireSize("界") == 8 && wireSize("🎵") == 14 && wireSize({"entries" => []}) == 15;
}
(:test) function test_restart_cleans_orphan_plan_pages_but_keeps_cache_mapping(logger) {
    var h = new SyncHarness();
    h.store.put("sync:pageCount", 0);
    h.store.put("sync:page:3", [SyncFixtures.removeOperation()]);
    h.store.put("cache:keep", "durable-mapping");
    h.engine.start();
    return h.store.get("sync:page:3") == null && h.store.get("cache:keep").equals("durable-mapping");
}
(:test) function test_download_finishing_after_expiry_keeps_mapping_without_new_requests(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.downloadOperation()], false, 1, null));
    var count = h.api.requests;
    h.clock.value += 3601;
    h.api.reply(200, new Media.ContentRef("finished-before-expiry-report", Media.CONTENT_TYPE_AUDIO));
    return h.library.mappings == 1 && h.api.requests == count && h.life.completions == 1 && h.life.error != null;
}
(:test) function test_oversized_plan_explains_failure_without_mutation(logger) {
    var h = new SyncHarness(); h.beforePlan();
    h.api.reply(200, h.plan([], false, 81, null));
    return h.life.error != null && h.life.error.equals("Plan exceeds watch operation budget") && h.library.removals == 0 && h.api.downloads == 0;
}

(:test) module CapacityFixtures {
function fillSyncInventory(library) {
    library.entries.add({"track_id" => SyncFixtures.unitTrack(), "cache_id" => "unit-cache", "filename" => "unit.mp3"});
    for (var i = 1; i < 200; i += 1) {
        library.entries.add({"track_id" => null, "cache_id" => "unknown-" + i, "filename" => null});
    }
}
function newCapacityDownload() {
    var op = SyncFixtures.downloadOperation();
    op["track_id"] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    op["media_path"] = "/api/v1/media/" + op["track_id"];
    return op;
}
}
(:test) function test_full_inventory_rejects_download_but_next_sync_can_remove(logger) {
    var h = new SyncHarness(); CapacityFixtures.fillSyncInventory(h.library); h.beforePlan();
    h.api.reply(200, h.plan([CapacityFixtures.newCapacityDownload()], true, 1, null));
    if (h.api.downloads != 0 || h.api.payload == null || !h.api.payload["status"].equals("failed")) { return false; }
    h.api.reply(200, {"accepted" => true}); h.finishOkay();
    if (h.library.entries.size() != 200 || h.life.completions != 1 || h.life.error == null) { return false; }
    h.restart(); h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.removeOperation()], true, 1, null));
    h.api.reply(200, {"accepted" => true}); h.finishOkay();
    return h.library.entries.size() == 199 && h.library.removals == 1 && h.life.error == null;
}
(:test) function test_confirmed_removal_frees_capacity_before_download(logger) {
    var h = new SyncHarness(); CapacityFixtures.fillSyncInventory(h.library); h.beforePlan();
    h.api.reply(200, h.plan([CapacityFixtures.newCapacityDownload(), SyncFixtures.removeOperation()], true, 2, null));
    if (h.library.removals != 1 || h.api.downloads != 0) { return false; }
    h.api.reply(200, {"accepted" => true});
    if (h.api.downloads != 1) { return false; }
    h.api.reply(200, new Media.ContentRef("replacement-cache", Media.CONTENT_TYPE_AUDIO));
    h.api.reply(200, {"accepted" => true}); h.finishOkay();
    return h.library.entries.size() == 200 && h.life.error == null;
}
(:test) function test_failed_removal_does_not_allow_over_capacity_download(logger) {
    var h = new SyncHarness(); CapacityFixtures.fillSyncInventory(h.library); h.library.failRemoval = true; h.beforePlan();
    h.api.reply(200, h.plan([SyncFixtures.removeOperation(), CapacityFixtures.newCapacityDownload()], true, 2, null));
    h.api.reply(200, {"accepted" => true});
    if (h.api.downloads != 0 || h.api.payload == null || !h.api.payload["status"].equals("failed")) { return false; }
    h.api.reply(200, {"accepted" => true}); h.finishOkay();
    return h.library.entries.size() == 200 && h.life.completions == 1 && h.life.error != null;
}
