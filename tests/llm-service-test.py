import argparse
import asyncio
import random
import statistics
import sys
import time
from typing import Dict, List, Optional, Tuple

from llm_client.llm_client import llm, llm_async

from config.conf_manager import setup_logging
import logging
setup_logging()
logger = logging.getLogger(__name__)

MODEL_SIZES: Dict[str, float] = {
    "qwen2.5:32b-instruct-q4_K_M": 19,
    "llama3.1:8b-instruct-q8_0": 8.5,
    "mistral:7b-instruct-q8_0": 7.7,
    "qwen2.5:7b-instruct-q8_0": 8.1,
    "qwen2.5-coder:14b-instruct-q8_0": 15,
    "command-r:35b-v0.1-q4_K_M": 21,
    "huihui_ai/gemma-4-abliterated:31b": 19,
    "huihui_ai/deepseek-r1-abliterated:32b": 19,
    "huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q6_K": 12,
    "codestral:22b-v0.1-q4_K_M": 13,
    "mistral-small:22b-instruct-2409-q6_K": 18,
    "glm-4.7-flash:latest": 19,
    "deepseek-coder-v2:16b": 8.9,
    "deepseek-r1:32b": 19,
    "deepseek-r1:70b": 42,
    "gemma4:31b": 19,
    "qwen2.5-coder:7b": 4.7,
    "ministral-3:14b": 9.1,
    "qwen2.5-coder:3b": 1.9,
    "qwen2.5-coder:32b": 19,
    "qwen3-coder:30b": 18,
    "qwen3.6:35b": 22,
    "qwen3.8:27b": 17,
    "qwen2.5:3b": 1.9,
    "qwen2.5:7b": 4.7,
    "dolphin-mixtral:latest": 26,
    "qwen2.5:32b": 19,
}

def categorize_model_size(size_gb: float) -> str:
    if size_gb < 5:
        return "small"
    elif size_gb <= 14:
        return "medium"
    else:
        return "large"

MODEL_BY_SIZE: Dict[str, List[str]] = {"small": [], "medium": [], "large": []}
for name, size in MODEL_SIZES.items():
    cat = categorize_model_size(size)
    MODEL_BY_SIZE[cat].append(name)

PROMPTS: Dict[str, str] = {
    "small": "Say hello in one sentence.",
    "medium": "Explain what artificial intelligence is in 3 paragraphs.",
    "complex": (
        "Write a detailed analysis of the impacts of climate change on the global economy, "
        "including short, medium, and long-term perspectives. Structure your response with "
        "an introduction, multiple sections, and a conclusion."
    ),
}

def parse_args():
    parser = argparse.ArgumentParser(description="LLM Benchmark")
    parser.add_argument(
        "--stress", action="store_true",
        help="Stress test: N concurrent calls, 66/22/11 random model size and prompt complexity"
    )
    parser.add_argument(
        "--small", action="store_true",
        help="Sequential benchmark on SMALL prompt for ALL models"
    )
    parser.add_argument(
        "--medium", action="store_true",
        help="Sequential benchmark on MEDIUM prompt for ALL models"
    )
    parser.add_argument(
        "--large", action="store_true",
        help="Sequential benchmark on COMPLEX prompt for ALL models"
    )
    parser.add_argument(
        "-n", type=int, default=None,
        help="Number of calls per model (default: 10 for stress, 1 for small/medium/large)"
    )
    return parser.parse_args()

def _inference_sync(model: str, prompt: str) -> float:
    start = time.perf_counter()
    llm.llm_call('', prompt, model)
    return time.perf_counter() - start

async def _inference_async(model: str, prompt: str) -> float:
    start = time.perf_counter()
    await llm_async.llm_call('', prompt, model=model)
    return time.perf_counter() - start

def _inference_sync_with_response(model: str, prompt: str, label: str) -> float:
    start = time.perf_counter()
    response = llm.llm_call('', prompt, model=model)
    elapsed = time.perf_counter() - start
    response_str = str(response)
    logger.info(f"    [{label}] RESPONSE: {repr(response_str)}")
    return elapsed

async def _inference_async_with_response(model: str, prompt: str, label: str) -> float:
    start = time.perf_counter()
    response = await llm_async.llm_call('', prompt, model=model)
    elapsed = time.perf_counter() - start
    response_str = str(response)
    logger.info(f"    [{label}] RESPONSE: {repr(response_str)}")
    return elapsed

def weighted_choice(weights: Dict[str, float]) -> str:
    items = list(weights.items())
    total = sum(w for _, w in items)
    r = random.uniform(0, total)
    cumulative = 0.0
    for key, weight in items:
        cumulative += weight
        if r <= cumulative:
            return key
    return items[-1][0]

