"""
ESPHome Native API server base implementation.

Implements the ESPHome TCP protocol (protobuf framing, varuint parsing,
hello/connect/ping/disconnect handshake). Adapted from linux-voice-assistant
(https://github.com/OHF-Voice/linux-voice-assistant).
"""

import asyncio
import logging
from abc import abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, List, Optional

# pylint: disable=no-name-in-module
from aioesphomeapi._frame_helper.packets import make_plain_text_packets
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    AuthenticationRequest,
    AuthenticationResponse,
    DisconnectRequest,
    DisconnectResponse,
    HelloRequest,
    HelloResponse,
    PingRequest,
    PingResponse,
)
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from google.protobuf import message

PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

_LOGGER = logging.getLogger(__name__)


class ESPhomeAPIServer(asyncio.Protocol):
    """Base ESPHome Native API TCP server protocol."""

    def __init__(self, name: str) -> None:
        self.name = name

        self._buffer: Optional[bytes] = None
        self._buffer_len: int = 0
        self._pos: int = 0
        self._transport = None
        self._writelines = None

    @abstractmethod
    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """Handle an incoming protobuf message and return responses."""

    def process_packet(self, msg_type: int, packet_data: bytes) -> None:
        msg_class = MESSAGE_TYPE_TO_PROTO[msg_type]
        msg_inst = msg_class.FromString(packet_data)

        if isinstance(msg_inst, HelloRequest):
            self.send_messages([
                HelloResponse(
                    api_version_major=1,
                    api_version_minor=10,
                    name=self.name,
                )
            ])
            return

        if isinstance(msg_inst, AuthenticationRequest):
            self.send_messages([AuthenticationResponse()])
        elif isinstance(msg_inst, DisconnectRequest):
            self.send_messages([DisconnectResponse()])
            _LOGGER.debug("Disconnect requested")
            if self._transport:
                self._transport.close()
                self._transport = None
                self._writelines = None
        elif isinstance(msg_inst, PingRequest):
            self.send_messages([PingResponse()])
        elif msgs := self.handle_message(msg_inst):
            if isinstance(msgs, message.Message):
                msgs = [msgs]
            self.send_messages(msgs)

    def send_messages(self, msgs: List[message.Message]) -> None:
        if self._writelines is None:
            return

        packets = [
            (PROTO_TO_MESSAGE_TYPE[msg.__class__], msg.SerializeToString())
            for msg in msgs
        ]
        packet_bytes = make_plain_text_packets(packets)
        self._writelines(packet_bytes)

    def connection_made(self, transport) -> None:
        self._transport = transport
        self._writelines = transport.writelines
        peer = transport.get_extra_info("peername")
        _LOGGER.info("Home Assistant connected from %s", peer)

    def connection_lost(self, exc) -> None:
        self._transport = None
        self._writelines = None
        _LOGGER.info("Home Assistant disconnected")

    def data_received(self, data: bytes) -> None:
        if self._buffer is None:
            self._buffer = data
            self._buffer_len = len(data)
        else:
            self._buffer += data
            self._buffer_len += len(data)

        while self._buffer_len >= 3:
            self._pos = 0

            if (preamble := self._read_varuint()) != 0x00:
                _LOGGER.error("Incorrect preamble: %s", preamble)
                return

            if (length := self._read_varuint()) == -1:
                _LOGGER.error("Incorrect length: %s", length)
                return

            if (msg_type := self._read_varuint()) == -1:
                _LOGGER.error("Incorrect message type: %s", msg_type)
                return

            if length == 0:
                self._remove_from_buffer()
                self.process_packet(msg_type, b"")
                continue

            if (packet_data := self._read(length)) is None:
                return

            self._remove_from_buffer()
            self.process_packet(msg_type, packet_data)

    def _read(self, length: int) -> Optional[bytes]:
        new_pos = self._pos + length
        if self._buffer_len < new_pos:
            return None
        original_pos = self._pos
        self._pos = new_pos
        if TYPE_CHECKING:
            assert self._buffer is not None
        return self._buffer[original_pos:new_pos]

    def _read_varuint(self) -> int:
        if not self._buffer:
            return -1

        result = 0
        bitpos = 0
        cstr = self._buffer
        while self._buffer_len > self._pos:
            val = cstr[self._pos]
            self._pos += 1
            result |= (val & 0x7F) << bitpos
            if (val & 0x80) == 0:
                return result
            bitpos += 7
        return -1

    def _remove_from_buffer(self) -> None:
        end_of_frame_pos = self._pos
        self._buffer_len -= end_of_frame_pos
        if self._buffer_len == 0:
            self._buffer = None
            return
        if TYPE_CHECKING:
            assert self._buffer is not None
        cstr = self._buffer
        self._buffer = cstr[end_of_frame_pos: self._buffer_len + end_of_frame_pos]
