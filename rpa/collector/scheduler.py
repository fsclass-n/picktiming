"""컨테이너용 스케줄러 (EC2 docker compose의 rpa 서비스)

매시 정각 가격 수집(COLLECT_ENABLED=true일 때만 — EC2 기본은 false, 실제 수집은 GitHub Actions 담당),
매일 03:00 재학습, 06:00 참가격, 매주 월 07:00 주간 리포트.
호스트 cron을 쓰는 경우 이 스케줄러 대신 deploy/crontab을 사용한다.
"""
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Config
from .jobs import run

log = logging.getLogger("scheduler")


def due_jobs(t: datetime, collect: bool = True) -> list[str]:
    """collect=False(COLLECT_ENABLED=false)면 외부 사이트 수집은 예약하지 않고 재학습·참가격·리포트만 실행"""
    jobs = []
    if t.minute == 0:
        if collect:
            jobs.append("collect")
        if t.hour == 3:
            jobs.append("train")
        if t.hour == 6:
            jobs.append("public")
        if t.hour == 7 and t.weekday() == 0:
            jobs.append("report")
    return jobs


def main() -> None:
    cfg = Config()
    done: set[str] = set()
    log.info("scheduler started (tz=%s, api=%s)", cfg.tz, cfg.api_base_url)
    while True:
        t = datetime.now(ZoneInfo(cfg.tz))
        for job in [j for j in due_jobs(t, collect=cfg.collect_enabled) if j in cfg.scheduled_jobs]:
            key = f"{job}-{t:%Y%m%d%H}"
            if key in done:
                continue
            done.add(key)
            try:
                log.info("%s 실행: %s", job, run(job, cfg))
            except Exception:  # 작업 하나가 실패해도 스케줄러는 계속 동작
                log.exception("%s 실패", job)
        if len(done) > 500:
            done = {k for k in done if k.endswith(f"{t:%Y%m%d%H}")}
        time.sleep(20)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    main()
