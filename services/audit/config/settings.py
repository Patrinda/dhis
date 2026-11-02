from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parents[1] / "shared"))

from dhis_common.settings_base import build  # noqa: E402

globals().update(build(
    service="audit",
    service_dir=HERE,
    apps=["ledger"],
    db_name="db_audit",
    extra={"EVENT_HANDLER": "ledger.handlers.handle"},
))
