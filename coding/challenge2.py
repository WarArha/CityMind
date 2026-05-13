"""
CityMind - Challenge 2: Road Network Optimization
==================================================
Technique: Kruskal's MST + Second-Path Augmentation (Dijkstra's)
Author: Group Project - BS Computer Science

HOW IT WORKS:
- Kruskal's Algorithm builds the Minimum Spanning Tree (MST)
  connecting all active nodes at minimum total road cost
- Second-Path Augmentation ensures two completely independent
  routes exist between the Primary Hospital and Ambulance Depot
- All results are written back to the shared CityGraph
- Roads NOT in MST remain available (adjacency preserved),
  MST edges are just marked as "optimal built roads"
- Blocked roads are PRESERVED across rebuilds: if a road was
  blocked before Build Roads is clicked again, it stays blocked.
"""

import heapq
from collections import defaultdict


# ─────────────────────────────────────────────
#  UNION-FIND (Disjoint Set Union)
#  Required by Kruskal's to detect cycles
# ─────────────────────────────────────────────
class UnionFind:
    """
    Union-Find with path compression and union by rank.
    Used by Kruskal's to check if adding an edge creates a cycle.

    VIVA EXPLANATION:
    - find(x): returns the root of x's component (with path compression)
    - union(x, y): merges two components, returns False if already same (cycle)
    """

    def __init__(self, nodes: list):
        self.parent = {n: n for n in nodes}
        self.rank   = {n: 0  for n in nodes}

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y) -> bool:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        return True

    def connected(self, x, y) -> bool:
        return self.find(x) == self.find(y)


# ─────────────────────────────────────────────
#  DIJKSTRA'S SHORTEST PATH
#  Used in Second-Path Augmentation step
# ─────────────────────────────────────────────
def dijkstra(graph: dict, start: int, end: int, blocked_edges: set = None) -> list:
    """
    Find shortest path from start to end in graph.
    graph format: {node: {neighbor: cost, ...}, ...}
    blocked_edges: set of frozenset({u, v}) pairs to treat as impassable

    Returns list of node IDs forming the path, or [] if no path exists.

    VIVA EXPLANATION:
    - Uses a min-heap (priority queue) to always expand the cheapest node first
    - Guarantees shortest path in graphs with non-negative edge weights
    - We use it here (not A*) because we have no spatial heuristic at this stage;
      A* is reserved for Challenge 4 where real-time recalculation is needed
    """
    if blocked_edges is None:
        blocked_edges = set()

    dist    = {start: 0.0}
    prev    = {start: None}
    heap    = [(0.0, start)]
    visited = set()

    while heap:
        cost, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == end:
            break
        for nb, edge_data in graph.get(node, {}).items():
            if frozenset({node, nb}) in blocked_edges:
                continue
            if isinstance(edge_data, dict):
                edge_cost = edge_data.get("cost", 1.0)
                if edge_data.get("blocked", False):
                    continue
            else:
                edge_cost = edge_data
            new_cost = cost + edge_cost
            if new_cost < dist.get(nb, float('inf')):
                dist[nb] = new_cost
                prev[nb] = node
                heapq.heappush(heap, (new_cost, nb))

    if end not in dist:
        return []
    path, cur = [], end
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return list(reversed(path))


