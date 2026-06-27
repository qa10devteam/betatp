.PHONY: test backtest serve install lint coverage

install:
	pip install -r requirements.txt

test:
	python3 -m pytest tests/ -v --tb=short

coverage:
	python3 -m pytest tests/ --cov=. --cov-report=term-missing -q

backtest:
	python3 scripts/backtest_vX.py --version 14 --edge 0.15

serve:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

daily:
	python3 scripts/run_daily_pipeline.py --edge 0.15 --max-picks 3

lint:
	python3 -m py_compile api/main.py engine/coupon.py engine/coupon_system.py value/alerts.py
	@echo "Lint OK"
