"""
CityMind - Challenge 3: Ambulance Placement
============================================
Technique: Genetic Algorithm (GA)
Author: Group Project - BS Computer Science

OBJECTIVE:
  Place 3 ambulances on active city nodes such that the WORST-CASE
  response time is minimised (minimax: the citizen furthest from any
  ambulance should be as close as possible).

SPEED OPTIMISATION — DISTANCE MATRIX:
  The bottleneck in naive GA is calling Dijkstra for every
  (node, chromosome) pair each generation.
  On a 10x10 grid: 100 nodes x 30 pop x 80 gens = 240,000 calls.
  Instead we run N Dijkstra searches ONCE before the GA starts,
  building a full N x N distance matrix.
  Fitness then becomes O(N) table lookups — essentially free.

GA COMPONENTS:
  Chromosome  — list of 3 distinct node IDs (one per ambulance)
  Population  — POPULATION_SIZE chromosomes
  Fitness     — -max(dist[node][nearest_ambulance]) over all nodes
  Selection   — tournament selection (TOURNAMENT_K=4)
  Crossover   — single-point, duplicates repaired
  Mutation    — per-gene with MUTATION_RATE probability
  Elitism     — ELITE_COUNT top chromosomes copied unchanged
  Termination — MAX_GENERATIONS or PATIENCE gens with no improvement
"""

import random
import heapq

# ── GA Hyperparameters ────────────────────────────────────────────
NUM_AMBULANCES  = 3
POPULATION_SIZE = 40
MAX_GENERATIONS = 120
MUTATION_RATE   = 0.20
TOURNAMENT_K    = 4
PATIENCE        = 25
ELITE_COUNT     = 3


# ── Full Dijkstra from one source to ALL reachable nodes ──────────
def dijkstra_all(city, source: int, active_set: set) -> dict:
    """
    Single-source Dijkstra returning {node_id: distance} for all
    reachable active nodes.  Called N times to build the matrix.
    Uses city.roads with cost + risk_index if available, else hop count.
    """
    dist = {source: 0.0}
    heap = [(0.0, source)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, float("inf")):
            continue
        if city.roads:
            for nb, edge in city.roads.get(node, {}).items():
                if nb not in active_set:
                    continue
                if isinstance(edge, dict):
                    if edge.get("blocked", False):
                        continue
                    base = edge.get("cost", 1.0)
                    if "base_cost" in edge:
                        nd = d + base
                    else:
                        risk = getattr(city, "risk_index", {}).get(nb, 0.0)
                        nd = d + base * (1.0 + risk)
                else:
                    base = float(edge)
                    risk = getattr(city, "risk_index", {}).get(nb, 0.0)
                    nd = d + base * (1.0 + risk)
                if nd < dist.get(nb, float("inf")):
                    dist[nb] = nd
                    heapq.heappush(heap, (nd, nb))
        else:
            # Fallback: BFS hop count via city.neighbors
            for nb in city.neighbors(node):
                if nb not in active_set:
                    continue
                nd = d + 1.0
                if nd < dist.get(nb, float("inf")):
                    dist[nb] = nd
                    heapq.heappush(heap, (nd, nb))
    return dist


def build_distance_matrix(city, active_nodes: list) -> list:
    """
    Build full N x N distance matrix using N Dijkstra runs.
    Returns dist_matrix[i][j] = distance from active_nodes[i] to active_nodes[j].
    O(N * (E log V)) — done ONCE before GA starts.
    """
    n          = len(active_nodes)
    idx        = {nid: i for i, nid in enumerate(active_nodes)}
    active_set = set(active_nodes)
    matrix     = [[float("inf")] * n for _ in range(n)]
    for i, src in enumerate(active_nodes):
        dists = dijkstra_all(city, src, active_set)
        for j, dst in enumerate(active_nodes):
            matrix[i][j] = dists.get(dst, float("inf"))
    return matrix


# ── Fitness using precomputed matrix ──────────────────────────────
def fitness_matrix(chromosome_idx: list, matrix: list, n: int) -> float:
    """
    O(N * k) lookup — no Dijkstra needed.
    chromosome_idx: list of integer indices into active_nodes (not node IDs).
    Returns negative worst-case distance (GA maximises, we minimise).
    """
    worst = 0.0
    for i in range(n):
        nearest = min(matrix[i][j] for j in chromosome_idx)
        if nearest > worst:
            worst = nearest
    return -worst


# ── GA operators ──────────────────────────────────────────────────
def random_chromosome(n: int) -> list:
    """Random list of NUM_AMBULANCES distinct indices into active_nodes."""
    return random.sample(range(n), NUM_AMBULANCES)


def tournament_select(pop: list, fits: list) -> list:
    candidates = random.sample(range(len(pop)), min(TOURNAMENT_K, len(pop)))
    return pop[max(candidates, key=lambda i: fits[i])][:]


def crossover(p1: list, p2: list, n: int) -> list:
    pt    = random.randint(1, NUM_AMBULANCES - 1)
    child = p1[:pt] + p2[pt:]
    seen  = set()
    result = []
    for g in child:
        if g not in seen:
            seen.add(g); result.append(g)
    unused = [x for x in range(n) if x not in seen]
    random.shuffle(unused)
    while len(result) < NUM_AMBULANCES:
        result.append(unused.pop())
    return result


