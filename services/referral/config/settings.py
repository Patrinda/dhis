from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parents[1] / "shared"))

from dhis_common.settings_base import build  # noqa: E402

globals().update(build(
    service="referral",
    service_dir=HERE,
    apps=["transfers"],
    db_name="db_refer",
))
