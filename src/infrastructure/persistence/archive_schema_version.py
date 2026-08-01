ARCHIVE_SCHEMA_VERSION = 2

# Version 1 predates per-slot retries. Those archives stay readable, and a
# version-1 document is re-encoded as version 1 when its canonical form is
# verified, so existing files keep validating without rewriting them.
SUPPORTED_ARCHIVE_SCHEMA_VERSIONS = (1, 2)

RETRY_SCHEMA_VERSION = 2