def random_model_and_prompt() -> Tuple[str, str]:
    size_key = weighted_choice({"small": 80, "medium": 15, "large": 5})
    model = random.choice(MODEL_BY_SIZE[size_key])
    prompt_key = weighted_choice({"small": 80, "medium": 15, "complex": 5})
    return model, prompt_key

def compute_stats(times: List[float]) -> Dict[str, float]:
    if not times:
        return {"avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "avg": statistics.mean(times),
        "min": min(times),
        "max": max(times),
    }

def compute_score(results: Dict) -> float:
    avg_times = []
    for key in ["small", "medium", "complex"]:
        values = results.get(key, [])
        if values:
            avg_times.append(statistics.mean(values))
    return statistics.mean(avg_times) if avg_times else 0.0

async def run_normal_test():
    logger.info("=" * 60)
    logger.info("MODE NORMAL - Basic sync/async test")
    logger.info("=" * 60)

    default_model = "qwen2.5:3b"
    results: Dict[str, float] = {}

    for name, prompt in PROMPTS.items():
        t_sync = _inference_sync_with_response(default_model, prompt, f"sync {name}")
        logger.info(f"  sync  {name:8s} : {t_sync:.4f}s")
        results[f"{name}_sync"] = t_sync

        t_async = await _inference_async_with_response(default_model, prompt, f"async {name}")
        logger.info(f"  async {name:8s} : {t_async:.4f}s")
        results[f"{name}_async"] = t_async

    logger.info("\nTest normal completed.")
    return results

async def run_stress_test(n: int):
    logger.info("=" * 60)
    logger.info(f"MODE STRESS - {n} parallel calls (80/15/5 model size and prompt)")
    logger.info("=" * 60)

    async def task_with_response(idx: int, model: str, prompt_key: str):
        start = time.perf_counter()
        response = await llm_async.llm_call('', PROMPTS[prompt_key], model=model)
        elapsed = time.perf_counter() - start

        response_str = str(response)
        truncated = response_str[:300] + "..." if len(response_str) > 300 else response_str
        logger.info(f"  [{idx:2d}] model={model:50s} prompt={prompt_key:8s} "
              f"time={elapsed:.4f}s  response={repr(truncated)}")

        return {
            'model': model,
            'prompt': prompt_key,
            'time': elapsed,
            'response': response_str,
        }

    tasks = []
    for i in range(n):
        model, prompt_key = random_model_and_prompt()
        tasks.append(task_with_response(i, model, prompt_key))

    results = await asyncio.gather(*tasks)
    return results

async def run_sequential_benchmark(size_filter: str, n: int):
    logger.info("=" * 60)
    logger.info(f"MODE SEQUENTIAL BENCHMARK - size={size_filter}  n={n} runs per prompt per model")
    logger.info("=" * 60)

    models_to_test = MODEL_BY_SIZE[size_filter]
    logger.info(f"Models to test ({len(models_to_test)}):")
    for m in sorted(models_to_test, key=lambda x: MODEL_SIZES[x]):
        logger.info(f"  {m} ({MODEL_SIZES[m]:.1f}GB)")

    results_per_model: Dict[str, Dict[str, List[float]]] = {}
    warmup_times: Dict[str, float] = {}

    for model in sorted(models_to_test, key=lambda m: MODEL_SIZES[m]):
        results_per_model[model] = {}

        logger.info(f"  {model:50s}  FIRST LOAD (cold start, not counted)...")
        first_load_start = time.perf_counter()
        _inference_sync(model, PROMPTS["small"])
        first_load_time = time.perf_counter() - first_load_start
        warmup_times[model] = first_load_time
        logger.info(f"  {model:50s}  first load: {first_load_time:.4f}s")

        for pkey, prompt in PROMPTS.items():
            times = []
            for i in range(n):
                t = _inference_sync(model, prompt)
                times.append(t)
                logger.info(f"  {model:50s}  {pkey:8s}  run {i+1}/{n} : {t:.4f}s")
            results_per_model[model][pkey] = times

    logger.info("\nSequential benchmark completed.")
    return results_per_model, warmup_times

def print_normal_results(results: Dict[str, float]):
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS - Normal mode")
    logger.info("=" * 60)
    for key, value in results.items():
        logger.info(f"  {key:20s} : {value:.4f}s")

