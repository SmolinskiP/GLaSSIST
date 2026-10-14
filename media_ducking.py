"""Lower configured media players while the assistant listens and speaks (ESPHome mode).

WebSocket mode does this inside main.process_voice_command. In ESPHome mode Home
Assistant drives the pipeline, so the volumes are changed through a short-lived
WebSocket connection, which needs HA_HOST and HA_TOKEN.
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import utils

logger = utils.setup_logger()


class MediaPlayerDucker:
    def __init__(self):
        # One worker keeps duck/restore in order without blocking the caller.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='media-ducking')
        self._lock = threading.Lock()
        self._active = False
        self._saved = None

    @staticmethod
    def _entities():
        entities = [e.strip() for e in utils.get_env('HA_MEDIA_PLAYER_ENTITIES', '').split(',') if e.strip()]
        if entities and not utils.get_env('HA_TOKEN'):
            logger.warning('Media player volume management needs HA_TOKEN in ESPHome mode - skipping')
            return []
        return entities

    def duck(self):
        entities = self._entities()
        if not entities:
            return
        with self._lock:
            if self._active:
                return
            self._active = True
        target = utils.get_env('HA_MEDIA_PLAYER_TARGET_VOLUME', 0.3, float)
        self._executor.submit(self._run, self._duck(entities, target))

    def restore(self):
        with self._lock:
            if not self._active:
                return
            self._active = False
        self._executor.submit(self._run, self._restore())

    @staticmethod
    def _run(coro):
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.error(f'Media player volume management failed: {e}')

    async def _duck(self, entities, target):
        from client import HomeAssistantClient
        client = HomeAssistantClient()
        if not await client.connect():
            return
        try:
            saved = await client.get_multiple_volumes(entities)
            if saved:
                self._saved = saved
                results = await client.set_multiple_volumes({entity: target for entity in saved})
                logger.info(f'Lowered media player volumes: {results}')
        finally:
            await client.close()

    async def _restore(self):
        saved, self._saved = self._saved, None
        if not saved:
            return
        from client import HomeAssistantClient
        client = HomeAssistantClient()
        if not await client.connect():
            return
        try:
            results = await client.set_multiple_volumes(saved)
            logger.info(f'Restored media player volumes: {results}')
        finally:
            await client.close()


media_ducker = MediaPlayerDucker()
