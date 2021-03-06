Manual Page for Hyper-shell
===========================

Synopsis
--------

| hyper-shell client  [-h] [*args*...]
| hyper-shell server  [-h] *TASKFILE* [*args*...]
| hyper-shell cluster [-h] *TASKFILE* [*args*...]

Description
-----------

The ``hyper-shell`` utility is a cross-platform, high performance computing
utility for processing arbitrary shell commands over a distributed, asynchronous
queue.

The hyper-shell server program accepts command lines as input and publishes
them to a shared queue. Any number of hyper-shell clients can connect to that
server either locally or from a remote machine. The clients pull these tasks off
the queue asynchronously. The hyper-shell cluster program allows the user to
automatically launch an appropriate number of clients under various schemes.

The hyper-shell cluster can also be launched in *parsl* mode. This loads a
named configuration from ``~/.hyper-shell/parsl_config.py`` and dispatches
tasks using the given scheduler (e.g., SLURM, Kubernetes). See
`parsl-project.org <https://parsl-project.org>`_


Global Options
--------------

Network Options
^^^^^^^^^^^^^^^
When running locally and in ``cluster`` mode, nothing need be specified.
Otherwise, the ``server``'s bind address may need to be set to allow for
remote connections. The port number and authkey are arbitrary choices.

-H, --host *ADDR*
    Address for server (default: localhost). For the ``server`` this is
    the bind address to use. For clients to be allowed to connect you will
    need to set this to 0.0.0.0 for the server.

.. code-block:: none

    user@host-1 ~$ hyper-shell server -H 0.0.0.0

.. code-block:: none

    user@host-2 ~$ hyper-shell client -H host-1


-p, --port *PORT*
    Port number for server (default: 50001). The port number is an arbitrary
    choice and just needs to be allowed by the server (not blocked or reserved).

-k, --authkey *KEY*
    Cryptographic key for connection (default: '--BADKEY--'). This is set by the
    server and required for clients to connect. The default is intentionally
    meant to suggest you set something more appropriate. In ``cluster`` mode, a
    128bit hex-token is autogenerated if none is explicitly provided.

Logging Options
^^^^^^^^^^^^^^^
All logging messages are written to ``stderr`` to allow for command outputs
to occupy ``stdout``. By default, the logging level is set to *WARNING*, so
no logging will be done unless there is some kind of issue (e.g., non-zero
exit status). Logging messages are colored according to their severity; blue,
green, yellow, red, and purple for debug, info, warning, error, and critical,
respectively. If ``stderr`` is being redirected, colors will be disabled.

The ``--logging`` switch is meant to facilitate job tracking in a distributed
computing context, including timestamps and hostnames in messages.

-v, --verbose
    Include information level messages. (conflicts with ``--debug``).

-d, --debug
    Include debugging level messages. (conflicts with ``--verbose``).

-l, --logging
    Show detailed syslog style messages. This disables colorized output and
    alters the format of messages to include a timestamp, hostname, and the
    level name.


Server Usage
------------

The hyper-shell server reads command lines from a file (or ``stdin``). If no
arguments are given, a usage statement is printed. To avoid this and simply run
with all defaults, reading from ``stdin``, ``-`` symbolizes standard input.

Any command that returns a non-zero exit status will have a warning message
emitted and the original command line will be printed to ``stdout``. In this
way, the server acts like a sieve, consuming commands and emitting failures.

Server Options
^^^^^^^^^^^^^^
-o, --output *FILE*
    Path to file for failed commands (default: <stdout>).

-s, --maxsize *SIZE*
    Maximum size of the queue (default: 10000). To avoid the server queueing up
    too many tasks, this will force the server to block if clients have not yet
    taken enough commands. This is helpful for pipelines.


Client Usage
------------

The client connects to the server and pulls commands off one at a time,
executing them on the local shell. The shell and environment inherit from the
client's execution environment.

The output of commands are simply redirected to ``stdout`` unless otherwise
specified by ``--output``. To isolate output from individual commands, you can
specify how to redirect from inside the command template; e.g.,

.. code-block:: none

    $ hyper-shell client ... -t '{} >$TASK_ID.out'

With no arguments, the client will just print a usage statement and exit.
To prompt the client to run with all default arguments, a ``--`` is
interpreted as a simple noarg.

.. code-block:: none

    $ hyper-shell client --

Client Options
^^^^^^^^^^^^^^
-x, --timeout *SEC*
    Length of time in seconds before disconnecting (default: 0). If finished
    with previous command and no other commands are published by the server
    after this period of time, automatically disconnect and shutdown. A
    timeout of 0 is special and means never timeout.

