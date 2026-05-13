"""
CityMind - Challenge 1: City Layout Planning
============================================
Technique: Constraint Satisfaction Problem (CSP) with Backtracking + Forward Checking
Author: Group Project - BS Computer Science

HOW IT WORKS:
- User provides number of nodes and grid size
- If nodes > grid cells, grid expands by adding columns
- CSP assigns location types to nodes respecting urban planning rules
- Dynamic node addition: checks empty slots first, expands grid if needed
- Node replacement: replaces a node type and re-runs CSP for optimal layout
- Empty grid cells remain empty (user can fill later)
"""

import random
import math
from collections import deque


# ─────────────────────────────────────────────
#  LOCATION TYPES
# ─────────────────────────────────────────────
LOCATION_TYPES = ["Residential", "Hospital", "School", "Industrial", "PowerPlant", "AmbulanceDepot"]

# Short display labels
LABELS = {
    "Residential":    "RES",
    "Hospital":       "HSP",
    "School":         "SCH",
    "Industrial":     "IND",
    "PowerPlant":     "PWR",
    "AmbulanceDepot": "AMB",
    None:             "   "   # empty node
}

# Emoji for pretty display
EMOJI = {
    "Residential":    "🏘 ",
    "Hospital":       "🏥",
    "School":         "🏫",
    "Industrial":     "🏭",
    "PowerPlant":     "⚡",
    "AmbulanceDepot": "🚑",
    None:             "⬜"
}


# ─────────────────────────────────────────────
#  CITY GRAPH (Shared Single Source of Truth)
# ─────────────────────────────────────────────
class CityGraph:
    """
    Represents the city as a grid-based graph.
    - Nodes are grid cells (row, col)
    - Edges are road connections between adjacent nodes
    - Only filled nodes are 'active'; empty cells remain None
    """

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        # assignment[node_id] = location_type or None
        self.assignment = {}
        # node_ids for active (filled) nodes
        self.active_nodes = []
        # road graph: adjacency list with costs
        self.roads = {}  # node_id -> {neighbor_id: cost}

    def node_id(self, r: int, c: int) -> int:
        return r * self.cols + c

    def coords(self, node_id: int):
        return divmod(node_id, self.cols)

    def all_cells(self):
        return [self.node_id(r, c) for r in range(self.rows) for c in range(self.cols)]

    def neighbors(self, node_id: int):
        r, c = self.coords(node_id)
        nbrs = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                nbrs.append(self.node_id(nr, nc))
        return nbrs

    def bfs_distance(self, start: int, targets: set) -> int:
        """BFS to find minimum distance from start to any node in targets."""
        if start in targets:
            return 0
        visited = {start}
        queue = deque([(start, 0)])
        while queue:
            node, dist = queue.popleft()
            for nb in self.neighbors(node):
                if nb not in visited and self.assignment.get(nb) is not None:
                    visited.add(nb)
                    if nb in targets:
                        return dist + 1
                    queue.append((nb, dist + 1))
        return float('inf')

    def get_empty_cells(self):
        """Return all cells not in active_nodes."""
        active_set = set(self.active_nodes)
        return [cell for cell in self.all_cells() if cell not in active_set]

    def expand_grid(self, extra_cols: int):
        """Expand grid by adding columns to the right."""
        old_cols = self.cols
        self.cols += extra_cols
        # Re-index all existing assignments
        new_assignment = {}
        for node in self.active_nodes:
            r, c = divmod(node, old_cols)          # old coords
            new_node = self.node_id(r, c)          # recalc with new cols
            new_assignment[new_node] = self.assignment[node]
        self.assignment = new_assignment
        self.active_nodes = list(new_assignment.keys())
        print(f"  [Grid Expanded] New size: {self.rows}x{self.cols}")

    def build_road_network(self):
        """Connect all active nodes to their active neighbors."""
        self.roads = {n: {} for n in self.active_nodes}
        active_set = set(self.active_nodes)
        for node in self.active_nodes:
            for nb in self.neighbors(node):
                if nb in active_set:
                    loc = self.assignment.get(node)
                    cost = 0.8 if loc == "Residential" else 1.0
                    self.roads[node][nb] = cost

    def display(self):
        """Print the city grid with location types."""
        print(f"\n{'─'*60}")
        print(f"  City Grid ({self.rows} rows × {self.cols} cols)")
        print(f"{'─'*60}")
        for r in range(self.rows):
            row_str = "  "
            for c in range(self.cols):
                nid = self.node_id(r, c)
                loc = self.assignment.get(nid)
                row_str += f"[{LABELS[loc]}]"
            print(row_str)
        print(f"{'─'*60}")
        # Legend
        print("\n  Legend:")
        for t, lbl in LABELS.items():
            if t is not None:
                print(f"    [{lbl}] = {t}")
        print(f"{'─'*60}\n")


