# This program is free software: you can redistribute it and/or modify it under the
# terms of the Apache License (v2.0) as published by the Apache Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the Apache License for more details.
#
# You should have received a copy of the Apache License along with this program.
# If not, see <https://www.apache.org/licenses/LICENSE-2.0>.

"""Run hyper-shell cluster, server and clients."""

# type annotations
from __future__ import annotations
from typing import Tuple

# standard libs
import sys
import time
import secrets
import psutil
import functools
from subprocess import Popen, PIPE

# internal libs
from ..__meta__ import __appname__
from ..core.logging import logger, HOST, setup as logging_setup
from ..core.queue import ADDRESS, MAXSIZE
from ..core.exceptions import print_and_exit
from .client import TEMPLATE

# external libs
from cmdkit.app import Application, exit_status
from cmdkit.cli import Interface, ArgumentError


# program name is constructed from module file name
NAME = 'cluster'
PROGRAM = f'{__appname__} {NAME}'
PADDING = ' ' * len(PROGRAM)

USAGE = f"""\
usage: {PROGRAM} FILE [--failures PATH] [--port NUM] [--maxsize SIZE] [--template CMD]
       {PADDING} [--local [--num-cores NUM] | [--ssh | --mpi] --nodefile PATH | --parsl [--profile NAME]]
       {PADDING} [--verbose | --debug] [--logging]
       {PADDING} [--help]

{__doc__}\
"""

HELP = f"""\
{USAGE}

arguments:
FILE                  Path to file for command list.

options:
-f, --failures  PATH  Path to file to write failed commands.
-p, --port      PORT  Port number for server (default: {ADDRESS[1]}).
-s, --maxsize   SIZE  Maximum items allowed in the queue (default: {MAXSIZE}).
-t, --template  CMD   Template command (default: "{TEMPLATE}").
    --local           Run cluster locally (uses --num-cores).
    --mpi             Run distributed cluster with MPI (uses --nodefile).
    --parsl           Run cluster using Parsl (uses --profile).
-N, --num-cores NUM   Number of cores to use (see --local).
    --nodefile  PATH  Path to node file (see --mpi).
    --profile   NAME  Name of parsl config to use.
-v, --verbose         Show info messages.
-d, --debug           Show debugging messages.
-l, --logging         Show detailed syslog style messages.
-h, --help            Show this message and exit.
"""


log = logger.with_name('hyper-shell.cluster')