# ─────────────────────────────────────────────
#  ROAD NETWORK BUILDER (Main Class)
# ─────────────────────────────────────────────
class RoadNetworkBuilder:
    """
    Challenge 2 controller.

    Responsibilities:
    1. Build all candidate edges from the shared CityGraph
    2. Run Kruskal's MST to find minimum-cost road network
    3. Run Second-Path Augmentation for Hospital <-> Depot safety
    4. Write all results back to shared CityGraph
    5. Display results and statistics

    Blocked road preservation:
    _write_to_city_graph() always reads which edges are currently
    blocked before overwriting city.roads, then restores those
    blocked flags on the new edge data. This means:
      - Clicking "Build Roads" again keeps your blocked roads blocked.
      - Adding/replacing a node and auto-rebuilding also keeps them blocked,
        PROVIDED the GUI saves the blocked set before add_node() runs
        (because add_node calls build_road_network() which wipes city.roads).
    """

    def __init__(self, city):
        self.city             = city
        self.mst_edges        = []
        self.backup_edges     = []
        self.primary_hospital = None
        self.ambulance_depot  = None

    # ── ENTRY POINT ─────────────────────────────────────────────────
    def build(self, blocked_edges: set = None):
        """
        Full pipeline.
        blocked_edges: optional set of frozenset({u,v}) to preserve as blocked.
          Pass this when calling after add_node/replace_node, because those
          operations wipe city.roads before this runs.
          If None, blocked edges are harvested automatically from city.roads.
        """
        print(f"\n{'═'*60}")
        print("  CityMind - Challenge 2: Road Network Optimization")
        print(f"{'═'*60}")

        self._identify_key_nodes()
        if self.primary_hospital is None:
            print("  ❌ No Hospital found in city. Cannot build road network.")
            return
        if self.ambulance_depot is None:
            print("  ❌ No Ambulance Depot found. Cannot guarantee safety routes.")
            return

        ph_coords = self.city.coords(self.primary_hospital)
        ad_coords = self.city.coords(self.ambulance_depot)
        print(f"  Primary Hospital  : node {self.primary_hospital} at {ph_coords}")
        print(f"  Ambulance Depot   : node {self.ambulance_depot}  at {ad_coords}")

        all_edges = self._get_candidate_edges()
        print(f"\n  Total candidate edges : {len(all_edges)}")

        self._run_kruskals(all_edges)
        mst_cost = sum(c for _, _, c in self.mst_edges)
        print(f"  MST edges built       : {len(self.mst_edges)}")
        print(f"  MST total cost        : {mst_cost:.2f}")

        self._second_path_augmentation()
        self._write_to_city_graph(blocked_edges=blocked_edges)
        self.display()
        self._verify_safety()

    # ── STEP 1: IDENTIFY KEY NODES ───────────────────────────────────
    def _identify_key_nodes(self):
        for nid in self.city.active_nodes:
            loc = self.city.assignment.get(nid)
            if loc == "Hospital" and self.primary_hospital is None:
                self.primary_hospital = nid
            if loc == "AmbulanceDepot" and self.ambulance_depot is None:
                self.ambulance_depot = nid
            if self.primary_hospital is not None and self.ambulance_depot is not None:
                break

    # ── STEP 2: CANDIDATE EDGES ──────────────────────────────────────
    def _get_candidate_edges(self) -> list:
        seen  = set()
        edges = []
        active_set = set(self.city.active_nodes)

        for node in self.city.active_nodes:
            for nb in self.city.neighbors(node):
                if nb not in active_set:
                    continue
                key = frozenset({node, nb})
                if key in seen:
                    continue
                seen.add(key)
                loc_u = self.city.assignment.get(node)
                loc_v = self.city.assignment.get(nb)
                cost = 0.8 if (loc_u == "Residential" or loc_v == "Residential") else 1.0
                edges.append((cost, node, nb))

        edges.sort()
        return edges

    # ── STEP 3: KRUSKAL'S MST ────────────────────────────────────────
    def _run_kruskals(self, edges: list):
        """
        Kruskal's Algorithm:
          1. Sort all edges by cost (already done)
          2. Use Union-Find to greedily add cheapest edge that doesn't form a cycle
          3. Stop when we have (num_nodes - 1) edges -> MST complete

        VIVA EXPLANATION:
          - Time complexity: O(E log E) dominated by sorting
          - Guarantees globally optimal (minimum cost) spanning tree
          - Union-Find cycle detection is nearly O(1) per operation
            due to path compression + union by rank
        """
        uf = UnionFind(self.city.active_nodes)
        self.mst_edges = []

        for cost, u, v in edges:
            if uf.union(u, v):
                self.mst_edges.append((u, v, cost))
                if len(self.mst_edges) == len(self.city.active_nodes) - 1:
                    break

        if len(self.mst_edges) < len(self.city.active_nodes) - 1:
            print("  ⚠  Warning: Graph is not fully connected. MST is incomplete.")

    # ── STEP 4: SECOND-PATH AUGMENTATION ────────────────────────────
    def _second_path_augmentation(self):
        """
        Guarantees two INDEPENDENT routes between Hospital and Depot.

        Algorithm:
          1. Find Route 1: shortest path in MST from Hospital to Depot
          2. Block all edges on Route 1 temporarily
          3. Find Route 2: shortest path in FULL adjacency graph
             (not just MST) avoiding Route 1 edges
          4. Add Route 2 edges to backup_edges

        VIVA EXPLANATION:
          "Independent" means the two routes share NO edges.
          If any one road fails, the other route is unaffected.
        """
        print(f"\n  [Second-Path Augmentation]")
        ph = self.primary_hospital
        ad = self.ambulance_depot

        mst_graph = defaultdict(dict)
        for u, v, c in self.mst_edges:
            mst_graph[u][v] = c
            mst_graph[v][u] = c

        route1 = dijkstra(mst_graph, ph, ad)
        if not route1:
            print("  ❌ No path found in MST between Hospital and Depot.")
            return

        route1_cost = sum(
            mst_graph[route1[i]][route1[i+1]]
            for i in range(len(route1)-1)
        )
        print(f"  Route 1 (MST path)    : {self._fmt_path(route1)}  cost={route1_cost:.2f}")

        blocked = set()
        for i in range(len(route1) - 1):
            blocked.add(frozenset({route1[i], route1[i+1]}))

        full_graph = defaultdict(dict)
        active_set = set(self.city.active_nodes)
        for node in self.city.active_nodes:
            for nb in self.city.neighbors(node):
                if nb not in active_set:
                    continue
                loc_u = self.city.assignment.get(node)
                loc_v = self.city.assignment.get(nb)
                cost  = 0.8 if (loc_u == "Residential" or loc_v == "Residential") else 1.0
                full_graph[node][nb] = cost

        route2 = dijkstra(full_graph, ph, ad, blocked_edges=blocked)
        if not route2:
            print("  ⚠  No independent backup route found.")
            print("     The grid may be too small or Hospital/Depot may be isolated.")
            print("     Consider increasing grid size for full safety coverage.")
            self.backup_edges = []
            return

        route2_cost = sum(
            full_graph[route2[i]][route2[i+1]]
            for i in range(len(route2)-1)
        )
        print(f"  Route 2 (backup path) : {self._fmt_path(route2)}  cost={route2_cost:.2f}")

        mst_edge_set = {frozenset({u, v}) for u, v, _ in self.mst_edges}
        self.backup_edges = []
        for i in range(len(route2) - 1):
            u, v = route2[i], route2[i+1]
            key  = frozenset({u, v})
            if key not in mst_edge_set:
                loc_u = self.city.assignment.get(u)
                loc_v = self.city.assignment.get(v)
                cost  = 0.8 if (loc_u == "Residential" or loc_v == "Residential") else 1.0
                self.backup_edges.append((u, v, cost))

        if self.backup_edges:
            print(f"  New edges added for safety : {len(self.backup_edges)}")
        else:
            print("  Route 2 uses only existing MST edges (already safe).")

    # ── STEP 5: WRITE BACK TO SHARED CITY GRAPH ─────────────────────
    def _write_to_city_graph(self, blocked_edges: set = None):
        """
        Write MST + backup edges into city.roads with full metadata.

        blocked_edges:
          A set of frozenset({u, v}) pairs that should be marked blocked=True
          in the new road data.

          TWO SOURCES:
            (a) Passed in explicitly by the GUI when calling after add_node /
                replace_node (because those operations wipe city.roads with
                plain floats, destroying blocked info before this runs).
            (b) If None is passed, this method harvests them automatically
                from city.roads BEFORE overwriting — correct for a direct
                "Build Roads" click where city.roads still has dict format.

        Edge metadata stored:
          base_cost  : float  — original road cost, never changed
          cost       : float  — base_cost * risk_multiplier (updated by Ch5)
          blocked    : bool   — True if this road is currently impassable
          in_mst     : bool   — True if selected by Kruskal's
          is_backup  : bool   — True if added by second-path augmentation
        """
        # ── Harvest blocked edges if not passed in ──────────────────
        if blocked_edges is None:
            blocked_edges = set()
            for node in self.city.active_nodes:
                for nb, edge in self.city.roads.get(node, {}).items():
                    if isinstance(edge, dict) and edge.get("blocked", False):
                        blocked_edges.add(frozenset({node, nb}))

        if blocked_edges:
            print(f"  Preserving {len(blocked_edges)} previously blocked road(s).")

        active_set = set(self.city.active_nodes)

        # ── Write all adjacent edges (non-MST, non-backup by default) ──
        for node in self.city.active_nodes:
            if node not in self.city.roads:
                self.city.roads[node] = {}
            for nb in self.city.neighbors(node):
                if nb not in active_set:
                    continue
                loc_u = self.city.assignment.get(node)
                loc_v = self.city.assignment.get(nb)
                cost  = 0.8 if (loc_u == "Residential" or loc_v == "Residential") else 1.0
                self.city.roads[node][nb] = {
                    "base_cost": cost,
                    "cost":      cost,
                    "blocked":   frozenset({node, nb}) in blocked_edges,
                    "in_mst":    False,
                    "is_backup": False,
                }

        # ── Mark MST edges ──────────────────────────────────────────
        for u, v, cost in self.mst_edges:
            self.city.roads[u][v]["in_mst"] = True
            self.city.roads[v][u]["in_mst"] = True

        # ── Mark backup edges ───────────────────────────────────────
        for u, v, cost in self.backup_edges:
            if v in self.city.roads.get(u, {}):
                self.city.roads[u][v]["is_backup"] = True
            if u in self.city.roads.get(v, {}):
                self.city.roads[v][u]["is_backup"] = True

        print(f"\n  ✅ Road network written to shared CityGraph.")

    # ── VERIFICATION ────────────────────────────────────────────────
    def _verify_safety(self) -> tuple:
        """
        Returns (safe: bool, failing_edges: list[str]).
        safe        — True if two independent Hospital↔Depot routes exist.
        failing_edges — human-readable descriptions of edges whose removal
                        disconnects Hospital from Depot (empty when safe).
        Terminal output (print) is unchanged for standalone use.
        """
        print(f"\n  [Safety Verification]")
        ph = self.primary_hospital
        ad = self.ambulance_depot

        full_graph = {}
        for node in self.city.active_nodes:
            full_graph[node] = {}
            for nb, data in self.city.roads.get(node, {}).items():
                if not data.get("blocked", False):
                    full_graph[node][nb] = data.get("cost", 1.0)

        mst_graph = defaultdict(dict)
        for u, v, c in self.mst_edges:
            mst_graph[u][v] = c
            mst_graph[v][u] = c

        route1 = dijkstra(mst_graph, ph, ad)
        if not route1:
            print("  ❌ Cannot verify: no primary route found.")
            return (False, ["No primary route found between Hospital and Depot."])

        all_safe = True
        failing  = []
        for i in range(len(route1) - 1):
            u, v    = route1[i], route1[i+1]
            blocked = {frozenset({u, v})}
            alt     = dijkstra(full_graph, ph, ad, blocked_edges=blocked)
            if not alt:
                msg = (f"Removing road {self.city.coords(u)}↔{self.city.coords(v)} "
                       f"disconnects Hospital from Depot")
                print(f"  ❌ {msg}!")
                all_safe = False
                failing.append(msg)
            else:
                print(f"  ✅ Road {self.city.coords(u)}<->{self.city.coords(v)} can fail "
                      f"— backup route available ({len(alt)-1} hops)")

        if all_safe:
            print(f"\n  ✅ SAFETY GUARANTEED: Two independent routes confirmed.")
        else:
            print(f"\n  ⚠  Safety not fully guaranteed. Consider expanding the grid.")

        return (all_safe, failing)

    # ── DISPLAY ──────────────────────────────────────────────────────
    def display(self):
        print(f"\n{'─'*60}")
        print("  Road Network Summary")
        print(f"{'─'*60}")

        total_cost = sum(c for _, _, c in self.mst_edges) + \
                     sum(c for _, _, c in self.backup_edges)

        print(f"  MST edges    : {len(self.mst_edges)}")
        print(f"  Backup edges : {len(self.backup_edges)}")
        print(f"  Total cost   : {total_cost:.2f}")

        print(f"\n  MST Edges (optimal roads):")
        for u, v, c in self.mst_edges:
            print(f"    {self.city.coords(u)} <-> {self.city.coords(v)}  cost={c:.1f}")

        if self.backup_edges:
            print(f"\n  Backup Edges (safety routes):")
            for u, v, c in self.backup_edges:
                print(f"    {self.city.coords(u)} <-> {self.city.coords(v)}  cost={c:.1f}")

        self._display_grid()
        print(f"{'─'*60}\n")

    def _display_grid(self):
        print(f"\n  Road Network Grid (M=MST, B=Backup, .=no built road):")
        print(f"  (Each cell shows location type + road indicators)\n")

        mst_set    = {frozenset({u, v}) for u, v, _ in self.mst_edges}
        backup_set = {frozenset({u, v}) for u, v, _ in self.backup_edges}

        LABELS = {
            "Residential": "RES", "Hospital": "HSP", "School": "SCH",
            "Industrial": "IND", "PowerPlant": "PWR", "AmbulanceDepot": "AMB",
            None: "   "
        }

        for r in range(self.city.rows):
            row_str = "  "
            for c in range(self.city.cols):
                nid = self.city.node_id(r, c)
                loc = self.city.assignment.get(nid)
                row_str += f"[{LABELS.get(loc, '???')}]"
                if c < self.city.cols - 1:
                    right = self.city.node_id(r, c + 1)
                    key   = frozenset({nid, right})
                    if key in mst_set:
                        row_str += "─M─"
                    elif key in backup_set:
                        row_str += "─B─"
                    else:
                        row_str += " . "
            print(row_str)

            if r < self.city.rows - 1:
                vert_str = "  "
                for c in range(self.city.cols):
                    nid  = self.city.node_id(r, c)
                    down = self.city.node_id(r + 1, c)
                    key  = frozenset({nid, down})
                    if key in mst_set:
                        vert_str += " M  "
                    elif key in backup_set:
                        vert_str += " B  "
                    else:
                        vert_str += " .  "
                    if c < self.city.cols - 1:
                        vert_str += "   "
                print(vert_str)

        print(f"\n  Legend: M = MST (optimal) road  |  B = Backup (safety) road  |  . = no built road")

    def _fmt_path(self, path: list) -> str:
        return " -> ".join(str(self.city.coords(n)) for n in path)


# ─────────────────────────────────────────────
#  STANDALONE ENTRY POINT
# ─────────────────────────────────────────────
def run_challenge2(city, blocked_edges: set = None):
    """
    Call this with a CityGraph instance from Challenge 1.
    blocked_edges: pass if city.roads was wiped before this call.
    """
    builder = RoadNetworkBuilder(city)
    builder.build(blocked_edges=blocked_edges)
    return builder


# ─────────────────────────────────────────────
#  DEMO
# ─────────────────────────────────────────────
def _demo_standalone():
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from challenge1 import CityLayoutManager
        type_counts = {
            "Residential": 6, "Hospital": 2, "School": 2,
            "Industrial": 2, "PowerPlant": 2, "AmbulanceDepot": 1,
        }
        manager = CityLayoutManager()
        manager.initialize(5, 5, sum(type_counts.values()), type_counts, 300, 500)
        run_challenge2(manager.city)
    except ImportError:
        print("challenge1.py not found.")


if __name__ == "__main__":
    _demo_standalone()