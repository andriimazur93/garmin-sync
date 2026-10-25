import Toybox.Lang;
import Toybox.Media;

// Only one request is in flight. Every callback carries its request generation.
class SyncCallback {
    private var _engine;
    private var _generation;
    function initialize(engine, generation) { _engine = engine; _generation = generation; }
    function progress(transferred, total) { _engine.onProgress(_generation, transferred, total); }
    function receive(code, data) {
        _engine.onResponse(_generation, {"code" => code, "data" => data});
    }
}

class SyncEngine {
    private var _api; private var _library; private var _store; private var _clock; private var _life;
    private var _finished = true;
    private var _serial = 0;
    private var _state;
    private var _session;
    private var _server;
    private var _epoch;
    private var _deadline;
    private var _lastClock;
    private var _sentAt;
    private var _phase;
    private var _generation;
    private var _inventory as Array<Dictionary>?;
    private var _uploadOffset;
    private var _uploadPage;
    private var _pageEnd;
    private var _planPages = 0;
    private var _planBytes = 0;
    private var _planCount = 0;
    private var _total;
    private var _revision;
    private var _confirmed;
    private var _operationIds as Dictionary?;
    private var _completePlan = false;
    private var _pass;
    private var _opPage;
    private var _opIndex;
    private var _operation as Dictionary?;
    private var _failures = false;
    private var _failureReason;