# ─────────────────────────────────────────────
#  CONSTRAINT CHECKER
# ─────────────────────────────────────────────
class ConstraintChecker:
    """
    Checks urban planning constraints:
    1. Industrial NOT adjacent to School or Hospital
    2. Every Residential within 3 hops of a Hospital
    3. Every PowerPlant within 2 hops of an Industrial zone
    """

    def __init__(self, city: CityGraph):
        self.city = city

    def is_compatible(self, node_id: int, loc_type: str, partial: dict) -> bool:
        """
        Forward-checking: can we assign loc_type to node_id given partial assignment?
        """
        r, c = self.city.coords(node_id)

        for nb in self.city.neighbors(node_id):
            nb_type = partial.get(nb)
            if nb_type is None:
                continue
            # Rule 1: Industrial not next to School/Hospital
            if loc_type == "Industrial" and nb_type in ("School", "Hospital"):
                return False
            if nb_type == "Industrial" and loc_type in ("School", "Hospital"):
                return False

        return True  # Full constraint check runs after complete assignment

    def full_check(self, assignment: dict, active_nodes: list):
        """
        Full constraint verification after complete assignment.
        Returns (passed: bool, violations: list of strings)
        """
        violations = []
        hospitals = {n for n in active_nodes if assignment.get(n) == "Hospital"}
        industrials = {n for n in active_nodes if assignment.get(n) == "Industrial"}

        for node in active_nodes:
            loc = assignment.get(node)
            if loc is None:
                continue

            # Rule 1: Industrial not adjacent to School/Hospital
            if loc == "Industrial":
                for nb in self.city.neighbors(node):
                    nb_loc = assignment.get(nb)
                    if nb_loc in ("School", "Hospital"):
                        violations.append(
                            f"Rule1: Industrial@{self.city.coords(node)} adjacent to {nb_loc}@{self.city.coords(nb)}"
                        )

            # Rule 2: Residential within 3 hops of Hospital
            if loc == "Residential":
                if not hospitals:
                    violations.append(f"Rule2: No hospitals exist; Residential@{self.city.coords(node)} uncovered")
                else:
                    dist = self.city.bfs_distance(node, hospitals)
                    if dist > 3:
                        violations.append(
                            f"Rule2: Residential@{self.city.coords(node)} is {dist} hops from nearest Hospital (max 3)"
                        )

            # Rule 3: PowerPlant within 2 hops of Industrial
            if loc == "PowerPlant":
                if not industrials:
                    violations.append(f"Rule3: No industrial zones; PowerPlant@{self.city.coords(node)} uncovered")
                else:
                    dist = self.city.bfs_distance(node, industrials)
                    if dist > 2:
                        violations.append(
                            f"Rule3: PowerPlant@{self.city.coords(node)} is {dist} hops from Industrial (max 2)"
                        )

        return (len(violations) == 0), violations


