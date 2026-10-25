import Toybox.Application;

class App extends Application.AudioContentProviderApp {
    private var _syncDelegate;

    function initialize() {
        AudioContentProviderApp.initialize();
    }

    function getPlaybackConfigurationView() {
        return [new PlaybackMenu(), new PlaybackMenuDelegate()];
    }

    // Compatibility entry point required by AudioContentProviderApp.
    // The production sync action belongs in playback configuration.
    function getSyncConfigurationView() {
        return getPlaybackConfigurationView();
    }

    function getSyncDelegate() {
        if (_syncDelegate == null) { _syncDelegate = new ProviderSyncDelegate(); }
        return _syncDelegate;
    }

    function getContentDelegate(args) {
        return new LibraryContentDelegate(null, args);
    }
}
