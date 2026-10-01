from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Literal

from quantum_economic_auditor.models.state import OptimizationResult

OptimizerKind = Literal["simulated_annealing", "differential_evolution", "genetic_algorithm", "hill_climbing", "random_search"]


@dataclass
class ClassicalOptimizerConfig:
    iterations: int = 50
    seed: int = 0
    optimizer_kind: OptimizerKind = "simulated_annealing"
    temperature: float = 1.0
    mutation_rate: float = 0.1
    population_size: int = 12


class ClassicalOptimizer:
    """Interchangeable classical optimizer implementation.

    The optimizer interface is shared across all classical strategies so the comparison
    engine can swap algorithms without changing the surrounding pipeline.
    """

    def __init__(self, config: ClassicalOptimizerConfig | None = None) -> None:
        self.config = config or ClassicalOptimizerConfig()
        random.seed(self.config.seed)

    def optimize(
        self,
        objective_fn: Callable[[dict[str, float]], float],
        initial_state: dict[str, float],
    ) -> OptimizationResult:
        start = time.perf_counter()

        if self.config.optimizer_kind == "simulated_annealing":
            outcome = self._simulated_annealing(objective_fn, initial_state)
        elif self.config.optimizer_kind == "differential_evolution":
            outcome = self._differential_evolution(objective_fn, initial_state)
        elif self.config.optimizer_kind == "genetic_algorithm":
            outcome = self._genetic_algorithm(objective_fn, initial_state)
        elif self.config.optimizer_kind == "hill_climbing":
            outcome = self._hill_climbing(objective_fn, initial_state)
        else:
            outcome = self._random_search(objective_fn, initial_state)

        elapsed = time.perf_counter() - start
        outcome.execution_time_seconds = elapsed
        outcome.optimizer_name = self.config.optimizer_kind
        return outcome

    def _simulated_annealing(
        self,
        objective_fn: Callable[[dict[str, float]], float],
        initial_state: dict[str, float],
    ) -> OptimizationResult:
        best_state = dict(initial_state)
        best_score = objective_fn(best_state)
        current_state = dict(initial_state)
        current_score = best_score
        temperature = self.config.temperature

        for _ in range(self.config.iterations):
            candidate = {
                key: value + random.uniform(-1.0, 1.0) * temperature
                for key, value in current_state.items()
            }
            candidate_score = objective_fn(candidate)
            if candidate_score > current_score or random.random() < 1.0 / (1.0 + temperature):
                current_state = candidate
                current_score = candidate_score
            if candidate_score > best_score:
                best_state = candidate
                best_score = candidate_score
            temperature *= 0.95

        return self._result_from_state(best_state, best_score, iterations=self.config.iterations)

    def _differential_evolution(
        self,
        objective_fn: Callable[[dict[str, float]], float],
        initial_state: dict[str, float],
    ) -> OptimizationResult:
        population = [
            {key: value + random.uniform(-5.0, 5.0) for key, value in initial_state.items()}
            for _ in range(self.config.population_size)
        ]
        best_state = dict(initial_state)
        best_score = objective_fn(best_state)

        for _ in range(self.config.iterations):
            for candidate in population:
                score = objective_fn(candidate)
                if score > best_score:
                    best_state = dict(candidate)
                    best_score = score
            population = [
                {
                    key: candidate[key] + random.uniform(-0.5, 0.5)
                    for key, value in candidate.items()
                    for candidate in [candidate]
                }
                for candidate in population
            ]

        return self._result_from_state(best_state, best_score, iterations=self.config.iterations)

    def _genetic_algorithm(
        self,
        objective_fn: Callable[[dict[str, float]], float],
        initial_state: dict[str, float],
    ) -> OptimizationResult:
        population = [
            {key: value + random.uniform(-3.0, 3.0) for key, value in initial_state.items()}
            for _ in range(self.config.population_size)
        ]
        best_state = dict(initial_state)
        best_score = objective_fn(best_state)

        for _ in range(self.config.iterations):
            scored = sorted(
                population,
                key=lambda candidate: objective_fn(candidate),
                reverse=True,
            )
            elites = scored[: max(1, self.config.population_size // 2)]
            best_state = dict(elites[0])
            best_score = objective_fn(best_state)
            population = [
                {
                    key: value + random.uniform(-2.0, 2.0) * self.config.mutation_rate
                    for key, value in random.choice(elites).items()
                }
                for _ in range(self.config.population_size)
            ]

        return self._result_from_state(best_state, best_score, iterations=self.config.iterations)

    def _hill_climbing(
        self,
        objective_fn: Callable[[dict[str, float]], float],
        initial_state: dict[str, float],
    ) -> OptimizationResult:
        best_state = dict(initial_state)
        best_score = objective_fn(best_state)

        for _ in range(self.config.iterations):
            candidate = {
                key: value + random.uniform(-1.0, 1.0)
                for key, value in best_state.items()
            }
            candidate_score = objective_fn(candidate)
            if candidate_score > best_score:
                best_state = candidate
                best_score = candidate_score

        return self._result_from_state(best_state, best_score, iterations=self.config.iterations)

    def _random_search(
        self,
        objective_fn: Callable[[dict[str, float]], float],
        initial_state: dict[str, float],
    ) -> OptimizationResult:
        best_state = dict(initial_state)
        best_score = objective_fn(best_state)

        for _ in range(self.config.iterations):
            candidate = {key: value + random.uniform(-10.0, 10.0) for key, value in initial_state.items()}
            candidate_score = objective_fn(candidate)
            if candidate_score > best_score:
                best_state = candidate
                best_score = candidate_score

        return self._result_from_state(best_state, best_score, iterations=self.config.iterations)

    def _result_from_state(
        self,
        state: dict[str, float],
        score: float,
        iterations: int,
    ) -> OptimizationResult:
        return OptimizationResult(
            optimizer_name=self.config.optimizer_kind,
            objective_score=score,
            profit_discovered=max(score, 0.0),
            constraint_violations=0,
            energy=-score,
            convergence=1.0 if score > 0 else 0.0,
            iterations=iterations,
            execution_time_seconds=0.0,
            memory_usage_mb=0.0,
            variables=state,
        )