def mutate(chromosome: list, n: int) -> list:
    chrom = chromosome[:]
    for i in range(NUM_AMBULANCES):
        if random.random() < MUTATION_RATE:
            used = set(chrom); used.discard(chrom[i])
            choices = [x for x in range(n) if x not in used]
            if choices:
                chrom[i] = random.choice(choices)
    return chrom


# ── Main GA solver ────────────────────────────────────────────────
class AmbulancePlacementGA:
    def __init__(self, city, callback=None):
        self.city             = city
        self.callback         = callback
        self.best_placement   = None   # list of node IDs
        self.best_worst_case  = float("inf")
        self.history          = []
        self.generations_run  = 0
        self._active_nodes    = []
        self._matrix          = None

    def run(self) -> list:
        """
        Full GA pipeline.
        Step 1 — collect active nodes
        Step 2 — build distance matrix (one-time Dijkstra)
        Step 3 — evolve population
        Step 4 — return best placement as node IDs
        """
        city   = self.city
        active = [n for n in city.active_nodes
                  if city.assignment.get(n) is not None]
        self._active_nodes = active
        n = len(active)

        if n < NUM_AMBULANCES:
            self.best_placement  = active[:NUM_AMBULANCES]
            self.best_worst_case = 0.0
            return self.best_placement

        # Step 2 — precompute (this is the slow part, done once)
        if self.callback:
            self.callback(0, float("inf"))   # signal matrix build started
        self._matrix = build_distance_matrix(city, active)
        matrix = self._matrix

        # Step 3 — GA on indices
        pop  = [random_chromosome(n) for _ in range(POPULATION_SIZE)]
        fits = [fitness_matrix(c, matrix, n) for c in pop]

        best_fit   = max(fits)
        best_chrom = pop[fits.index(best_fit)][:]
        no_improve = 0

        for gen in range(MAX_GENERATIONS):
            self.generations_run = gen + 1

            elite_idx = sorted(range(len(fits)), key=lambda i: fits[i], reverse=True)
            new_pop   = [pop[i][:] for i in elite_idx[:ELITE_COUNT]]
            while len(new_pop) < POPULATION_SIZE:
                p1    = tournament_select(pop, fits)
                p2    = tournament_select(pop, fits)
                child = crossover(p1, p2, n)
                child = mutate(child, n)
                new_pop.append(child)

            pop  = new_pop
            fits = [fitness_matrix(c, matrix, n) for c in pop]

            gen_best = max(fits)
            self.history.append(-gen_best)

            if gen_best > best_fit:
                best_fit   = gen_best
                best_chrom = pop[fits.index(gen_best)][:]
                no_improve = 0
            else:
                no_improve += 1

            if self.callback:
                self.callback(gen + 1, -gen_best)

            if no_improve >= PATIENCE:
                break

        # Step 4 — convert index chromosome back to node IDs
        self.best_placement  = [active[i] for i in best_chrom]
        self.best_worst_case = -best_fit
        return self.best_placement

    def coverage_report(self) -> list:
        """
        Returns list of (node_id, nearest_ambulance_id, distance).
        Uses precomputed matrix — instant after run() completes.
        """
        if not self.best_placement or self._matrix is None:
            return []
        active  = self._active_nodes
        matrix  = self._matrix
        idx     = {nid: i for i, nid in enumerate(active)}
        amb_idx = [idx[nid] for nid in self.best_placement if nid in idx]
        result  = []
        for i, nid in enumerate(active):
            if not amb_idx:
                break
            nearest_j = min(amb_idx, key=lambda j: matrix[i][j])
            dist      = matrix[i][nearest_j]
            result.append((nid, active[nearest_j], dist))
        return result


# ── Standalone entry point ────────────────────────────────────────
def run_challenge3(city, callback=None):
    ga = AmbulancePlacementGA(city, callback=callback)
    ga.run()
    return ga


if __name__ == "__main__":
    import sys, os, io
    sys.path.insert(0, os.path.dirname(__file__))
    from challenge1 import CityLayoutManager
    from contextlib import redirect_stdout

    print("Running Challenge 1...")
    tc  = {"Residential":6,"Hospital":2,"School":2,
           "Industrial":2,"PowerPlant":2,"AmbulanceDepot":1}
    mgr = CityLayoutManager()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mgr.initialize(5, 5, sum(tc.values()), tc, 300, 500)

    print("Running Challenge 3 GA (with precomputed matrix)...")
    def progress(gen, worst):
        if gen == 0:
            print("  Building distance matrix...")
        elif gen % 20 == 0:
            print(f"  Gen {gen}: worst-dist={worst:.2f}")

    ga = run_challenge3(mgr.city, callback=progress)
    print(f"Best: {[mgr.city.coords(n) for n in ga.best_placement]}")
    print(f"Worst-case dist: {ga.best_worst_case:.2f}")
    print(f"Generations: {ga.generations_run}")

    