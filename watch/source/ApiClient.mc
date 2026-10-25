import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.Media;

class ApiClient {
    private var _url as String;
    private var _token as String;
    function initialize(config as Dictionary) {
        if (!validServerUrl(config["url"]) || !validDeviceToken(config["token"])) {
            throw new Lang.InvalidValueException("Configure HTTPS server URL and device token");
        }
        _url = config["url"];
        if (_url.substring(_url.length() - 1, _url.length()).equals("/")) { _url = _url.substring(0, _url.length() - 1); }
        _token = config["token"];
    }
    function request(verb, path, payload, callback) {
        var methods = {"GET" => Communications.HTTP_REQUEST_METHOD_GET,
            "POST" => Communications.HTTP_REQUEST_METHOD_POST, "PUT" => Communications.HTTP_REQUEST_METHOD_PUT};
        if (!methods.hasKey(verb) || path.find("/api/v1/") != 0) { throw new Lang.InvalidValueException("Invalid API request"); }
        Communications.makeWebRequest(_url + path, payload, {
            :method => methods[verb],
            :headers => {"Authorization" => "Bearer " + _token, "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON},
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, callback);
    }
    function download(path, sessionId, callback, progress) {
        if (path.find("/api/v1/media/") != 0 || !validUuid(sessionId)) { throw new Lang.InvalidValueException("Invalid media request"); }
        Communications.makeWebRequest(_url + path, null, {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :headers => {"Authorization" => "Bearer " + _token, "X-Sync-Session" => sessionId},
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_AUDIO,
            :mediaEncoding => Media.ENCODING_MP3,
            :fileDownloadProgressCallback => progress
        }, callback);
    }
    function cancel() { Communications.cancelAllRequests(); }
}

function validServerUrl(value) {
    if (!(value instanceof String) || value.length() < 9 || value.length() > 256 || value.find("https://") != 0) { return false; }
    var host = value.substring(8, value.length());
    if (host.substring(host.length() - 1, host.length()).equals("/")) { host = host.substring(0, host.length() - 1); }
    if (host.length() == 0) { return false; }
    for (var i = 0; i < host.length(); i += 1) {
        if ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:".find(host.substring(i, i + 1)) == null) { return false; }
    }
    return true;
}
function validDeviceToken(value) {
    if (!(value instanceof String) || value.length() < 16 || value.length() > 256) { return false; }
    for (var i = 0; i < value.length(); i += 1) {
        if ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-".find(value.substring(i, i + 1)) == null) { return false; }
    }
    return true;
}