class Cluster(Application):

    interface = Interface(PROGRAM, USAGE, HELP)

    taskfile: str = '-'
    interface.add_argument('taskfile')

    port: int = ADDRESS[1]
    interface.add_argument('-p', '--port', default=port, type=int)

    maxsize: int = MAXSIZE
    interface.add_argument('-s', '--maxsize', default=maxsize, type=int)

    failures: str = None
    interface.add_argument('-f', '--failures', default=None)

    template: str = TEMPLATE
    interface.add_argument('-t', '--template', default=template)

    # clustering method
    cluster_mode: str = 'local'
    cluster_modes: Tuple[str] = ('local', 'ssh', 'mpi', 'parsl')
    cluster_mode_interface = interface.add_mutually_exclusive_group()
    cluster_mode_interface.add_argument('--local', action='store_true', dest='use_local')
    cluster_mode_interface.add_argument('--ssh', action='store_true', dest='use_ssh')
    cluster_mode_interface.add_argument('--mpi', action='store_true', dest='use_mpi')
    cluster_mode_interface.add_argument('--parsl', action='store_true', dest='use_parsl')

    nodefile: str = None
    num_cores: int = None
    profile: str = 'local'  # name of parsl config to use (from config file)
    parallelism_interface = interface.add_mutually_exclusive_group()
    parallelism_interface.add_argument('--nodefile', default=None)
    parallelism_interface.add_argument('-N', '--num-cores', default=None, type=int)
    parallelism_interface.add_argument('--profile', default=profile)

    debug: bool = False
    verbose: bool = False
    logging_interface = interface.add_mutually_exclusive_group()
    logging_interface.add_argument('-d', '--debug', action='store_true')
    logging_interface.add_argument('-v', '--verbose', action='store_true')

    logging: bool = False
    interface.add_argument('-l', '--logging', action='store_true')

    exceptions = {
        RuntimeError: functools.partial(print_and_exit, logger=log.critical,
                                        status=exit_status.runtime_error),
        FileNotFoundError: functools.partial(print_and_exit, logger=log.critical,
                                             status=exit_status.runtime_error)
    }

    def run(self) -> None:
        """Run the hyper-shell cluster."""

        for mode in self.cluster_modes:
            if hasattr(self, f'use_{mode}') and getattr(self, f'use_{mode}') is True:
                self.cluster_mode = mode

        method = getattr(self, f'run_{self.cluster_mode}')
        method()

    def run_local(self) -> None:
        """Run the cluster in 'local' mode."""

        failures = '' if self.failures is None else f'--output {self.failures}'
        server_invocation = (f'hyper-shell server {self.taskfile} {failures} --port {self.port} '
                             f'--authkey {self.authkey} --maxsize {self.maxsize} {self.logging_args}')

        log.debug(f'starting server: {server_invocation}')
        server_process = Popen(server_invocation, shell=True, stdin=sys.stdin, stdout=PIPE, stderr=sys.stderr)

        client_invocation = (f'hyper-shell client --port {self.port} --authkey {self.authkey} '
                             f'{self.logging_args} --template "{self.template}"')

        num_cores = self.num_cores if self.num_cores is not None else psutil.cpu_count()
        log.debug(f'starting {num_cores} clients: {client_invocation}')
        time.sleep(2)  # o.w. clients might start too fast and be refused

        client_processes = []
        for _ in range(num_cores):
            client = Popen(client_invocation, shell=True, stdout=sys.stdout, stderr=sys.stderr)
            client_processes.append(client)

        for client in client_processes:
            client.wait()

        server_process.wait()

    def run_ssh(self) -> None:
        """Run the cluster in 'ssh' mode."""

        if self.nodefile is None:
            raise ArgumentError('no nodefile given')

        with open(self.nodefile, mode='r') as nodefile:
            log.debug(f'reading hostnames from {self.nodefile}')
            hostnames = [hostname.strip() for hostname in nodefile.readlines()]

        failures = '' if self.failures is None else f'--output {self.failures}'
        server_invocation = (f'hyper-shell server {self.taskfile} {failures} --host 0.0.0.0 --port {self.port} '
                             f'--authkey {self.authkey} --maxsize {self.maxsize} {self.logging_args}')

        log.debug(f'starting server: {server_invocation}')
        server_process = Popen(server_invocation, shell=True, stdin=sys.stdin, stdout=PIPE, stderr=sys.stderr)

        client_invocation = (f'hyper-shell client --host {HOST} --port {self.port} --authkey {self.authkey} '
                             f'{self.logging_args} --template "{self.template}"')

        num_hosts = len(set(hostnames))
        num_clients = len(hostnames)
        log.debug(f'starting {num_clients} clients across {num_hosts} hosts: {client_invocation}')
        time.sleep(2)

        client_processes = []
        for hostname in hostnames:
            client = Popen(f'ssh {hostname} {client_invocation}', shell=True,
                           stdout=sys.stdout, stderr=sys.stderr)
            client_processes.append(client)

        for client in client_processes:
            client.wait()

        server_process.wait()

    def run_mpi(self) -> None:
        """Run the cluster in 'mpi' mode."""

        failures = '' if self.failures is None else f'--output {self.failures}'
        server_invocation = (f'hyper-shell server {self.taskfile} {failures} --host 0.0.0.0 '
                             f'--port {self.port} --authkey {self.authkey} --maxsize {self.maxsize} '
                             f'{self.logging_args}')

        log.debug(f'starting server: {server_invocation}')
        server_process = Popen(server_invocation, shell=True, stdin=sys.stdin, stderr=sys.stderr)

        client_invocation = (f'hyper-shell client --host {HOST} --port {self.port} --authkey {self.authkey} '
                             f'{self.logging_args} --template "{self.template}"')

        log.debug(f'starting clients: {client_invocation}')
        time.sleep(2)

        mpi_invocation = f'mpiexec -machinefile {self.nodefile} {client_invocation}'
        mpi_process = Popen(mpi_invocation, shell=True, stdout=sys.stdout, stderr=sys.stderr)

        mpi_process.wait()
        server_process.wait()

    def run_parsl(self) -> None:
        """Run cluster in 'parsl' mode."""

        failures = '' if self.failures is None else f'--output {self.failures}'
        server_invocation = (f'hyper-shell server {self.taskfile} {failures} --port {self.port} '
                             f'--authkey {self.authkey} --maxsize {self.maxsize} {self.logging_args}')

        log.debug(f'starting server: {server_invocation}')
        server = Popen(server_invocation, shell=True, stdin=sys.stdin, stderr=sys.stderr)

        client_invocation = (f'hyper-shell client --port {self.port} --authkey {self.authkey} '
                             f'{self.logging_args} --template "{self.template}" '
                             f'--parsl --profile "{self.profile}"')

        time.sleep(2)  # o.w. clients might start too fast and be refused
        log.debug(f'starting client: {client_invocation}')
        client = Popen(client_invocation, shell=True, stdout=sys.stdout, stderr=sys.stderr)
        client.wait()

        # server exits when all clients signal
        server.wait()

    @property
    @functools.lru_cache(maxsize=1)
    def logging_args(self) -> str:
        """Necessary logging arguments for subprocess invocation."""
        args = ''
        if self.debug:
            args += '--debug'
        if self.verbose:
            args += '--verbose'
        if self.logging:
            args += ' --logging'
        return args

    @property
    @functools.lru_cache(maxsize=1)
    def authkey(self) -> str:
        """One-time cryptographic key for server/client connection."""
        return secrets.token_hex(nbytes=16)

    def __enter__(self) -> Cluster:
        """Initialize resources."""
        logging_setup(log, self.debug, self.verbose, self.logging)
        return self

    def __exit__(self, *exc) -> None:
        """Release resources."""


# inherit docstring from module
Cluster.__doc__ = __doc__