    function initialize(api, library, store, clock, lifecycle) {
        _api = api; _library = library; _store = store; _clock = clock; _life = lifecycle;
    }
    function isActive() { return !_finished; }
    function start() {
        if (!_finished) { return; }
        _finished = false; _failureReason = null;
        _deadline = null; _lastClock = _clock.now(); _completePlan = false;
        _planPages = 0; _planBytes = 0; _planCount = 0; _failures = false; _operationIds = {};
        try {
            // Never resume old removals. A fresh session reconciles durable cache mappings.
            // Include a page written just before a crash interrupted pageCount.
            for (var i = 0; i < 4; i += 1) { _store.drop("sync:page:" + i); }
            _store.put("sync:pageCount", 0); _store.put("sync:planComplete", false);
            _epoch = _store.get("sync:epoch");
            if (_epoch == null) { _epoch = _store.newId(); _store.put("sync:epoch", _epoch); }
            send("info", "GET", "/api/v1/info", null);
        } catch (error) { finish("Cannot initialize sync"); }
    }
    function cancel() { if (!_finished) { finish("Cancelled"); } }
    function onResponse(generation, response as Dictionary) {
        if (_finished || generation != _serial) { return; }
        try {
            if (!_state.equals("download")) { checkTime(); }
            var code = response["code"];
            var data = response["data"];
            if (_state.equals("reclaim")) {
                if (code != 200 && code != 404 && code != 409 && code != 410) { invalid("Cannot close previous session"); }
                openSession(); return;
            }
            if (_state.equals("download")) {
                if (code == 200) { downloaded(data); } else { checkTime(); result(false); }
                return;
            }
            if (code != 200) { invalid("Server unavailable or request rejected"); }
            if (!(data instanceof Dictionary)) { invalid("Invalid server response"); }
            var body = data as Dictionary;
            if (_state.equals("info")) {
                if (body["protocol_version"] != 1 || !validUuid(body["server_id"])) { invalid("Unsupported server"); }
                _server = body["server_id"];
                var previous = _store.get("sync:session") as Dictionary?;
                _store.put("sync:server", _server);
                if (previous != null && previous["server_id"].equals(_server) && previous["device_epoch"].equals(_epoch)) {
                    send("reclaim", "POST", "/api/v1/sessions/" + previous["session_id"] + "/finish", {"outcome" => "cancelled"});
                } else { openSession(); }
            } else if (_state.equals("open")) {
                validateIdentity(body); updateLifetime(body);
                upload("before");
            } else if (_state.equals("upload")) {
                accepted(body); _uploadOffset = _pageEnd; _uploadPage += 1; sendInventoryPage();
            } else if (_state.equals("commit")) {
                if (body["phase"] == null || !body["phase"].equals(_phase) ||
                    body["session_id"] == null || !body["session_id"].equals(_session) ||
                    body["generation_id"] == null || !body["generation_id"].equals(_generation) ||
                    body["pages"] != _uploadPage || body["entries"] != _inventory.size()) { invalid("Inventory commit mismatch"); }
                _inventory = null;
                if (_phase.equals("before")) { send("plan", "GET", base() + "/plan", null); }
                else { send("finish", "POST", base() + "/finish", {"outcome" => _failures ? "failed" : "success"}); }
            } else if (_state.equals("plan")) {
                receivePlan(body);
            } else if (_state.equals("result")) {
                accepted(body); _store.drop("sync:result"); nextOperation();
            } else if (_state.equals("finish")) {
                accepted(body); _store.drop("sync:session"); finish(_failures ? "Some tracks failed" : null);
            } else { invalid("Unexpected response"); }
        } catch (error) { finish(_failureReason == null ? "Sync failed; retry manually" : _failureReason); }
    }
    private function openSession() {
        _session = _store.newId();
        var body = {"session_id" => _session, "device_epoch" => _epoch, "server_id" => _server, "protocol_version" => 1};
        _store.put("sync:session", body);
        send("open", "POST", "/api/v1/sessions", body);
    }
    private function base() { return "/api/v1/sessions/" + _session; }
    private function send(state, verb, path, payload) {
        if (_finished) { return; }
        checkTime(); _state = state; _sentAt = _clock.now(); _serial += 1;
        _api.request(verb, path, payload, new SyncCallback(self, _serial).method(:receive));
    }
    private function checkTime() {
        var now = _clock.now();
        if (now < _lastClock || (_deadline != null && now >= _deadline)) { invalid("Session expired"); }
        _lastClock = now;
    }
    private function validateIdentity(data as Dictionary) {
        if (data["protocol_version"] != 1 || data["session_id"] == null || !data["session_id"].equals(_session) ||
            data["server_id"] == null || !data["server_id"].equals(_server) ||
            data["device_epoch"] == null || !data["device_epoch"].equals(_epoch)) { invalid("Sync identity mismatch"); }
    }
    private function updateLifetime(data as Dictionary) {
        var seconds = data["remaining_seconds"];
        if (!(seconds instanceof Number) || seconds <= 0 || seconds > 3600) { invalid("Invalid session lifetime"); }
        // Request start makes this conservative even with a delayed response.
        var expires = _sentAt + seconds;
        if (_deadline == null || expires < _deadline) { _deadline = expires; }
        checkTime();
    }
    private function accepted(data as Dictionary) { if (data["accepted"] != true) { invalid("Missing acknowledgement"); } }
    private function upload(phase) {
        checkTime(); _phase = phase; _generation = _store.newId();
        _inventory = _library.enumerateInventory();
        if (_inventory.size() > 200) { invalid("Inventory exceeds watch sync budget"); }
        _uploadOffset = 0; _uploadPage = 0; sendInventoryPage();
    }
    private function sendInventoryPage() {
        var path = base() + "/inventory/" + _generation;
        if (_uploadOffset >= _inventory.size()) {
            send("commit", "POST", path + "/commit", {"phase" => _phase,
                "expected_pages" => _uploadPage, "expected_entries" => _inventory.size()});
            return;
        }
        var items = [];
        _pageEnd = _uploadOffset;
        while (_pageEnd < _inventory.size() && items.size() < 20) {
            items.add(_inventory[_pageEnd]);
            if (wireSize({"entries" => items}) > 7000) { items.remove(items[items.size() - 1]); break; }
            _pageEnd += 1;
        }
        if (items.size() == 0) { invalid("Inventory entry exceeds request budget"); }
        send("upload", "PUT", path + "/pages/" + _uploadPage, {"entries" => items});
    }
    private function receivePlan(data as Dictionary) {
        validateIdentity(data); updateLifetime(data);
        var items = data["items"] as Array<Dictionary>?;
        if (!(items instanceof Array) || items.size() > 20 || !(data["total_operations"] instanceof Number) ||
            data["offset"] != _planCount || !(data["desired_revision"] instanceof Number) ||
            !(data["association_confirmed"] instanceof Boolean)) { invalid("Invalid plan envelope"); }
        if (_planPages == 0) {
            _total = data["total_operations"]; _revision = data["desired_revision"]; _confirmed = data["association_confirmed"];
            if (_total < 0 || _total > 80) { invalid("Plan exceeds watch operation budget"); }
        } else if (data["total_operations"] != _total || data["desired_revision"] != _revision || data["association_confirmed"] != _confirmed) {
            invalid("Plan changed between pages");
        }
        var bytes = jsonBudget(data, false);
        if (bytes > 8192 || _planPages >= 4 || _planBytes + bytes > 16000) { invalid("Plan exceeds watch storage budget"); }
        for (var i = 0; i < items.size(); i += 1) {
            var op = items[i]; validateOperation(op);
            if (_operationIds.hasKey(op["operation_id"])) { invalid("Duplicate operation"); }
            _operationIds[op["operation_id"]] = true;
        }
        _store.put("sync:page:" + _planPages, items);
        _planPages += 1; _planBytes += bytes; _planCount += items.size();
        _store.put("sync:pageCount", _planPages);
        if (_planCount > _total) { invalid("Plan count mismatch"); }
        var cursor = data["next_cursor"];
        if (cursor != null) {
            if (!(cursor instanceof String) || cursor.length() > 100 || items.size() == 0 || _planCount >= _total) { invalid("Invalid next plan cursor"); }
            send("plan", "GET", base() + "/plan?cursor=" + cursor, null);
            return;
        }
        if (_planCount != _total) { invalid("Incomplete plan"); }
        _store.put("sync:planIdentity", {"session_id" => _session, "server_id" => _server,
            "device_epoch" => _epoch, "desired_revision" => _revision});
        _store.put("sync:planComplete", true); _completePlan = true;
        _pass = 0; _opPage = 0; _opIndex = 0; _operationIds = null;
        nextOperation();
    }
    private function validateOperation(op as Dictionary) {
        if (!(op instanceof Dictionary) || !validUuid(op["operation_id"]) || !validDigest(op["track_id"])) { invalid("Invalid operation identity"); }
        if (op["action"] != null && op["action"].equals("remove")) {
            if (!_confirmed || !(op["cache_id"] instanceof String) || op["cache_id"].length() == 0 || op["cache_id"].length() > 256) { invalid("Removal requires confirmed association"); }
            // Validate against actual current mappings, including unknown references.
            var entries = _library.enumerateInventory() as Array<Dictionary>;
            for (var i = 0; i < entries.size(); i += 1) {
                if (entries[i]["cache_id"].equals(op["cache_id"]) &&
                    (entries[i]["track_id"] == null || !entries[i]["track_id"].equals(op["track_id"]))) { invalid("Retain unknown cache reference"); }
            }
        } else if (op["action"] != null && op["action"].equals("download")) {
            if (!(op["filename"] instanceof String) || op["filename"].length() > 255 ||
                !(op["size_bytes"] instanceof Number) || op["size_bytes"] <= 0 ||
                op["media_path"] == null || !op["media_path"].equals("/api/v1/media/" + op["track_id"])) { invalid("Invalid download metadata"); }
        } else { invalid("Unknown operation action"); }
    }
    private function nextOperation() {
        checkTime();
        if (!_completePlan || _store.get("sync:planComplete") != true) { invalid("Complete plan required"); }
        while (_pass < 2) {
            while (_opPage < _planPages) {
                var items = _store.get("sync:page:" + _opPage) as Array<Dictionary>?;
                if (!(items instanceof Array)) { invalid("Stored plan page missing"); }
                while (_opIndex < items.size()) {
                    _operation = items[_opIndex]; _opIndex += 1;
                    if ((_pass == 0) != _operation["action"].equals("remove")) { continue; }
                    checkTime(); validateOperation(_operation);
                    var entries = _library.enumerateInventory() as Array<Dictionary>;
                    if (_pass == 0) {
                        var exists = false;
                        for (var i = 0; i < entries.size(); i += 1) { if (entries[i]["cache_id"].equals(_operation["cache_id"])) { exists = true; } }
                        if (exists && !_library.removeCache(_operation["track_id"], _operation["cache_id"])) { result(false); }
                        else { result(true); }
                    } else {
                        for (var j = 0; j < entries.size(); j += 1) {
                            if (entries[j]["track_id"] != null && entries[j]["track_id"].equals(_operation["track_id"])) { result(true); return; }
                        }
                        // Keep the next before/after report within its measured budget.
                        // Count actual cache entries after removals, including unknown
                        // references and removals that failed to free a slot.
                        if (entries.size() >= 200) { result(false); return; }
                        _state = "download"; _sentAt = _clock.now(); _serial += 1;
                        var callback = new SyncCallback(self, _serial);
                        _api.download(_operation["media_path"], _session, callback.method(:receive), callback.method(:progress));
                    }
                    return;
                }
                _opPage += 1; _opIndex = 0;
            }
            _pass += 1; _opPage = 0; _opIndex = 0;
        }
        upload("after");
    }
    private function downloaded(data) {
        if (!(data instanceof Media.ContentRef)) { result(false); return; }
        _library.recordDownloaded(_operation["track_id"], data, _operation["filename"]);
        result(true);
    }
    private function result(success) {
        if (!success) { _failures = true; }
        var body = {"status" => success ? "success" : "failed", "error" => success ? null : "Media operation failed"};
        _store.put("sync:result", {"session_id" => _session, "operation_id" => _operation["operation_id"], "result" => body});
        send("result", "PUT", base() + "/results/" + _operation["operation_id"], body);
    }
    function onProgress(generation, transferred, total) {
        if (_finished || generation != _serial || !_state.equals("download")) { return; }
        _life.progress(total != null && total > 0 ? (99 * transferred.toFloat() / total).toNumber() : 0);
    }
    private function finish(error) {
        if (_finished) { return; }
        _finished = true; _serial += 1;
        if (error != null) { try { _api.cancel(); } catch (ignored) {} }
        try { _store.put("sync:lastError", error); } catch (ignored) {}
        if (error == null) { _life.progress(100); }
        _life.complete(error);
    }
    private function invalid(message) { _failureReason = message; throw new Lang.InvalidValueException(message); }
}

