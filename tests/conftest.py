import os
import sys
from pathlib import Path

# 테스트는 환경 파일 없이도 돌아야 한다 (config 가 .env.dev 를 읽지만 없어도 기본값으로 동작)
os.environ.setdefault("APP_ENV", "dev")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.taxonomy import dictionary  # noqa: E402


@pytest.fixture(scope="session")
def d():
    return dictionary.from_seed()
