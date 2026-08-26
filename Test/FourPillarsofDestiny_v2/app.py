from cli import main
from logging_utils import LOGGER

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOGGER.warning("사용자가 실행을 중단했습니다.")
        raise
    except Exception:
        LOGGER.exception("프로그램이 처리되지 않은 오류로 종료되었습니다.")
        raise
