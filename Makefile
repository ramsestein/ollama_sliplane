# Pukara evaluation pipeline.
# `make eval` regenerates docs/metrics.md from eval/results/*.json.

SEED ?= 42
BOOTSTRAP ?= 1000

.PHONY: eval eval-regex eval-bert generate-metrics clean

## Full reproducible pipeline (regex baseline; BERT needs the gated model).
eval: eval-regex generate-metrics

eval-regex:
	python -m eval.meddocan --corpus data/meddocan/corpus --mode regex \
		--out eval/results/meddocan.json --bootstrap $(BOOTSTRAP) --seed $(SEED)
	python -m eval.promptbench --mode regex --out eval/results/promptbench.json \
		--seed $(SEED)
	python -m eval.utility --corpus data/meddocan/corpus \
		--out eval/results/utility.json
	python -m eval.cost --corpus data/meddocan/corpus \
		--out eval/results/cost.json

## BERT/combined intrinsic eval (TODO: requires the gated model under models/).
eval-bert:
	python -m eval.meddocan --corpus data/meddocan/corpus --mode combined \
		--out eval/results/meddocan-combined.json --bootstrap $(BOOTSTRAP) \
		--seed $(SEED)

generate-metrics:
	python -m eval.generate_metrics

clean:
	rm -f eval/results/*.json docs/metrics.md
