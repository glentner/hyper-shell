# SPDX-FileCopyrightText: 2021 Geoffrey Lentner
# SPDX-License-Identifier: Apache-2.0

"""
Connect to server and run tasks.

TODO: examples and notes
"""


# type annotations
from __future__ import annotations
from typing import List, Tuple, Optional, Callable, Dict

# standard libs
import os
import sys
import logging
import functools
from enum import Enum
from datetime import datetime
from queue import Queue, Empty as QueueEmpty, Full as QueueFull
from subprocess import Popen, TimeoutExpired

# external libs
from cmdkit.app import Application, exit_status
from cmdkit.cli import Interface

# internal libs
from hypershell.core.config import default, config
from hypershell.core.fsm import State, StateMachine
from hypershell.core.thread import Thread
from hypershell.core.queue import QueueClient, QueueConfig
from hypershell.core.logging import HOSTNAME, Logger
from hypershell.core.exceptions import handle_exception
from hypershell.database.model import Task

# public interface
__all__ = ['run_client', 'ClientThread', 'ClientApp', 'DEFAULT_TEMPLATE', ]


# module level logger
log: Logger = logging.getLogger(__name__)


class SchedulerState(State, Enum):
    """Finite states for scheduler."""
    START = 0
    GET_REMOTE = 1
    UNPACK = 2
    POP_TASK = 3
    PUT_LOCAL = 4
    HALT = 5


class ClientScheduler(StateMachine):
    """Receive task bundles from server and schedule locally."""

    queue: QueueClient
    local: Queue[Optional[Task]]
    bundle: List[bytes]

    task: Task
    tasks: List[Task]
    final_task_id: str = None

    state = SchedulerState.START
    states = SchedulerState

    def __init__(self, queue: QueueClient, local: Queue[Optional[Task]]) -> None:
        """Initialize IO `stream` to read tasks and submit to database."""
        self.queue = queue
        self.local = local
        self.bundle = []
        self.tasks = []

    @functools.cached_property
    def actions(self) -> Dict[SchedulerState, Callable[[], SchedulerState]]:
        return {
            SchedulerState.START: self.start,
            SchedulerState.GET_REMOTE: self.get_remote,
            SchedulerState.UNPACK: self.unpack_bundle,
            SchedulerState.POP_TASK: self.pop_task,
            SchedulerState.PUT_LOCAL: self.put_local,
        }

    @staticmethod
    def start() -> SchedulerState:
        """Jump to GET_REMOTE state."""
        log.debug('Started scheduler')
        return SchedulerState.GET_REMOTE

    def get_remote(self) -> SchedulerState:
        """Get the next task bundle from the server."""
        try:
            self.bundle = self.queue.scheduled.get(timeout=2)
            self.queue.scheduled.task_done()
            if self.bundle is not None:
                log.debug(f'Received {len(self.bundle)} task(s) from server')
                return SchedulerState.UNPACK
            else:
                log.debug('Received disconnect')
                return SchedulerState.HALT
        except QueueEmpty:
            return SchedulerState.GET_REMOTE

    def unpack_bundle(self) -> SchedulerState:
        """Unpack latest bundle of tasks."""
        self.tasks = [Task.unpack(data) for data in self.bundle]
        self.final_task_id = self.tasks[-1].id
        return SchedulerState.POP_TASK

    def pop_task(self) -> SchedulerState:
        """Pop next task off current task list."""
        try:
            self.task = self.tasks.pop(0)
            return SchedulerState.PUT_LOCAL
        except IndexError:
            return SchedulerState.GET_REMOTE

    def put_local(self) -> SchedulerState:
        """Put latest task on the local task queue."""
        try:
            self.local.put(self.task, timeout=2)
            return SchedulerState.POP_TASK
        except QueueFull:
            return SchedulerState.PUT_LOCAL


class ClientSchedulerThread(Thread):
    """Run client scheduler in dedicated thread."""

    def __init__(self, queue: QueueClient, local: Queue[Optional[bytes]]) -> None:
        """Initialize machine."""
        super().__init__(name='hypershell-client-scheduler')
        self.machine = ClientScheduler(queue=queue, local=local)

    def run(self) -> None:
        """Run machine."""
        self.machine.run()
        self.stop()

    def stop(self, wait: bool = False, timeout: int = None) -> None:
        """Stop machine."""
        self.machine.halt()
        log.debug('Stopping scheduler')
        super().stop(wait=wait, timeout=timeout)

    @property
    def final_task_id(self) -> Optional[str]:
        """Task id of the last task from the last bundle."""
        return self.machine.final_task_id


