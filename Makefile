# Pukara evaluation pipeline.
# `make eval` regenerates docs/metrics.md from eval/results/*.json.

SEED ?= 42
BOOTSTRAP ?= 1000

.PHONY: eval eval-full eval-regex generate-metrics clean

## Full reproducible pipeline (the real system: BERT + regex).
eval: eval-full generate-metrics

eval-full:
	python -m eval.meddocan --corpus data/meddocan/corpus --mode combined \
		--out eval/results/meddocan.json --bootstrap $(BOOTSTRAP) --seed $(SEED)
	python -m eval.promptbench --mode combined \
		--out eval/results/promptbench.json --seed $(SEED)
	python -m eval.utility --corpus data/meddocan/corpus --mode combined \
		--out eval/results/utility.json
	python -m eval.cost --corpus data/meddocan/corpus --mode combined \
		--out eval/results/cost.json

## Regex-only ablation (no model needed).
eval-regex:
	python -m eval.meddocan --corpus data/meddocan/corpus --mode regex \
		--out eval/results/meddocan-regex.json --bootstrap $(BOOTSTRAP) \
		--seed $(SEED)

generate-metrics:
	python -m eval.generate_metrics

clean:
	rm -f eval/results/*.json docs/metrics.md

