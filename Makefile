.PHONY: demo check replay bootstrap

demo:
	python3 -m http.server 8011 --bind 127.0.0.1 --directory apps/platform/web

check:
	python3 scripts/check_repository.py

replay:
	python3 benchmarks/replay.py

bootstrap:
	python3 benchmarks/replay.py --bootstrap