def print_stress_results(results: list):
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS - Stress mode")
    logger.info("=" * 60)

    all_times = [r['time'] for r in results]

    model_times: Dict[str, List[float]] = {}
    for r in results:
        model_times.setdefault(r['model'], []).append(r['time'])

    prompt_times: Dict[str, List[float]] = {}
    for r in results:
        prompt_times.setdefault(r['prompt'], []).append(r['time'])

    logger.info(f"\nTotal calls: {len(results)}")
    logger.info(f"Global avg:  {statistics.mean(all_times):.4f}s")
    logger.info(f"Global min:  {min(all_times):.4f}s")
    logger.info(f"Global max:  {max(all_times):.4f}s")
    if len(all_times) > 1:
        logger.info(f"Global stdev: {statistics.stdev(all_times):.4f}s")

    logger.info("\nPer-model stats:")
    model_avgs = [(m, statistics.mean(t), min(t), max(t), len(t))
                  for m, t in sorted(model_times.items(), key=lambda x: statistics.mean(x[1]))]
    for model, avg, mn, mx, count in model_avgs:
        logger.info(f"  {model:50s}  avg: {avg:7.4f}s  min: {mn:7.4f}s  max: {mx:7.4f}s  count: {count}")

    logger.info("\nPer-prompt stats:")
    for prompt in ['small', 'medium', 'complex']:
        if prompt in prompt_times:
            t = prompt_times[prompt]
            avg = statistics.mean(t)
            mn = min(t)
            mx = max(t)
            logger.info(f"  {prompt:8s}  avg: {avg:7.4f}s  min: {mn:7.4f}s  max: {mx:7.4f}s  count: {len(t)}")
        else:
            logger.info(f"  {prompt:8s}  (no calls)")

    error_count = sum(1 for r in results if not r['response'] or r['response'].strip() == '')
    if error_count > 0:
        logger.info(f"\nWARNING: {error_count}/{len(results)} responses are empty or None!")
        logger.info("This indicates a possible bug in llm_async.generate().")

def print_sequential_results(results_per_model: Dict[str, Dict[str, List[float]]],
                              warmup_times: Dict[str, float],
                              size_filter: str):
    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS - Sequential benchmark (size={size_filter})")
    logger.info("=" * 60)

    logger.info(f"\n--- Per-model stats: avg/min/max for small/medium/complex prompts ---")
    logger.info(f"  (warmup not counted in stats below)")
    model_avgs = []
    for model, prompt_data in results_per_model.items():
        all_model_times = []
        for t in prompt_data.values():
            all_model_times.extend(t)
        overall_avg = statistics.mean(all_model_times)
        model_avgs.append((model, MODEL_SIZES.get(model, 0), overall_avg, prompt_data))

    model_avgs.sort(key=lambda x: x[2])

    rank = 1
    for model, size, overall_avg, prompt_data in model_avgs:
        first_load = warmup_times.get(model, 0)
        logger.info(f"\n  #{rank} {model} ({size:.1f}GB) - overall avg: {overall_avg:.4f}s")
        logger.info(f"       first_load: {first_load:.4f}s")
        for pkey in ["small", "medium", "complex"]:
            times = prompt_data.get(pkey, [])
            if times:
                avg = statistics.mean(times)
                mn = min(times)
                mx = max(times)
                logger.info(f"       {pkey:8s}  avg: {avg:.4f}s  min: {mn:.4f}s  max: {mx:.4f}s")
        rank += 1

    logger.info(f"\n--- Global stats per prompt (all {size_filter} models) ---")
    logger.info(f"  (warmup not counted)")
    for pkey in ["small", "medium", "complex"]:
        all_times = []
        for model_data in results_per_model.values():
            all_times.extend(model_data.get(pkey, []))
        if all_times:
            avg = statistics.mean(all_times)
            mn = min(all_times)
            mx = max(all_times)
            logger.info(f"  {pkey:8s}  avg: {avg:.4f}s  min: {mn:.4f}s  max: {mx:.4f}s  total runs: {len(all_times)}")

    logger.info(f"\n--- First load times (warmup) ---")
    for model, load_time in sorted(warmup_times.items(), key=lambda x: x[1]):
        logger.info(f"  {model:50s}  {load_time:.4f}s")

async def main():
    args = parse_args()

    mode_flags = [args.stress, args.small, args.medium, args.large]
    if sum(mode_flags) > 1:
        logger.info("Error: only one mode allowed at a time (--stress, --small, --medium, --large)")
        sys.exit(1)

    if args.stress:
        n = args.n if args.n is not None else 10
        results = await run_stress_test(n)
        print_stress_results(results)

    elif args.small:
        n = args.n if args.n is not None else 1
        results, warmup_times = await run_sequential_benchmark("small", n)
        print_sequential_results(results, warmup_times, "small")

    elif args.medium:
        n = args.n if args.n is not None else 1
        results, warmup_times = await run_sequential_benchmark("medium", n)
        print_sequential_results(results, warmup_times, "medium")

    elif args.large:
        n = args.n if args.n is not None else 1
        results, warmup_times = await run_sequential_benchmark("large", n)
        print_sequential_results(results, warmup_times, "large")

    else:
        results = await run_normal_test()
        print_normal_results(results)

if __name__ == "__main__":
    asyncio.run(main())

