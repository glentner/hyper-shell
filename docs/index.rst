hyper-shell
===========

Release v\ |release| (:ref:`Getting Started <getting_started>`)

.. image:: https://img.shields.io/badge/license-Apache-blue.svg?style=flat
    :target: https://www.apache.org/licenses/LICENSE-2.0
    :alt: License

.. image:: https://img.shields.io/pypi/v/hyper-shell.svg?style=flat&color=blue
    :target: https://pypi.org/project/hyper-shell
    :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/hyper-shell.svg?logo=python&logoColor=white&style=flat
    :target: https://pypi.org/project/hyper-shell
    :alt: Python Versions

.. image:: https://readthedocs.org/projects/hyper-shell/badge/?version=latest&style=flat
    :target: https://hyper-shell.readthedocs.io
    :alt: Documentation

.. image:: https://pepy.tech/badge/hyper-shell
    :target: https://pepy.tech/badge/hyper-shell
    :alt: Downloads

|

.. include:: _include/desc.rst

Several tools offer similar functionality but not all together in a single tool with
the user ergonomics we provide. Novel design elements include but are not limited to
(1) cross-platform, (2) client-server design, (3) staggered launch for large scales,
(4) persistent hosting of the server, and optionally (5) a database in-the-loop for
persisting task metadata and automated retries.

*HyperShell* is pure Python and is tested on Linux, macOS, and Windows 10 in
Python 3.9+ environments. The server and client don't even need to use the same
platform simultaneously.

-------------------

Features
--------

|

**Simple, Scalable**

Take a listing of shell commands and process them in parallel.
In this example, we use the ``-t`` option to specify a template for the input arguments
which are not fully formed shell commands. Larger workloads will want to use a database
for managing tasks and scheduling. In this case, we can run this small example with
``--no-db`` to disable the database and submit tasks directly to the shared queue.

.. admonition:: Hello World
    :class: note

    .. code-block:: shell

        seq 4 | hyper-shell cluster -N2 -t 'echo {}' --no-db

    .. details:: Output

        .. code-block:: none

            0
            1
            2
            4

|

Scale out to remote servers with SSH and even define *groups* in your configuration file.
By default, all command `stdout` and `stderr` are joined and written out directly.
Capture individual task `stdout` and `stderr` with ``--capture``.
Set the :ref:`logging <logging>` level to ``INFO`` to see each task start or ``DEBUG`` to
see additional detail about what is running, where, and when.

.. admonition:: Distributed Cluster over SSH
    :class: note

    .. code-block:: shell

        hyper-shell cluster tasks.in -N4 --ssh-group=xyz --capture

    .. details:: Logs

        .. code-block:: none

            2022-03-14 12:29:19.659 a00.cluster.xyz   INFO [hypershell.client] Running task (5fb74a31-fc38-4535-8b45-c19bc3dbedee)
            2022-03-14 12:29:19.665 a01.cluster.xyz   INFO [hypershell.client] Running task (c1d32c32-3e76-48e0-b2c3-9420ea20b41b)
            2022-03-14 12:29:19.668 a02.cluster.xyz   INFO [hypershell.client] Running task (4a6e19ec-d325-468f-a55b-03a797eb51d5)
            2022-03-14 12:29:19.671 a03.cluster.xyz   INFO [hypershell.client] Running task (09587f55-4b50-4e2b-a528-55c60667b62a)
            2022-03-14 12:29:19.674 a04.cluster.xyz   INFO [hypershell.client] Running task (1336f778-c9ab-4111-810e-229d572be62e)


|

**Flexible**

One of several novel features of *hyper-shell*, however, is the ability to independently
stand up the *server* on one machine and then connect to that server using a *client* from
a different environment.

Start the *hyper-shell server* and set the bind address to ``0.0.0.0`` to allow remote connections.
The server schedules tasks on a distributed queue. It is recommended that you protect your instance
with a private *key* (``-k/--auth``).

.. admonition:: Server
    :class: note

    .. code-block:: shell

        hyper-shell server -H '0.0.0.0' -k '<AUTHKEY>' --print < tasks.in > tasks.failed


Connect to the running server from a different host (even from a different platform, e.g., Windows).
You can connect with any number of clients from any number of hosts. The separate client connections
will each pull tasks off the queue asynchronously, balancing the load.

.. admonition:: Client
    :class: note

    .. code-block:: shell

        hyper-shell client -H '<HOSTNAME>' -k '<AUTHKEY>'

|

**Dynamic**

Special variables are automatically defined for each individual task. For example, ``TASK_ID`` gives
a unique UUID for each task (regardless of which client executes the task).

Further, any environment variable defined with the ``HYPERSHELL_EXPORT_`` prefix will be injected into
the environment of each task, *sans prefix*.

Use ``-t`` (short for ``--template``) to expand a template, ``{}`` can be used to insert the incoming
task arguments (alternatively, use ``TASK_ARGS``). Be sure to use single quotes to delay the variable
expansion. Many meta-patterns are supported (see full overview of :ref:`templates <templates>`):

* File operations (e.g., the basename ``'{/}'``)
* Slicing on whitespace (e.g., first ``'{[0]}'``, first three ``'{[:3]}'``, every other ``'{[::2]}'``)
* Sub-commands (e.g., ``'{% dirname @ %}'``)
* Lambda expressions in *x* (e.g., ``'{= x + 1 =}'``)

.. admonition:: Templates
    :class: note

    .. code-block:: shell

        hyper-shell cluster tasks.in -N12 -t './some_program.py {} >outputs/{/-}.out'

Capturing `stdout` and `stderr` is supported directly in fact with the ``--capture`` option.
See the full documentation for environment variables under :ref:`configuration <config>`.

|

.. toctree::
    :hidden:
    :caption: Intro

    getting_started
    install

.. toctree::
    :hidden:
    :caption: Reference

    cli/index
    api/index
    config
    logging
    database
    templates

.. toctree::
    :hidden:
    :caption: Tutorial

    tutorial/basic
    tutorial/distributed
    tutorial/hybrid
    tutorial/advanced

.. toctree::
    :hidden:
    :caption: Project

    blog/index
    roadmap

.. toctree::
    :hidden:
    :caption: Development

    contributing
    license

.. toctree::
    :hidden:
    :caption: Supplemental

    citation