DEFAULT_BUNDLESIZE: int = default.client.bundlesize
DEFAULT_BUNDLEWAIT: int = default.client.bundlewait


class CollectorState(State, Enum):
    """Finite states of collector."""
    START = 0
    GET_LOCAL = 1
    CHECK_BUNDLE = 2
    PACK_BUNDLE = 3
    PUT_REMOTE = 4
    FINALIZE = 5
    HALT = 6


class ClientCollector(StateMachine):
    """Collect finished tasks and bundle for outgoing queue."""

    tasks: List[Task]
    bundle: List[bytes]

    queue: QueueClient
    local: Queue[Optional[Task]]

    bundlesize: int
    bundlewait: int
    previous_send: datetime

    state = CollectorState.START
    states = CollectorState

    def __init__(self, queue: QueueClient, local: Queue[Optional[Task]],
                 bundlesize: int = DEFAULT_BUNDLESIZE, bundlewait: int = DEFAULT_BUNDLEWAIT) -> None:
        """Collect tasks from local queue of finished tasks and push them to the server."""
        self.tasks = []
        self.bundle = []
        self.local = local
        self.queue = queue
        self.bundlesize = bundlesize
        self.bundlewait = bundlewait

    @functools.cached_property
    def actions(self) -> Dict[CollectorState, Callable[[], CollectorState]]:
        return {
            CollectorState.START: self.start,
            CollectorState.GET_LOCAL: self.get_local,
            CollectorState.CHECK_BUNDLE: self.check_bundle,
            CollectorState.PACK_BUNDLE: self.pack_bundle,
            CollectorState.PUT_REMOTE: self.put_remote,
            CollectorState.FINALIZE: self.finalize,
        }

    def start(self) -> CollectorState:
        """Jump to GET_LOCAL state."""
        log.debug('Started collector')
        self.previous_send = datetime.now()
        return CollectorState.GET_LOCAL

    def get_local(self) -> CollectorState:
        """Get the next task from the local completed task queue."""
        try:
            task = self.local.get(timeout=1)
            self.local.task_done()
            if task is not None:
                self.tasks.append(task)
                return CollectorState.CHECK_BUNDLE
            else:
                return CollectorState.FINALIZE
        except QueueEmpty:
            return CollectorState.CHECK_BUNDLE

    def check_bundle(self) -> CollectorState:
        """Check state of task bundle and proceed with return if necessary."""
        wait_time = (datetime.now() - self.previous_send)
        since_last = wait_time.total_seconds()
        if len(self.tasks) >= self.bundlesize:
            log.trace(f'Bundle size ({len(self.tasks)}) reached')
            return CollectorState.PACK_BUNDLE
        elif since_last >= self.bundlewait:
            log.trace(f'Wait time exceeded ({wait_time})')
            return CollectorState.PACK_BUNDLE
        else:
            return CollectorState.GET_LOCAL

    def pack_bundle(self) -> CollectorState:
        """Pack tasks into bundle before pushing back to server."""
        self.bundle = [task.pack() for task in self.tasks]
        return CollectorState.PUT_REMOTE

    def put_remote(self) -> CollectorState:
        """Push out bundle of completed tasks."""
        if self.bundle:
            self.queue.completed.put(self.bundle)
            log.trace(f'Returned bundle of {len(self.bundle)} task(s)')
            self.tasks.clear()
            self.bundle.clear()
            self.previous_send = datetime.now()
        else:
            log.trace('No local tasks to return')
        return CollectorState.GET_LOCAL

    def finalize(self) -> CollectorState:
        """Push out any remaining tasks and halt."""
        self.put_remote()
        log.debug('Stopping collector')
        return CollectorState.HALT


class ClientCollectorThread(Thread):
    """Run client collector within dedicated thread."""

    def __init__(self, queue: QueueClient, local: Queue[Optional[bytes]],
                 bundlesize: int = DEFAULT_BUNDLESIZE, bundlewait: int = DEFAULT_BUNDLEWAIT) -> None:
        """Initialize machine."""
        super().__init__(name='hypershell-client-collector')
        self.machine = ClientCollector(queue=queue, local=local, bundlesize=bundlesize, bundlewait=bundlewait)

    def run(self) -> None:
        """Run machine."""
        self.machine.run()
        self.stop()

    def stop(self, wait: bool = False, timeout: int = None) -> None:
        """Stop machine."""
        self.machine.halt()
        super().stop(wait=wait, timeout=timeout)


DEFAULT_TEMPLATE = '{}'


class TaskState(State, Enum):
    """Finite states for task executor."""
    START = 0
    GET_LOCAL = 1
    START_TASK = 2
    WAIT_TASK = 3
    PUT_LOCAL = 4
    FINALIZE = 5
    HALT = 6


