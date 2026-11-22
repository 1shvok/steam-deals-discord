
import json
import os
import tempfile


def save_json_atomic(file_path, data):
    """
    Save JSON data safely by writing to a temporary file
    and atomically replacing the destination file.
    """

    directory = os.path.dirname(os.path.abspath(file_path))
    filename = os.path.basename(file_path)

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False
        ) as temp_file:

            temp_path = temp_file.name

            json.dump(
                data,
                temp_file,
                indent=2,
                ensure_ascii=False
            )

            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, file_path)
        temp_path = None

    finally:
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