-t, --template *CMD*
    Template command (default: "{}"). Any valid command can be a template.
    All "{}" are substituted (if present) as the input task argument.

-o, --output *FILE*
    Path to file for command outputs (default: <stdout>).

Parsl Mode
^^^^^^^^^^
These options are pass to the client by the cluster program to trigger a single
client to launch *parsl*. Running more than one client instance in parsl
mode will invoke more than one parsl cluster.

--parsl [--profile *NAME*]
    Hand-off tasks to Parsl (default profile: "local"). The "local" profile just
    uses threads and really only works as a placeholder for testing purposes.
    Running the cluster in ``--local`` mode is to be preferred.


Cluster Usage
-------------

The program offers a concise means to launch a workflow. In all cases, a
server is started. Depending on the launch scheme selected, one or more
clients will be launched locally or remotely for you.

Cluster Modes
^^^^^^^^^^^^^
Each mode is mutually exclusive. The associated partner options are only
valid if given with their launcher option.

--local [-N | --num-cores *NUM*]
    Launch clients locally. A new client process will be started for each "core"
    requested. By default, it will launch as many clients as there are cores on
    the machine. These clients will launch using the exact path to the current
    executable.

--ssh [--nodefile *FILE*]
    Launch clients with SSH. The *nodefile* should enumerate the hosts to be
    used. An SSH session will be created for every line in this file.
    SSH-keys should be setup to allow password-less connections. If not given,
    a global ~/.hyper-shell/nodefile can be used.

--mpi [--nodefile *FILE*]
    Launch clients with MPI. The *FILE* is passed to the ``-machinefile`` option
    for ``mpiexec``. If not given, rely on ``mpiexec`` to know what to do.

--parsl [--profile *NAME*]
    Launch a single client to run in *parsl* mode. This loads a
    ``parsl.config.Config`` object from ``~/.hyper-shell/parsl_config.py``. If
    not specified, the profile defaults to "local", which just uses some number
    of threads locally.

Cluster Options
^^^^^^^^^^^^^^^
Some of these options are merely passed through to the server or the client.

-f, --failed *FILE*
    A file path to write commands which exited with a non-zero status. If not
    specified, nothing will be written.

-o, --output *FILE*
    A file path to write the output of commands. By default, if this option is
    not specified, all command outputs will be redirected to ``stdout`` .

-s, --maxsize *SIZE*
    Maximum size of the queue (default: 10000). To avoid the server queueing up
    too many tasks, this will force the server to block if clients have not yet
    taken enough commands. This is helpful for pipelines.

-t, --template *CMD*
    Template command (default: "{}").


Environment Variables
---------------------

All environment variables that start with the ``HYPERSHELL_`` prefix will be
injected into the execution environment of the tasks with the prefix stripped.

Example:

.. code-block:: none

    $ export HYPERSHELL_PATH=/other/bin:$PATH
    $ export HYPERSHELL_OTHER=FOO

All tasks will then have ``PATH=/other/bin:$PATH`` defined for the task as well
as a new variable, ``OTHER``.

``HYPERSHELL_EXE``

    When running the hyper-shell cluster with ``--ssh`` (or similar) it is
    not uncommon for the hyper-shell on the remote system to either be in a
    different location or not necessarily available on the *PATH*. Using the
    ``HYPERSHELL_EXE`` environment variable, set an explicit path to use.

.. code-block:: bash

    $ export HYPERSHELL_EXE=/other/bin/hyper-shell

``HYPERSHELL_CWD``

    When executed directly, the hyper-shell client will run tasks in the same
    directory as the client is running in. This can be changed by specifying the
    ``HYPERSHELL_CWD``.

.. code-block:: bash

    $ export HYPERSHELL_CWD=$HOME/other

``HYPERSHELL_LOGGING_LEVEL``

    You can specify what logging level to use without the need for a command line
    switch by defining this variable. Both numbered and named values are allowed;
    e.g., 0-4 or one of DEBUG, INFO, WARNING, ERROR, and CRITICAL.

.. code-block:: bash

    $ export HYPERSHELL_LOGGING_LEVEL=DEBUG

``HYPERSHELL_LOGGING_HANDLER``

    You can specify what logging style to use without the need for a command line
    switch by defining this variable. Allowed values are STANDARD or DETAILED,
    corresponding to the basic colorized messages and the syslog style detailed
    messages, respectively.

.. code-block:: bash

    $ export HYPERSHELL_LOGGING_HANDLER=DETAILED

All tasks will also have special variables defined within their environment
that are specific to that instance.

