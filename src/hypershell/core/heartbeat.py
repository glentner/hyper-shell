# SPDX-FileCopyrightText: 2021 Geoffrey Lentner
# SPDX-License-Identifier: Apache-2.0

"""Heartbeat data passed between client and server."""


# type annotations
from __future__ import annotations
from typing import Type

# standard libs
import json
from enum import Enum
from uuid import uuid4 as gen_uuid
from datetime import datetime
from dataclasses import dataclass

# internal libs
from .logging import HOSTNAME


class ClientState(Enum):
    """Client state."""

    RUNNING = 0
    FINISHED = 1

    @classmethod
    def from_value(cls: Type[ClientState], value: int) -> ClientState:
        """Instance from associated integer value."""
        return {0: cls.RUNNING, 1: cls.FINISHED}.get(value)


@dataclass
class Heartbeat:
    """Momentary notice of a client's active status."""

    uuid: str
    host: str
    time: datetime
    state: ClientState

    @classmethod
    def new(cls: Type[Heartbeat],
            uuid: str = None,
            host: str = None,
            time: datetime = None,
            state: ClientState = None) -> Heartbeat:
        """Create new instance."""
        return cls(uuid=(uuid or str(gen_uuid())),
                   host=(host or HOSTNAME),
                   time=(time or datetime.now()),
                   state=(state or ClientState.RUNNING))

    def pack(self: Heartbeat) -> bytes:
        """Serialize data."""
        return json.dumps({'uuid': self.uuid,
                           'host': self.host,
                           'time': str(self.time),
                           'state': self.state.value}).encode('utf-8')

    @classmethod
    def unpack(cls: Type[Heartbeat], data: bytes) -> Heartbeat:
        """Deserialize from raw `data`."""
        data = json.loads(data.decode('utf-8'))
        data['time'] = datetime.fromisoformat(data['time'])
        data['state'] = ClientState.from_value(data['state'])
        return cls(**data)

