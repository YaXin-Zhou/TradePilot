"""v1.3 U1: 调度器启停测试"""
import sys, os, pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScheduler:
    def test_scheduler_module_imports(self):
        from tasks.scheduler import start_scheduler, stop_scheduler
        assert callable(start_scheduler)
        assert callable(stop_scheduler)

    @pytest.mark.asyncio
    async def test_scheduler_jobs_registered(self):
        from tasks.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
        try:
            from tasks.scheduler import scheduler
            jobs = scheduler.get_jobs()
            assert len(jobs) >= 4  # 至少 4 类定时任务
        finally:
            stop_scheduler()