``TASK_ID``

    The unique integer identifier for this task. The value of ``TASK_ID`` is
    a count starting from zero set by the server.

``TASK_ARG``

    The input argument for this command. This  the  variable equivalent of '{}'
    and can be substituted as such. This may be useful for shell-isms in
    the command template.


Examples
--------

Simple Cluster
^^^^^^^^^^^^^^
Process an existing list of commands from some ``taskfile``. Presumably, one
could execute ``taskfile`` directly and the lines would be executed in serial.

.. code-block:: none

    $ hyper-shell cluster taskfile -f taskfile.failed

Dynamic Pipeline
^^^^^^^^^^^^^^^^
Await tasks and dispatch them as they arrive. It is common practice to use
all-caps to mark files as being transient in nature. In this case, ``TASKFILE``
is like a queue unto itself. Enable verbose logging with ``-vl``, redirect
outputs and view logging messages but also append them to a file using ``tee``.

.. code-block:: none

    $ tail -f TASKFILE | hyper-shell cluster -vl -N4 -f FAILED \
        2>&1 1>OUTPUTS | tee -a hyper-shell.log

Server and Clients
^^^^^^^^^^^^^^^^^^
Start a server manually to publish tasks. Define an access key using ``-k``
and set the bind address for the server so clients can connect remotely.

.. code-block:: none

    $ hyper-shell server -dlk 'some-key' -H 0.0.0.0 < taskfile > taskfile.failed

On different machines launch one or more clients. This can be done manually,
or in an automated fashion.

.. code-block:: none

    $ hyper-shell client -dlk 'some-key' -H 'server-hostname' > local.out

HPC Job (Direct)
^^^^^^^^^^^^^^^^
Schedule tasks on a computing cluster using a job scheduler, such as
`SLURM <https://slurm.schedmd.com>`_. A basic job script might be:

.. code-block:: bash

    #!/bin/bash
    #SBATCH --nodes=2
    #SBATCH --tasks-per-node=12
    #SBATCH --account=ACCOUNT

    # launch server
    hyper-shell server -dlH 0.0.0.0 < TASKFILE > FAILED \
        2>>hyper-shell.log

    # launch clients
    srun hyper-shell client -dlH `hostname` > OUTPUTS \
        2>>hyper-shell.log

HPC Job (Elastic)
^^^^^^^^^^^^^^^^^
Instead of scheduling a job with a fixed size, allow for a continuous pipeline
to exist and elastically scale the required backend-nodes according to the task
load.

On a login-node on the cluster:

.. code-block:: none

    $ hyper-shell cluster -dl --parsl --profile=myconfig < TASKFILE \
        >OUTPUTS 2>>hyper-shell.log

This will create a server and a single client which launches *parsl* using the
named configuration. In ``~/.hyper-shell/parsl_config.py``:

.. code-block:: python

    # see parsl.readthedocs.io
    from parsl.config import Config

    myconfig = Config(
        # implement your custom configuration
    )

Elastic Cloud Computing
^^^^^^^^^^^^^^^^^^^^^^^
On a small persistent compute instance, run the server in a pipeline
configuration. Then, setup your *parsl* configuration to use *Kubernetes*
(or similar) to elastically scale compute as necessary. Be sure to include
both *hyper-shell* and *parsl* in your compute image.

Hybrid Makefile and Hyper-Shell
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Using a *Makefile* to define a directed acyclic graph (DAG) for your
computations, whether in a local or HPC context is robust and to be encouraged.
In fact, *GNU Make* offers a parallel execution mode (using the ``-j`` flag). On
a single compute node this will not only execute tasks in parallel but uses the
filesystem to track successful and failed commands, facilitating the re-execution
of incomplete tasks without needlessly executing tasks that have succeeded.

In the context of tasks such as these, the dependency graph has branches that do
not connect for independent tasks. Example, issuing ``make outputs/task-1.out``
may be completely isolated from ``make outputs/task-2.out``. Let *Make* retain
the DAG and execution formulae; if one defines a top-level target that simply
prints all the final targets of the tasks, you can pipe that into something like
*hyper-shell* to run in a distributed context when necessary.

.. code-block:: none

    $ make list | hyper-shell cluster -t 'make {}' --mpi --nodefile $NODEFILE

You might even embed that in the *Makefile* itself to run in a distributed mode.

.. code-block:: none

    cluster:
        $(make) list | hyper-shell cluster -t '$(make) {}' --mpi --nodefile $(NODEFILE)


See Also
--------

ssh(1), mpiexec(1), tail(1), tee(1), make(1)
