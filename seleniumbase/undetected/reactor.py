import time
import asyncio
import json
import logging
import threading

from selenium import webdriver

logger = logging.getLogger(__name__)


class Reactor(threading.Thread):
    def __init__(
            self, driver: webdriver.Chrome
    ):
        super().__init__()
        self.driver = driver
        self.loop = asyncio.new_event_loop()
        self.paused = False
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.daemon = True
        self.handlers = {}

    def add_event_handler(self, method_name, callback: callable):
        """

        Parameters
        ----------
        event_name: str
            example "Network.responseReceived"

        callback: callable
            callable which accepts 1 parameter: the message object dictionary

        Returns
        -------

        """
        with self.lock:
            self.handlers[method_name.lower()] = callback

    def terminate(self, timeout=10):
        self.event.set()
        start_time = time.time()
        while not self.paused:
            elapsed_time = time.time() - start_time
            if elapsed_time >= timeout:
                break
            time.sleep(0.1)
        self.loop.close()
        return None

    def run(self):
        try:
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.listen())
        except Exception as e:
            logger.warning("Reactor.run() => %s", e)

    async def _wait_service_started(self):
        while True:
            with self.lock:
                if (
                    getattr(self.driver, "service", None)
                    and getattr(self.driver.service, "process", None)
                    and self.driver.service.process.poll()
                ):
                    await asyncio.sleep(self.driver._delay or 0.25)
                else:
                    break

    async def listen(self):
        while not self.event.is_set():
            await self._wait_service_started()
            await asyncio.sleep(1)

            try:
                with self.lock:
                    log_entries = self.driver.get_log("performance")

                for entry in log_entries:
                    try:
                        obj_serialized: str = entry.get("message")
                        obj: dict = json.loads(obj_serialized)
                        message: dict = obj.get("message")
                        method: str = message.get("method")

                        if "*" in self.handlers:
                            await self.loop.run_in_executor(
                                None, self.handlers["*"], message
                            )
                        elif method.lower() in self.handlers:
                            await self.loop.run_in_executor(
                                None, self.handlers[method.lower()], message
                            )
                    except Exception as error:
                        raise error from None

            except Exception as error:
                logging.debug("exception ignored :", error)

        self.paused = True