class TaskExecutor(StateMachine):
    """Run tasks locally."""

    id: int
    task: Task
    process: Popen
    template: str

    inbound: Queue[Optional[Task]]
    outbound: Queue[Optional[Task]]

    state = TaskState.START
    states = TaskState

    def __init__(self, id: int, inbound: Queue[Optional[Task]], outbound: Queue[Optional[Task]],
                 template: str = DEFAULT_TEMPLATE) -> None:
        """Initialize task executor."""
        self.id = id
        self.template = template
        self.inbound = inbound
        self.outbound = outbound

    @functools.cached_property
    def actions(self) -> Dict[TaskState, Callable[[], TaskState]]:
        return {
            TaskState.START: self.start,
            TaskState.GET_LOCAL: self.get_local,
            TaskState.START_TASK: self.start_task,
            TaskState.WAIT_TASK: self.wait_task,
            TaskState.PUT_LOCAL: self.put_local,
            TaskState.FINALIZE: self.finalize,
        }

    def start(self) -> TaskState:
        """Jump to GET_LOCAL state."""
        log.debug(f'Started executor ({self.id})')
        return TaskState.GET_LOCAL

    def get_local(self) -> TaskState:
        """Get the next task from the local queue of new tasks."""
        try:
            self.task = self.inbound.get(timeout=1)
            return TaskState.START_TASK if self.task else TaskState.FINALIZE
        except QueueEmpty:
            return TaskState.GET_LOCAL

    def start_task(self) -> TaskState:
        """Start current task locally."""
        self.task.command = self.template.replace('{}', self.task.args)
        self.task.start_time = datetime.now().astimezone()
        self.task.client_host = HOSTNAME
        log.trace(f'Running task ({self.task.id})')
        self.process = Popen(self.task.command, shell=True, stdout=sys.stdout, stderr=sys.stderr,
                             env={**os.environ, 'TASK_ID': self.task.id, 'TASK_ARGS': self.task.args})
        return TaskState.WAIT_TASK

    def wait_task(self) -> TaskState:
        """Wait for current task to complete."""
        try:
            self.task.exit_status = self.process.wait(timeout=2)
            self.task.completion_time = datetime.now().astimezone()
            log.trace(f'Completed task ({self.task.id})')
            return TaskState.PUT_LOCAL
        except TimeoutExpired:
            return TaskState.WAIT_TASK

    def put_local(self) -> TaskState:
        """Put completed task on outbound queue."""
        try:
            self.outbound.put(self.task, timeout=2)
            return TaskState.GET_LOCAL
        except QueueFull:
            return TaskState.PUT_LOCAL

    def finalize(self) -> TaskState:
        """Push out any remaining tasks and halt."""
        log.debug(f'Stopping executor ({self.id})')
        return TaskState.HALT


class TaskThread(Thread):
    """Run task executor within dedicated thread."""

    def __init__(self, id: int,
                 inbound: Queue[Optional[str]], outbound: Queue[Optional[str]],
                 template: str = DEFAULT_TEMPLATE) -> None:
        """Initialize task executor."""
        super().__init__(name=f'hypershell-executor-{id}')
        self.machine = TaskExecutor(id=id, inbound=inbound, outbound=outbound, template=template)

    def run(self) -> None:
        """Run machine."""
        self.machine.run()
        self.stop()

    def stop(self, wait: bool = False, timeout: int = None) -> None:
        """Stop machine."""
        self.machine.halt()
        super().stop(wait=wait, timeout=timeout)


