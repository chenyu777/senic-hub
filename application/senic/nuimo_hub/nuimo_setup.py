import logging
import nuimo
import threading


logger = logging.getLogger(__name__)


class NuimoSetup(nuimo.ControllerManagerListener, nuimo.ControllerListener):  # pragma: no cover

    def __init__(self, adapter_name):
        self._manager = nuimo.ControllerManager(adapter_name)
        self._manager.listener = self
        self._is_running = False  # Prevents from considering D-Bus events if we aren't running
        self._discovery_timeout_timer = None
        self._controller = None

    def discover_and_connect_controller(self, timeout=None):
        logger.debug("Discover and connect Nuimo controller with timeout = %f", timeout)
        self._is_running = True
        # TODO: If there's a connected Nuimo, take it and don't run discovery
        if timeout:
            self._discovery_timeout_timer = threading.Timer(timeout, self.discovery_timed_out)
            self._discovery_timeout_timer.start()
        self._controller = None
        self._manager.start_discovery()
        # Start D-Bus event loop. This call is blocking until the loop gets stopped.
        # Will be stopped when a controller was connected (see below).
        self._manager.run()
        self._is_running = False
        logger.debug("Stopped")
        if self._discovery_timeout_timer:
            self._discovery_timeout_timer.cancel()
        if self._connect_timeout_timer:
            self._connect_timeout_timer.cancel()
        if self._controller and self._controller.is_connected():
            return self._controller.mac_address
        else:
            return None

    def _restart_discovery(self):
        if not self._is_running:
            return
        logger.debug("restarting discovery")
        self._manager.start_discovery()

    def discovery_timed_out(self):
        if not self._is_running:
            return
        logger.debug("Discovery timed out, stopping now")
        self._is_running = False
        if self._connect_timeout_timer:
            self._connect_timeout_timer.cancel()
        if self._controller:
            self._controller.disconnect()
        self._manager.stop_discovery()
        self._manager.stop()

    def controller_discovered(self, controller):
        if not self._is_running:
            return
        if self._controller is not None:
            logger.debug("%s discovered but ignored, already connecting to another one", controller.mac_address)
            return
        logger.debug("%s discovered, stopping discovery and trying to connect", controller.mac_address)
        self._connect_timeout_timer = threading.Timer(20, self.connect_timed_out)
        self._connect_timeout_timer.start()
        self._controller = controller
        self._controller.listener = self
        self._controller.connect()

    def connect_succeeded(self):
        if not self._is_running:
            return
        logger.debug("%s successfully connected, stopping now", self._controller.mac_address)
        if self._connect_timeout_timer:
            self._connect_timeout_timer.cancel()
        self._manager.stop_discovery()
        self._manager.stop()

    def connect_failed(self, error):
        if not self._is_running:
            return
        logger.debug("%s connection failed: %s", self._controller.mac_address, error)
        if self._connect_timeout_timer:
            self._connect_timeout_timer.cancel()
        self._controller.listener = None  # Ignore any further events
        self._controller.disconnect()
        self._controller = None
        self._restart_discovery()

    def connect_timed_out(self):
        if not self._is_running:
            return
        self.connect_failed(Exception("Timeout"))