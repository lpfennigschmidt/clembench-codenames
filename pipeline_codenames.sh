#!/bin/bash
# Usage: ./pipeline_codenames.sh
# Preparation: ./setup.sh

# for huggingface models
source venv_hf/bin/activate
source prepare_path.sh

rm -rf ./results/*

echo
echo "==================================================="
echo "PIPELINE: Starting"
echo "==================================================="
echo
game_runs_gpu_server=(
  # Same-team codenames
  #"codenames mock"
  # Huggingface models
  #"codenames openchat_3.5"
  #"codenames sheep-duck-llama-2-13b"
  "codenames CodeLlama-34b-Instruct-hf"
  "codenames Yi-34B-Chat"
  "codenames mistral-medium"
  # Open.AI models
  "codenames gpt-3.5-turbo-0613"
  #"codenames gpt-4-0613"
  #"codenames gpt-4-1106-preview"
  # Multi-player codenames
)

game_runs=(
  #"codenames fsc-openchat-3.5-0106"
  #"codenames fsc-codellama-34b-instruct"
  "codenames mock"
)

# game_runs=game_runs_api

total_runs=${#game_runs[@]}
echo "Number of benchmark runs: $total_runs"
current_runs=1
for run_args in "${game_runs[@]}"; do
  echo "Run $current_runs of $total_runs: $run_args"
  bash -c "./run.sh ${run_args}"
  ((current_runs++))
done

echo "Run scoring"
python3 scripts/cli.py score -g codenames

echo "Run evaluation"
python3 evaluation/codenames_eval.py models
python3 evaluation/codenames_eval.py errors
python3 evaluation/codenames_eval.py experiments

echo "==================================================="
echo "PIPELINE: Finished"
echo "==================================================="