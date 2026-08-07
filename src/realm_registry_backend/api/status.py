import sys
from api.registry import count_registered_realms


def get_status() -> dict:
    version = "VERSION_PLACEHOLDER"
    commit = "COMMIT_HASH_PLACEHOLDER"
    commit_datetime = "COMMIT_DATETIME_PLACEHOLDER"
    return {
        "version": version,
        "commit": commit,
        "commit_datetime": commit_datetime,
        "status": "ok",
        "realms_count": count_registered_realms(),
        "dependencies": [
            "ic-basilisk==BASILISK_VERSION_PLACEHOLDER",
            "ic-python-db==IC_PYTHON_DB_VERSION_PLACEHOLDER",
            "ic-python-logging==IC_PYTHON_LOGGING_VERSION_PLACEHOLDER",
        ],
        "python_version": sys.version,
    }