class ClientThread(Thread):
    """Manage asynchronous task bundle scheduling and receiving."""

    client: QueueClient
    num_tasks: int

    inbound: Queue[Optional[Task]]
    outbound: Queue[Optional[Task]]

    scheduler: ClientSchedulerThread
    collector: ClientCollectorThread

    executors: List[TaskThread]

    def __init__(self,
                 num_tasks: int = 1,
                 bundlesize: int = DEFAULT_BUNDLESIZE, bundlewait: int = DEFAULT_BUNDLEWAIT,
                 address: Tuple[str, int] = (QueueConfig.host, QueueConfig.port),
                 auth: str = QueueConfig.auth, template: str = DEFAULT_TEMPLATE) -> None:
        """Initialize queue manager and child threads."""
        super().__init__(name='hypershell-client')
        self.num_tasks = num_tasks
        self.client = QueueClient(config=QueueConfig(host=address[0], port=address[1], auth=auth))
        self.inbound = Queue(maxsize=DEFAULT_BUNDLESIZE)
        self.outbound = Queue(maxsize=DEFAULT_BUNDLESIZE)
        self.scheduler = ClientSchedulerThread(queue=self.client, local=self.inbound)
        self.collector = ClientCollectorThread(queue=self.client, local=self.outbound,
                                               bundlesize=bundlesize, bundlewait=bundlewait)
        self.executors = [TaskThread(id=count+1, inbound=self.inbound, outbound=self.outbound, template=template)
                          for count in range(num_tasks)]

    def run(self) -> None:
        """Start child threads, wait."""
        log.info(f'Starting client with {self.num_tasks} task executor(s)')
        with self.client:
            self.start_threads()
            self.wait_scheduler()
            self.wait_executors()
            self.wait_collector()
            self.register_final_task()
        log.info('Stopped')

    def start_threads(self) -> None:
        """Start child threads."""
        self.scheduler.start()
        self.collector.start()
        for executor in self.executors:
            executor.start()

    def wait_scheduler(self) -> None:
        """Wait for all tasks to be completed."""
        self.scheduler.join()

    def wait_executors(self) -> None:
        """Send disconnect signal to each task executor thread."""
        for _ in self.executors:
            self.inbound.put(None)  # signal executors to shutdown
        for thread in self.executors:
            thread.join()

    def wait_collector(self) -> None:
        """Signal collector to halt."""
        self.outbound.put(None)
        self.collector.join()

    def register_final_task(self) -> None:
        """Send final task ID to server."""
        log.trace(f'Registering final task ({self.scheduler.final_task_id})')
        self.client.terminator.put(self.scheduler.final_task_id.encode())

    def stop(self, wait: bool = False, timeout: int = None) -> None:
        """Stop child threads before main thread."""
        log.debug('Stopping client')
        self.scheduler.stop(wait=wait, timeout=timeout)
        self.collector.stop(wait=wait, timeout=timeout)
        super().stop(wait=wait, timeout=timeout)


def run_client(num_tasks: int = 1, bundlesize: int = DEFAULT_BUNDLESIZE, bundlewait: int = DEFAULT_BUNDLEWAIT,
               address: Tuple[str, int] = (QueueConfig.host, QueueConfig.port), auth: str = QueueConfig.auth,
               template: str = DEFAULT_TEMPLATE) -> None:
    """Run client until disconnect signal received."""
    thread = ClientThread.new(num_tasks=num_tasks, bundlesize=bundlesize, bundlewait=bundlewait,
                              address=address, auth=auth, template=template)
    try:
        thread.join()
    except Exception:
        thread.stop()
        raise


APP_NAME = 'hypershell client'
APP_USAGE = f"""\
usage: {APP_NAME} [-h] [-N NUM] [-H ADDR] [-p PORT] [-t TEMPLATE]
Run client.\
"""

APP_HELP = f"""\
{APP_USAGE}

options:
-N, --num-tasks   NUM   Number of tasks to run in parallel.
-t, --template    CMD   Command-line template pattern.
-b, --bundlesize  SIZE  Number of lines to buffer (default: {DEFAULT_BUNDLESIZE}).
-w, --bundlewait  SEC   Seconds to wait before flushing tasks (default: {DEFAULT_BUNDLEWAIT}).
-H, --host        ADDR  Hostname for server.
-p, --port        NUM   Port number for server.
-h, --help              Show this message and exit.\
"""


class ClientApp(Application):
    """Run client."""

    name = APP_NAME
    interface = Interface(APP_NAME, APP_USAGE, APP_HELP)

    num_tasks: int = 1
    interface.add_argument('-N', '--num_tasks', type=int, default=num_tasks)

    host: str = QueueConfig.host
    interface.add_argument('-H', '--host', default=host)

    port: int = QueueConfig.port
    interface.add_argument('-p', '--port', type=int, default=port)

    authkey: str = QueueConfig.auth
    interface.add_argument('--auth', default=authkey)

    template: str = DEFAULT_TEMPLATE
    interface.add_argument('-t', '--template', default=template)

    bundlesize: int = config.submit.bundlesize
    interface.add_argument('-b', '--bundlesize', type=int, default=bundlesize)

    bundlewait: int = config.submit.bundlewait
    interface.add_argument('-w', '--bundlewait', type=int, default=bundlewait)

    exceptions = {
        ConnectionRefusedError: functools.partial(handle_exception, logger=log, status=exit_status.runtime_error),
        **Application.exceptions,
    }

    def run(self) -> None:
        """Run client."""
        run_client(num_tasks=self.num_tasks, bundlesize=self.bundlesize, bundlewait=self.bundlewait,
                   address=(self.host, self.port), auth=self.authkey, template=self.template)