function validDigest(value) {
    if (!(value instanceof String) || value.length() != 64) { return false; }
    for (var i = 0; i < 64; i += 1) { if ("0123456789abcdef".find(value.substring(i, i + 1)) == null) { return false; } }
    return true;
}
function validUuid(value) {
    if (!(value instanceof String) || value.length() != 36) { return false; }
    for (var i = 0; i < 36; i += 1) {
        var ch = value.substring(i, i + 1);
        if (i == 8 || i == 13 || i == 18 || i == 23) { if (!ch.equals("-")) { return false; } }
        else if ("0123456789abcdef".find(ch) == null) { return false; }
    }
    return true;
}
// Exact separators; optional Unicode escaping bound for outgoing SDK JSON.
function wireSize(value) { return jsonBudget(value, true); }
function jsonBudget(value, escapedUnicode) {
    if (value == null) { return 4; }
    if (value instanceof String) {
        var bytes = value.toUtf8Array(); var size = 2;
        for (var i = 0; i < bytes.size(); i += 1) {
            var b = bytes[i];
            if (b == 34 || b == 92 || b == 8 || b == 9 || b == 10 || b == 12 || b == 13) { size += 2; }
            else if (b < 32) { size += 6; }
            else if (b >= 128 && escapedUnicode) {
                var count = b < 224 ? 2 : (b < 240 ? 3 : 4);
                size += count == 4 ? 12 : 6;
                i += count - 1;
            } else { size += 1; }
        }
        return size;
    }
    if (value instanceof Array) {
        var total = 2;
        for (var j = 0; j < value.size(); j += 1) { total += jsonBudget(value[j], escapedUnicode) + (j > 0 ? 2 : 0); }
        return total;
    }
    if (value instanceof Dictionary) {
        var keys = value.keys(); var count = 2;
        for (var k = 0; k < keys.size(); k += 1) {
            count += jsonBudget(keys[k], escapedUnicode) + jsonBudget(value[keys[k]], escapedUnicode) + 2 + (k > 0 ? 2 : 0);
        }
        return count;
    }
    return value.toString().length();
}
