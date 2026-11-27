"""Start or release one Colab VM by a notebook hash the broker chose.

Runs with the pinned Colab CLI's own Python (/opt/colab-ci/venv/bin/python), as colabci:

    colab_vm.py new <hash-file> <config> <name> <gpu>   # `colab new`, with our notebook hash
    colab_vm.py release <hash-file> <gpu>               # unassign the VM of that hash, if any

`colab new` picks a random notebook hash and, when Colab is slow to place a VM, can be killed
after the server already assigned one, which then bills with no session left to stop. With a
hash the broker wrote down first, `release` finds that exact VM (and never another session on
the account) and gives it back. Relies on colab_cli 0.8.0 internals; install.sh pins it.
"""
import sys
import uuid
from pathlib import Path


def options(gpu):
    from colab_cli.commands.session import resolve_runtime_options

    return resolve_runtime_options(None if gpu == "CPU" else gpu)


def new(hash_file, config, name, gpu):
    import colab_cli.commands.session as session
    from colab_cli.cli import main

    fixed = uuid.UUID(Path(hash_file).read_text().strip())

    class FixedUUID:
        UUID = uuid.UUID

        @staticmethod
        def uuid4():
            return fixed

    session.uuid = FixedUUID
    args = ["--config", config, "new", "-s", name]
    if gpu != "CPU":
        args += ["--gpu", gpu]
    sys.argv = ["colab", *args]
    return main()


def release(hash_file, gpu):
    from colab_cli.client import Assignment
    from colab_cli.common import state

    fixed = uuid.UUID(Path(hash_file).read_text().strip())
    variant, accelerator, shape = options(gpu)
    found = state.client._get_assignment(fixed, variant, accelerator, shape)
    if isinstance(found, Assignment):
        state.client.unassign(found.endpoint)
        print(f"released {found.endpoint}")
    else:
        print("no VM for this hash")
    return 0


if __name__ == "__main__":
    command, *rest = sys.argv[1:]
    sys.exit(new(*rest) if command == "new" else release(*rest))
