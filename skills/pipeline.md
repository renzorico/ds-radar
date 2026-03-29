# MODE: pipeline

## Purpose
Orchestrate the full flow for one or more offers: evaluate → pdf → track.

## Inputs
- One or more raw offer JSON paths (evals/<date>/<company>-<role>.json)
- profile/profile.yaml (for grade gate)

## Outputs
- Delegates outputs to evaluator, pdf, and tracker modes
- tracker.tsv — updated with new rows

## Tools allowed
- filesystem read
- filesystem write
- anthropic API
- shell

## Steps
1. TODO
2. TODO
3. TODO