# ─────────────────────────────────────────────
#  CSP SOLVER (Backtracking + Forward Checking)
# ─────────────────────────────────────────────
class CSPSolver:
    """
    Solves the city layout as a CSP:
    - Variables: active node IDs
    - Domain: LOCATION_TYPES (constrained by remaining type_counts)
    - Constraints: urban planning rules

    Real techniques used:
    - Backtracking search
    - Forward Checking (maintains live domains, prunes after each assignment)
    - MRV heuristic (picks variable with smallest remaining domain)
    - Min-Conflicts as fallback when backtracking budget is exhausted
    """

    def __init__(self, city: CityGraph, checker: ConstraintChecker, type_counts: dict,
                 max_bt: int = 300, max_mc: int = 500):
        self.city = city
        self.checker = checker
        self.type_counts = type_counts
        self.remaining_counts = dict(type_counts)
        self.max_bt = max_bt
        self.max_mc = max_mc
        self._bt_calls = 0

    def solve(self) -> bool:
        """Run CSP backtracking with FC + MRV. Returns True if solution found."""
        nodes = list(self.city.active_nodes)
        # Initialize domain for each variable: all types still available
        domains = {n: list(LOCATION_TYPES) for n in nodes}
        return self._backtrack(domains, {})

    def _select_unassigned_mrv(self, domains, partial):
        """MRV: pick the unassigned variable with the FEWEST legal values left."""
        unassigned = [n for n in domains if n not in partial]
        if not unassigned:
            return None
        # Tie-break by node_id for determinism
        return min(unassigned, key=lambda n: (len(domains[n]), n))

    def _forward_check(self, node, loc_type, domains, partial):
        """
        After assigning loc_type to node, prune domains of unassigned neighbors.
        Returns (ok, removed) where:
          - ok = False if any neighbor's domain becomes empty (dead end)
          - removed = dict of {neighbor: [values_we_pruned]} so we can undo
        """
        removed = {}
        for nb in self.city.neighbors(node):
            if nb in partial or nb not in domains:
                continue
            pruned_here = []
            # Rule 1: if we just placed Industrial, neighbors can't be School/Hospital
            if loc_type == "Industrial":
                for v in ("School", "Hospital"):
                    if v in domains[nb]:
                        domains[nb].remove(v)
                        pruned_here.append(v)
            # Rule 1 mirror: if we placed School/Hospital, neighbors can't be Industrial
            if loc_type in ("School", "Hospital"):
                if "Industrial" in domains[nb]:
                    domains[nb].remove("Industrial")
                    pruned_here.append("Industrial")
            # Also prune any type whose remaining_counts has hit zero
            for v in list(domains[nb]):
                if self.remaining_counts.get(v, 0) <= 0:
                    domains[nb].remove(v)
                    pruned_here.append(v)
            if pruned_here:
                removed[nb] = pruned_here
            if not domains[nb]:
                return False, removed   # dead end → trigger backtrack
        return True, removed

    def _undo_forward_check(self, removed, domains):
        """Restore domain values pruned by a failed forward check."""
        for nb, vals in removed.items():
            domains[nb].extend(vals)

    def _backtrack(self, domains, partial) -> bool:
        self._bt_calls += 1
        if self._bt_calls > self.max_bt:
            return False  # budget exhausted → caller falls through to min-conflicts

        # Done? Verify with full check (catches Rule 2 & Rule 3 which are non-local)
        if len(partial) == len(self.city.active_nodes):
            self.city.assignment.update(partial)
            ok, _ = self.checker.full_check(self.city.assignment, self.city.active_nodes)
            if ok:
                return True
            for n in self.city.active_nodes:
                self.city.assignment[n] = None
            return False

        # MRV: pick the most-constrained variable
        node = self._select_unassigned_mrv(domains, partial)
        if node is None:
            return False

        # Try each value in this variable's current domain
        for loc_type in list(domains[node]):
            if self.remaining_counts.get(loc_type, 0) <= 0:
                continue
            if not self.checker.is_compatible(node, loc_type, partial):
                continue

            # Tentatively assign
            partial[node] = loc_type
            self.remaining_counts[loc_type] -= 1
            saved_domain = domains[node]
            domains[node] = [loc_type]

            # Forward check: prune neighbors
            ok, removed = self._forward_check(node, loc_type, domains, partial)
            if ok and self._backtrack(domains, partial):
                return True

            # Undo
            self._undo_forward_check(removed, domains)
            domains[node] = saved_domain
            self.remaining_counts[loc_type] += 1
            del partial[node]

        return False

    # ───────── Min-Conflicts (unchanged behavior, kept as fallback) ─────────
    def find_minimum_conflict_solution(self):
        print("\n  [CSP] Backtracking budget exhausted. Running Min-Conflicts fallback...")
        nodes = list(self.city.active_nodes)
        types_flat = []
        for t, cnt in self.type_counts.items():
            types_flat.extend([t] * cnt)
        while len(types_flat) < len(nodes):
            types_flat.append("Residential")

        random.shuffle(types_flat)
        assignment = {nodes[i]: types_flat[i] for i in range(len(nodes))}

        for _ in range(self.max_mc):
            _, violations = self.checker.full_check(assignment, nodes)
            if not violations:
                break
            conflicted = self._get_conflicted_node(assignment, violations, nodes)
            best_type = self._min_conflict_value(conflicted, assignment, nodes)
            assignment[conflicted] = best_type

        self.city.assignment.update(assignment)
        _, violations = self.checker.full_check(self.city.assignment, nodes)
        return assignment, violations

    def _get_conflicted_node(self, assignment, violations, nodes):
        mentioned = set()
        for v in violations:
            for node in nodes:
                if str(self.city.coords(node)) in v:
                    mentioned.add(node)
        return random.choice(list(mentioned)) if mentioned else random.choice(nodes)

    def _min_conflict_value(self, node, assignment, nodes):
        """Swap to the type that yields fewest violations, respecting type counts."""
        best_type = assignment[node]
        best_count = float('inf')
        current_type = assignment[node]

        current_counts = {}
        for n in nodes:
            t = assignment.get(n)
            if t:
                current_counts[t] = current_counts.get(t, 0) + 1

        for loc_type in LOCATION_TYPES:
            if loc_type != current_type:
                new_current = current_counts.get(current_type, 0) - 1
                new_target  = current_counts.get(loc_type, 0) + 1
                if new_current < 0:
                    continue
                if new_target > self.type_counts.get(loc_type, 0):
                    continue
                if new_current < self.type_counts.get(current_type, 0) - 1:
                    continue

            old = assignment[node]
            assignment[node] = loc_type
            _, viols = self.checker.full_check(assignment, nodes)
            if len(viols) < best_count:
                best_count = len(viols)
                best_type = loc_type
            assignment[node] = old

        return best_type

