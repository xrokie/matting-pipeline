from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from uuid import uuid4


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


class JobStore:
    def __init__(self):
        self._jobs = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)

    def submit(
        self,
        project_id,
        target,
        *args,
        initial_stage="queued",
        initial_message="任务已进入队列",
        running_stage="matanyone2",
        running_message="开始执行 MatAnyone2 video matting",
        **kwargs,
    ):
        job_id = f"job_{uuid4().hex[:16]}"
        job = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "queued",
            "stage": initial_stage,
            "progress": 0.0,
            "message": initial_message,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "result": None,
            "error": None,
        }

        with self._lock:
            self._jobs[job_id] = job

        self._executor.submit(
            self._run_job,
            job_id,
            target,
            running_stage,
            running_message,
            *args,
            **kwargs,
        )
        return self.get(job_id)

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return dict(job)

    def update(self, job_id, **updates):
        with self._lock:
            job = self._jobs[job_id]
            job.update(updates)
            job["updated_at"] = now_iso()
            return dict(job)

    def _run_job(self, job_id, target, running_stage, running_message, *args, **kwargs):
        self.update(
            job_id,
            status="running",
            stage=running_stage,
            progress=0.05,
            message=running_message,
        )

        try:
            result = target(job_id=job_id, *args, **kwargs)
        except Exception as exc:
            self.update(
                job_id,
                status="failed",
                stage="failed",
                progress=1.0,
                message="任务失败",
                error={
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            return

        self.update(
            job_id,
            status="succeeded",
            stage="succeeded",
            progress=1.0,
            message="任务完成",
            result=result,
        )


jobs = JobStore()
