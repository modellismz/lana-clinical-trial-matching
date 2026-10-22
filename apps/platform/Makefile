PY := .venv/bin/python

.PHONY: setup data embed iris train export thailand patient-map eval eval-snapshot cron test serve static
setup:            ## python env + IRIS container
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && docker compose up -d
	@echo "IRIS: if the first connection says 'Password change required' run: make iris-unlock"
iris-unlock:
	printf 'do ##class(Security.Users).UnExpireUserPasswords("*")\nhalt\n' | docker exec -i lana-mvp-iris iris session IRIS -U %SYS
data:             ## real public data: cBioPortal cohorts, ClinicalTrials.gov trials, TREC pairs
	$(PY) pipeline/build_cohort.py && $(PY) pipeline/fetch_trials.py && $(PY) pipeline/fetch_trec.py
embed:            ## bge-m3 embeddings of every trial chunk, then load them into IRIS
	$(PY) pipeline/embed_trials.py && $(PY) pipeline/load_iris.py && $(PY) pipeline/build_trial_segments.py
train:            ## trial-fit (TREC) and biomarker-completion (real cohorts) models
	$(PY) pipeline/train_trial_fit.py && $(PY) pipeline/train_completion.py
export:           ## run the engine on the demo patients, write web/data
	$(PY) pipeline/export_demo.py && $(PY) pipeline/build_thailand.py && python3 pipeline/build_patient_map.py && $(PY) pipeline/eval_retrieval.py
patient-map:      ## home page: every cohort patient + similarity links -> web/data/patient_map.json (needs make data)
	python3 pipeline/build_patient_map.py
thailand:         ## province geometry + modelled (SIM) patient pools for the match page -> web/data/thailand.json
	python3 pipeline/build_thailand.py
eval:             ## golden-set evaluation of the retrieval stage -> web/data/evaluation.json + data/eval_runs.jsonl; exit 1 on a recall@40 drop > 0.05
	$(PY) pipeline/eval_retrieval.py
eval-snapshot:    ## same from the exported web/data only (final top 12; no IRIS, no model)
	python3 pipeline/eval_retrieval.py --snapshot
cron:             ## crontab lines for pipeline/eval_schedule.json (paste into `crontab -e`)
	@python3 -c "import json;s=json.load(open('pipeline/eval_schedule.json'));print('CRON_TZ='+s['timezone']);[print(f\"{j['cron']}  cd $(CURDIR) && {j['target']} >> data/cron.log 2>&1   # {j['name']}\") for j in s['jobs'] if j['cron']]"
test:
	$(PY) -m pytest -q tests
serve:            ## live API + static site on http://localhost:8010
	$(PY) -m uvicorn server.app:app --port 8010
static:           ## static site only, no Python models needed
	cd web && python3 -m http.server 8011