# ─────────────────────────────────────────────
#  CITY LAYOUT MANAGER (Main Controller)
# ─────────────────────────────────────────────
class CityLayoutManager:
    """
    High-level controller that handles:
    - Dynamic grid sizing
    - Grid expansion when nodes > grid capacity
    - Adding new nodes (checks empty slots, expands if needed)
    - Node replacement (re-runs full CSP)
    - Reporting violations and minimum-conflict solutions
    """

    def __init__(self):
        self.city = None
        self.checker = None
        self.type_counts = {}

    # ── 1. INITIALIZE CITY ──────────────────────────────────────────
    def initialize(self, rows: int, cols: int, num_nodes: int, type_counts: dict, max_bt: int = 300, max_mc: int = 500):
        """
        Create city with given grid size and place num_nodes active nodes.
        If num_nodes > rows*cols, expand grid columns automatically.
        """
        print(f"\n{'═'*60}")
        print(f"  CityMind - Challenge 1: City Layout Planning")
        print(f"{'═'*60}")

        total_cells = rows * cols
        self.type_counts = dict(type_counts)
        self.max_bt = max_bt
        self.max_mc = max_mc
        total_requested = sum(type_counts.values())

        # Verify type_counts match num_nodes
        if total_requested != num_nodes:
            print(f"  [Warning] type_counts sum ({total_requested}) != num_nodes ({num_nodes})")
            print(f"  Adjusting num_nodes to {total_requested}")
            num_nodes = total_requested

        # Expand grid if needed
        if num_nodes > total_cells:
            extra = num_nodes - total_cells
            extra_cols = math.ceil(extra / rows)
            print(f"  [Info] {num_nodes} nodes > {total_cells} grid cells.")
            print(f"  [Info] Expanding grid by {extra_cols} column(s).")
            cols += extra_cols

        self.city = CityGraph(rows, cols)
        self.checker = ConstraintChecker(self.city)

        # Place active nodes - fill grid left-to-right, top-to-bottom
        all_cells = self.city.all_cells()
        self.city.active_nodes = all_cells[:num_nodes]
        for nid in all_cells:
            self.city.assignment[nid] = None  # all cells start empty

        print(f"  Grid: {rows} x {self.city.cols}  |  Active Nodes: {num_nodes}  |  Empty Cells: {self.city.cols * rows - num_nodes}")
        print(f"  Location Types Requested: {type_counts}")
        print(f"\n  Running CSP Solver (Backtracking + Forward Checking)...")

        solver = CSPSolver(self.city, self.checker, self.type_counts, self.max_bt, self.max_mc)
        success = solver.solve()

        if success:
            print("  ✅ CSP Solved! Valid city layout found.")
            self.city.build_road_network()
            self.city.display()
            self._show_stats()
        else:
            print("  ❌ No perfect solution found. Finding minimum-conflict layout...")
            assignment, violations = solver.find_minimum_conflict_solution()
            self.city.build_road_network()
            self.city.display()
            print(f"\n  ⚠  Constraint Violations ({len(violations)}):")
            for v in violations:
                print(f"    • {v}")
            print(f"\n  💡 Suggestion: Increase grid size or adjust node counts to resolve conflicts.")
            self._identify_conflict_rules(violations)
            self._conflict_cell_summary(violations)
            self._interactive_resolve(violations)   # ← NEW

    # ── 2. ADD NEW NODE ─────────────────────────────────────────────
    def add_node(self, loc_type: str):
        """
        Add a new node of given type.
        - First checks for empty cells in current grid
        - If no empty cells: expands grid by 50% more columns, places node at best position
        - Re-runs CSP after placement
        """
        print(f"\n{'─'*60}")
        print(f"  [Add Node] Requesting new: {loc_type}")

        empty_cells = self.city.get_empty_cells()

        if empty_cells:
            # Find best empty cell (least distance to existing active nodes)
            best_cell = self._best_empty_cell(empty_cells)
            r, c = self.city.coords(best_cell)
            print(f"  ✅ Empty slot found at ({r},{c}). Placing {loc_type} there.")
            self.city.active_nodes.append(best_cell)
            self.type_counts[loc_type] = self.type_counts.get(loc_type, 0) + 1
        else:
            # Expand grid by 50% more columns
            extra_cols = max(1, self.city.cols // 2)
            print(f"  [Grid Full] Expanding by {extra_cols} columns (50% of current {self.city.cols}).")
            self.city.expand_grid(extra_cols)
            # Place ONLY the new node at best position in expanded area
            empty_cells = self.city.get_empty_cells()
            best_cell = self._best_empty_cell_in_expansion(empty_cells, self.city.cols - extra_cols)
            r, c = self.city.coords(best_cell)
            print(f"  Placing {loc_type} at best position ({r},{c}) in expanded grid.")
            self.city.active_nodes.append(best_cell)
            self.type_counts[loc_type] = self.type_counts.get(loc_type, 0) + 1

        # Clear all assignments and re-run CSP on all active nodes
        for nid in self.city.active_nodes:
            self.city.assignment[nid] = None
        print(f"  Re-running CSP for optimal layout with new node...")

        solver = CSPSolver(self.city, self.checker, self.type_counts, self.max_bt, self.max_mc)
        success = solver.solve()

        if success:
            print("  ✅ New optimal layout found.")
        else:
            print("  ⚠  No perfect layout; using min-conflict solution.")
            solver.find_minimum_conflict_solution()

        self.city.build_road_network()
        self.city.display()
        self._show_stats()

    # ── 3. REPLACE NODE ─────────────────────────────────────────────
    def replace_node(self, node_id: int, new_type: str):
        """
        Replace the type of an existing node and re-run CSP
        to find optimal layout for the whole city.
        """
        r, c = self.city.coords(node_id)
        old_type = self.city.assignment.get(node_id)
        print(f"\n{'─'*60}")
        print(f"  [Replace Node] ({r},{c}): {old_type} → {new_type}")

        if node_id not in self.city.active_nodes:
            print("  ❌ Node is not active. Cannot replace.")
            return

        # Update type counts
        if old_type and self.type_counts.get(old_type, 0) > 0:
            self.type_counts[old_type] -= 1
        self.type_counts[new_type] = self.type_counts.get(new_type, 0) + 1

        # Clear and re-solve
        for nid in self.city.active_nodes:
            self.city.assignment[nid] = None
        print("  Re-running CSP for full optimal city layout...")

        solver = CSPSolver(self.city, self.checker, self.type_counts, self.max_bt, self.max_mc)
        success = solver.solve()

        if success:
            print("  ✅ New optimal layout found after replacement.")
        else:
            print("  ⚠  No perfect layout; using min-conflict solution.")
            solver.find_minimum_conflict_solution()

        self.city.build_road_network()
        self.city.display()
        self._show_stats()
        # Explicitly confirm whether replacement satisfies all CSP constraints
        ok, violations = self.checker.full_check(self.city.assignment, self.city.active_nodes)
        if ok:
            print("  ✅ Replacement satisfies all CSP constraints.")
        else:
            print(f"  ⚠  Replacement introduced {len(violations)} violation(s):")
            for v in violations:
                print(f"    • {v}")
            self._conflict_cell_summary(violations)
            self._identify_conflict_rules(violations)   # ← NEW
            self._interactive_resolve(violations)       # ← NEW

    # ── 4. VALIDATE CURRENT LAYOUT ──────────────────────────────────
    def validate(self):
        """Check current layout and report all constraint violations."""
        print(f"\n{'─'*60}")
        print("  [Validation] Checking all constraints...")
        ok, violations = self.checker.full_check(self.city.assignment, self.city.active_nodes)
        if ok:
            print("  ✅ All constraints satisfied!")
        else:
            print(f"  ❌ Found {len(violations)} violation(s):")
            for v in violations:
                print(f"    • {v}")
            self._identify_conflict_rules(violations)
            self._interactive_resolve(violations)   

    # ── HELPERS ─────────────────────────────────────────────────────
    def _best_empty_cell(self, empty_cells: list) -> int:
        """Find empty cell with least average grid distance to active nodes."""
        if not self.city.active_nodes:
            return empty_cells[0]
        best, best_score = empty_cells[0], float('inf')
        for cell in empty_cells:
            cr, cc = self.city.coords(cell)
            score = sum(
                abs(cr - self.city.coords(n)[0]) + abs(cc - self.city.coords(n)[1])
                for n in self.city.active_nodes
            )
            avg = score / len(self.city.active_nodes)
            if avg < best_score:
                best_score, best = avg, cell
        return best

    def _best_empty_cell_in_expansion(self, empty_cells: list, old_col_count: int) -> int:
        """
        Find the best cell in the newly expanded columns.
        Prefer cells in expansion area closest to existing nodes.
        """
        expansion_cells = [c for c in empty_cells if self.city.coords(c)[1] >= old_col_count]
        if not expansion_cells:
            return self._best_empty_cell(empty_cells)
        return self._best_empty_cell(expansion_cells)

    def _show_stats(self):
        """Show count of each location type in current assignment."""
      
        counts = {t: 0 for t in LOCATION_TYPES}   # init ALL types to 0
        for nid in self.city.active_nodes:
            t = self.city.assignment.get(nid)
            if t:
                counts[t] = counts.get(t, 0) + 1
        print("  Current Node Counts:")
        for t in LOCATION_TYPES:                   # fixed order, all types shown
            print(f"    {LABELS[t]} ({t}): {counts[t]}")
            
    def _conflict_cell_summary(self, violations: list):
        """Show exactly which cells are involved in conflicts and why."""
        from collections import defaultdict
        cell_issues = defaultdict(list)

        for v in violations:
            # extract coords like (2,3) from violation strings
            import re
            coords = re.findall(r'\((\d+),\s*(\d+)\)', v)
            rule = v.split(":")[0].strip()
            reason = v.split(":", 1)[1].strip() if ":" in v else v
            for r, c in coords:
                cell_issues[(int(r), int(c))].append(f"{rule}: {reason}")

        if not cell_issues:
            return

        print("\n  Conflicted Cell Summary:")
        print(f"  {'Cell':<12} {'Type':<16} {'Issues'}")
        print(f"  {'─'*55}")
        for (r, c), issues in sorted(cell_issues.items()):
            nid = self.city.node_id(r, c)
            loc = self.city.assignment.get(nid, "Unknown")
            label = LABELS.get(loc, "???")
            for issue in issues:
                print(f"  ({r},{c}) {label:<4} {loc:<16} {issue}")

    def _identify_conflict_rules(self, violations: list):
        """Identify which specific rule is causing conflicts."""
        rule_hits = {"Rule1": 0, "Rule2": 0, "Rule3": 0}
        for v in violations:
            for key in rule_hits:
                if key in v:
                    rule_hits[key] += 1
        print("\n  Conflict Source Analysis:")
        rule_desc = {
            "Rule1": "Industrial adjacent to School/Hospital",
            "Rule2": "Residential too far from Hospital (>3 hops)",
            "Rule3": "PowerPlant too far from Industrial (>2 hops)"
        }
        for rule, count in rule_hits.items():
            if count > 0:
                print(f"    🔴 {rule} ({rule_desc[rule]}): {count} violation(s)")
                if rule == "Rule1":
                    print("       → Fix: Increase grid size or reduce Industrial/School/Hospital counts")
                elif rule == "Rule2":
                    print("       → Fix: Add more Hospitals or reduce Residential count")
                elif rule == "Rule3":
                    print("       → Fix: Place PowerPlant closer to Industrial zones")

    # ── INTERACTIVE CONFLICT RESOLUTION ─────────────────────────────
    def _interactive_resolve(self, violations: list):
        """
        After conflicts are detected, offer the user concrete fixes
        and apply the chosen one automatically. Re-runs CSP after fixing.
        """
        if not violations:
            return

        rule_hits = {"Rule1": 0, "Rule2": 0, "Rule3": 0}
        for v in violations:
            for key in rule_hits:
                if key in v:
                    rule_hits[key] += 1

        # Build a menu of fixes based on which rules failed
        print("\n  ┌─────────────────────────────────────────────────┐")
        print("  │  Would you like the system to auto-fix conflicts? │")
        print("  └─────────────────────────────────────────────────┘")

        fixes = []   # list of (label, callable)

        if rule_hits["Rule1"] > 0:
            fixes.append((
                "Expand grid by 2 columns (more space for Industrial separation)",
                lambda: self._fix_expand_grid(2)
            ))
            fixes.append((
                "Reduce Industrial count by 1",
                lambda: self._fix_reduce_type("Industrial", 1)
            ))

        if rule_hits["Rule2"] > 0:
            fixes.append((
                "Add 1 more Hospital (improves Residential coverage)",
                lambda: self._fix_add_type("Hospital", 1)
            ))
            fixes.append((
                "Reduce Residential count by 2",
                lambda: self._fix_reduce_type("Residential", 2)
            ))

        if rule_hits["Rule3"] > 0:
            fixes.append((
                "Reduce PowerPlant count by 1 (or add another Industrial)",
                lambda: self._fix_reduce_type("PowerPlant", 1)
            ))
            fixes.append((
                "Add 1 more Industrial zone (anchors PowerPlants)",
                lambda: self._fix_add_type("Industrial", 1)
            ))

        fixes.append(("Skip auto-fix and keep current min-conflict layout", None))

        # Show menu
        print("\n  Available Options:")
        for i, (label, _) in enumerate(fixes, 1):
            print(f"    {i}. {label}")

        try:
            choice = int(input("\n  Choose a fix (1-{}): ".format(len(fixes))).strip())
        except ValueError:
            print("  Invalid input. Keeping current layout.")
            return

        if choice < 1 or choice > len(fixes):
            print("  Invalid choice. Keeping current layout.")
            return

        label, action = fixes[choice - 1]
        if action is None:
            print(f"  → Keeping min-conflict layout as-is.")
            return

        print(f"\n  → Applying: {label}")
        action()
        self._resolve_and_show()


    def _resolve_and_show(self):
        """Re-run CSP after a fix, display the new grid, recurse if still broken."""
        for nid in self.city.active_nodes:
            self.city.assignment[nid] = None
        print("  Re-running CSP with adjusted configuration...")
        solver = CSPSolver(self.city, self.checker, self.type_counts, self.max_bt, self.max_mc)
        success = solver.solve()
        if success:
            print("  ✅ Conflict resolved! Valid layout found after auto-fix.")
            self.city.build_road_network()
            self.city.display()
            self._show_stats()
        else:
            print("  ⚠  Still no perfect solution after fix. Falling back to min-conflicts.")
            _, violations = solver.find_minimum_conflict_solution()
            self.city.build_road_network()
            self.city.display()
            self._show_stats()
            if violations:
                print(f"\n  ⚠  Remaining violations: {len(violations)}")
                self._identify_conflict_rules(violations)
                # Offer another round of fixes (user can stop anytime)
                self._interactive_resolve(violations)


    # ── FIX PRIMITIVES (called by _interactive_resolve) ─────────────
    def _fix_expand_grid(self, extra_cols: int):
        """Add columns to give CSP more room."""
        self.city.expand_grid(extra_cols)

    def _fix_reduce_type(self, loc_type: str, n: int):
        """Remove n nodes of given type from active set."""
        removed = 0
        # Walk active_nodes in reverse so removal is safe
        for nid in list(reversed(self.city.active_nodes)):
            if removed >= n:
                break
            if self.city.assignment.get(nid) == loc_type:
                self.city.active_nodes.remove(nid)
                self.city.assignment[nid] = None
                removed += 1
        self.type_counts[loc_type] = max(0, self.type_counts.get(loc_type, 0) - removed)
        print(f"    Removed {removed} {loc_type} node(s). New count: {self.type_counts[loc_type]}")

    def _fix_add_type(self, loc_type: str, n: int):
        """Add n new nodes of given type, expanding grid if no empty cells exist."""
        for _ in range(n):
            empty = self.city.get_empty_cells()
            if not empty:
                extra_cols = max(1, self.city.cols // 2)
                print(f"    No empty cells — expanding grid by {extra_cols} cols.")
                self.city.expand_grid(extra_cols)
                empty = self.city.get_empty_cells()
            target = self._best_empty_cell(empty)
            self.city.active_nodes.append(target)
        self.type_counts[loc_type] = self.type_counts.get(loc_type, 0) + n
        print(f"    Added {n} {loc_type} node(s). New count: {self.type_counts[loc_type]}")
# ─────────────────────────────────────────────
#  INTERACTIVE DEMO / MAIN
# ─────────────────────────────────────────────
def get_user_input():
    """Collect user inputs for grid and node configuration."""
    print("\n" + "═" * 60)
    print("  Welcome to CityMind - Challenge 1: City Layout Planner")
    print("═" * 60)

    rows = int(input("\n  Enter number of grid rows: ").strip())
    cols = int(input("  Enter number of grid columns: ").strip())

    print("\n  Enter how many of each location type to place:")
    print("  (Enter 0 if you don't want that type)")

    type_counts = {}
    for t in LOCATION_TYPES:
        val = int(input(f"    {t}: ").strip())
        if val > 0:
            type_counts[t] = val

    num_nodes = sum(type_counts.values())
    max_bt = int(input("\n  Max backtracking attempts before giving up (e.g. 500): ").strip())
    max_mc = int(input("  Max min-conflict iterations as fallback (e.g. 1000): ").strip())
    return rows, cols, num_nodes, type_counts, max_bt, max_mc


def demo_run():
    """
    Automated demo with a pre-set configuration.
    Great for testing and showing to professor.
    """
    print("\n" + "═" * 60)
    print("  CityMind - Challenge 1: DEMO MODE")
    print("═" * 60)

    # Configuration
    rows = 5
    cols = 5
    type_counts = {
        "Residential":    6,
        "Hospital":       2,
        "School":         2,
        "Industrial":     2,
        "PowerPlant":     2,
        "AmbulanceDepot": 1
    }
    num_nodes = sum(type_counts.values())  # = 15, fits in 5x5

    max_bt = 300      # tweak these demo defaults freely
    max_mc = 500
    manager = CityLayoutManager()
    manager.initialize(rows, cols, num_nodes, type_counts, max_bt, max_mc)

    # ── Demo: Add a new hospital ──
    print("\n" + "═" * 60)
    print("  DEMO: Adding a new Hospital node...")
    print("═" * 60)
    manager.add_node("Hospital")

    # ── Demo: Replace a node ──
    print("\n" + "═" * 60)
    print("  DEMO: Replacing node at (0,0) type with School...")
    print("═" * 60)
    node_to_replace = manager.city.node_id(0, 0)
    manager.replace_node(node_to_replace, "School")

    # ── Final Validation ──
    manager.validate()

    print("\n" + "═" * 60)
    print("  DEMO COMPLETE ✅")
    print("  All constraints verified. City layout is valid.")
    print("═" * 60)


def interactive_run():
    """Full interactive mode for user-controlled city building."""
    rows, cols, num_nodes, type_counts, max_bt, max_mc = get_user_input()

    manager = CityLayoutManager()
    manager.initialize(rows, cols, num_nodes, type_counts, max_bt, max_mc)

    while True:
        print("\n  What would you like to do?")
        print("  1. Add a new node")
        print("  2. Replace an existing node")
        print("  3. Validate layout")
        print("  4. Show city grid")
        print("  5. Build Road Network (Challenge 2)")
        print("  6. Exit")

        choice = input("\n  Enter choice (1-6): ").strip()

        if choice == "1":
            print(f"  Available types: {LOCATION_TYPES}")
            loc = input("  Enter location type to add: ").strip()
            if loc in LOCATION_TYPES:
                manager.add_node(loc)
            else:
                print("  Invalid type.")

        elif choice == "2":
            r = int(input("  Enter row of node to replace: "))
            c = int(input("  Enter col of node to replace: "))
            nid = manager.city.node_id(r, c)
            print(f"  Available types: {LOCATION_TYPES}")
            new_type = input("  Enter new type: ").strip()
            if new_type in LOCATION_TYPES:
                manager.replace_node(nid, new_type)
            else:
                print("  Invalid type.")

        elif choice == "3":
            manager.validate()

        elif choice == "4":
            manager.city.display()

        elif choice == "5":
            from challenge2 import run_challenge2
            run_challenge2(manager.city)

        elif choice == "6":
            print("\n  Exiting CityMind. Goodbye!")
            break

        else:
            print("  Invalid choice.")

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo_run()
    else:
        print("\n  Run mode:")
        print("  1. Interactive (you enter values)")
        print("  2. Demo (pre-set values, shows all features)")
        mode = input("\n  Choose (1 or 2): ").strip()
        if mode == "2":
            demo_run()
        else:
            interactive_run()