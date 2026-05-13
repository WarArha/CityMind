"""
CityMind - Challenge 4: Emergency Routing Under Changing Conditions
====================================================================
Technique: A* Search with Admissible Heuristic + Dynamic Re-routing
Author: Group Project - BS Computer Science

WHY A* (not Dijkstra or BFS):
  Dijkstra's algorithm expands nodes purely by accumulated cost, radiating
  outward in all directions. A* adds a heuristic h(n) — an estimate of the
  remaining cost to the goal — so it preferentially expands nodes that are
  BOTH cheaply reached AND close to the goal. This dramatically reduces the
  number of nodes visited, making real-time re-routing feasible.

  BFS gives shortest paths only on unweighted graphs. Our city has weighted
  roads (Residential = 0.8, others = 1.0, risk-adjusted if Ch5 ran), so BFS
  would give wrong results.

ADMISSIBILITY — THE KEY GUARANTEE:
  For A* to guarantee the OPTIMAL (shortest) path, the heuristic must be
  ADMISSIBLE: h(n) must NEVER OVERESTIMATE the true cost to the goal.

  Our heuristic: h(n) = Manhattan_distance(n, goal) × 0.8

  Proof of admissibility:
    - Any path from n to goal must traverse at least Manhattan_distance edges
      (the grid is 4-connected; diagonal shortcuts don't exist).
    - Every road edge costs at minimum 0.8 (Residential zones).
    - Therefore: true_cost ≥ Manhattan_distance × 0.8 = h(n).
    - So h(n) ≤ true_cost → admissible → A* returns the optimal path.

  Note: if Ch5 (Crime Risk) has run, effective edge costs increase by the
  risk factor (cost × (1+risk)). Our heuristic ignores risk and still
  uses 0.8 as the minimum, so it remains admissible even with risk applied.

DYNAMIC RE-ROUTING:
  After each team step, every edge on the route ahead is checked:
    if any road is marked blocked → immediately re-run A* from current position.
  This guarantees:
    1. The team is never stuck — re-routing finds any available path.
    2. The new route is optimal under current road conditions.
    3. Response is instantaneous (re-routing happens on the same cycle as the
       road block, before the next step is taken).

MULTI-CIVILIAN MISSION (Sequential Waypoints):
  The team must reach ALL civilians in given order (not just the nearest).
  Full route = A*(start→civ1) ++ A*(civ1→civ2) ++ ... ++ A*(civN-1→civN).
  When a civilian is reached, their waypoint is removed and the route
  automatically continues to the next. A* re-runs for the new sub-leg
  whenever the environment changes.
"""

import heapq


# ── A* Core ───────────────────────────────────────────────────────────────────

def astar(city, start: int, goal: int) -> list:
    """
    A* shortest path from start to goal.

    Heuristic: Manhattan distance × 0.8  (admissible — see module docstring).
    Respects:
      - city.roads blocked flags
      - city.risk_index values from Ch5 (if available)
    Falls back to grid adjacency (unit cost) when no roads are built.

    Returns list of node IDs forming the path (inclusive), or [] if unreachable.
    """
    if start == goal:
        return [start]

    def h(node: int) -> float:
        r1, c1 = city.coords(node)
        r2, c2 = city.coords(goal)
        return (abs(r1 - r2) + abs(c1 - c2)) * 0.8   # admissible lower bound

    open_set  = [(h(start), 0.0, start)]   # (f = g + h, g, node)
    g_score   = {start: 0.0}
    came_from = {start: None}
    closed    = set()
    active_set = set(city.active_nodes)

    while open_set:
        f, g, node = heapq.heappop(open_set)
        if node in closed:
            continue
        if node == goal:
            path, cur = [], goal
            while cur is not None:
                path.append(cur); cur = came_from[cur]
            return list(reversed(path))
        closed.add(node)

        if city.roads:
            # Use built road network with real costs
            for nb, edge in city.roads.get(node, {}).items():
                if nb not in active_set:
                    continue
                if isinstance(edge, dict):
                    if edge.get("blocked", False):
                        continue
                    base = edge.get("cost", 1.0)
                    if "base_cost" in edge:
                        step = base
                    else:
                        risk = getattr(city, "risk_index", {}).get(nb, 0.0)
                        step = base * (1.0 + risk)
                else:
                    base = float(edge) if edge else 1.0
                    risk = getattr(city, "risk_index", {}).get(nb, 0.0)
                    step = base * (1.0 + risk)
                ng = g + step
                if ng < g_score.get(nb, float("inf")):
                    g_score[nb]   = ng
                    came_from[nb] = node
                    heapq.heappush(open_set, (ng + h(nb), ng, nb))
        else:
            # No roads built: traverse grid adjacency with unit cost
            for nb in city.neighbors(node):
                if nb not in active_set:
                    continue
                ng = g + 1.0
                if ng < g_score.get(nb, float("inf")):
                    g_score[nb]   = ng
                    came_from[nb] = node
                    heapq.heappush(open_set, (ng + h(nb), ng, nb))

    return []   # goal unreachable


def _route_has_block(city, route: list, from_idx: int) -> bool:
    """Return True if any edge on route[from_idx:] is currently blocked."""
    for i in range(from_idx, len(route) - 1):
        u, v = route[i], route[i + 1]
        edge = city.roads.get(u, {}).get(v, {})
        if isinstance(edge, dict) and edge.get("blocked", False):
            return True
    return False


# ── Mission Controller ────────────────────────────────────────────────────────

class EmergencyMission:
    """
    Manages the full state of one emergency mission:

      - Plans an A* route from the team's current position through all
        remaining civilian waypoints in order.
      - Tracks step-by-step team advancement along that route.
      - Detects blocked roads on the route ahead and re-routes with A*.
      - Records statistics: total travel cost, re-route count, civilians reached.

    Workflow:
        m = EmergencyMission(city, start_node, [civ1, civ2, civ3])
        while not m.is_done:
            new_pos, reached = m.advance()
            # if road state changed:
            m.check_reroute()
    """

    def __init__(self, city, start: int, civilians: list):
        self.city      = city
        self.start     = start
        self.civilians = list(civilians)    # original order — never mutated
        self.remaining = list(civilians)    # shrinks as civilians are reached or skipped
        self.reached   = []                 # civilians actually reached, in arrival order
        self.skipped   = []                 # civilians skipped because no A* path currently exists
        self.last_skipped = []              # civilians skipped during the latest planning/reroute call
        self.reroutes  = 0
        self.total_cost = 0.0
        # "active"           — mission in progress
        # "complete"         — all civilians reached
        # "partial_complete" — reachable civilians handled, unreachable civilians skipped
        # "no_path"          — legacy fallback, kept for compatibility
        self.status    = "active"

        self.route    = []    # current planned path as node IDs
        self.step_idx = 0     # team is at route[step_idx]

        self._plan()

    # ── Internal planning ─────────────────────────────────────────────

    def _plan(self):
        """
        (Re-)compute route from current position through remaining waypoints.

        Important integration behavior:
        If one civilian becomes unreachable because roads are blocked, the mission
        must NOT die immediately. Instead, that civilian is marked as skipped and
        A* continues planning toward the rest of the civilians that are still
        reachable from the team's current position. This lets the 20-step
        simulation continue and demonstrates graceful emergency handling.
        """
        self.last_skipped = []

        if not self.remaining:
            self.status   = "partial_complete" if self.skipped else "complete"
            self.route    = [self.current_pos]
            self.step_idx = 0
            return

        full = []
        pos  = self.current_pos
        reachable_remaining = []

        for target in list(self.remaining):
            seg = astar(self.city, pos, target)
            if not seg:
                # Do not end the whole mission. Mark this civilian unreachable
                # for now and continue checking the next civilians.
                if target not in self.skipped:
                    self.skipped.append(target)
                self.last_skipped.append(target)
                continue

            # Concatenate segments; skip duplicate junction node.
            full = full + (seg[1:] if full else seg)
            pos  = target
            reachable_remaining.append(target)

        self.remaining = reachable_remaining

        if not self.remaining:
            # Every pending civilian was unreachable/skipped. The mission is not
            # a total failure; it is complete for all currently reachable targets.
            self.status   = "partial_complete" if self.skipped else "complete"
            self.route    = [self.current_pos]
            self.step_idx = 0
            return

        self.route    = full if full else [self.current_pos]
        self.step_idx = 0
        self.status   = "active"

    # ── Team advancement ──────────────────────────────────────────────

    def advance(self):
        """
        Move team one step forward along the current route.
        Returns (new_position, civilian_node_if_just_reached_else_None).
        No-ops (returns current position) when mission is done or at route end.
        """
        if self.status != "active":
            return self.current_pos, None
        if self.step_idx + 1 >= len(self.route):
            return self.current_pos, None

        prev          = self.current_pos
        self.step_idx += 1
        new_pos       = self.route[self.step_idx]

        # Accumulate travel cost for this step
        edge = self.city.roads.get(prev, {}).get(new_pos, {})
        if isinstance(edge, dict):
            base = edge.get("cost", 1.0)
            if "base_cost" in edge:
                self.total_cost += base
            else:
                risk = getattr(self.city, "risk_index", {}).get(new_pos, 0.0)
                self.total_cost += base * (1.0 + risk)
        else:
            base = float(edge) if edge else 1.0
            risk = getattr(self.city, "risk_index", {}).get(new_pos, 0.0)
            self.total_cost += base * (1.0 + risk)

        # Check if we just reached the NEXT expected civilian (strict sequential order).
        # We only count arrival when the team reaches remaining[0], not any civilian
        # encountered incidentally along the route to the current target.
        reached = None
        if self.remaining and new_pos == self.remaining[0]:
            reached = new_pos
            self.reached.append(new_pos)
            self.remaining.pop(0)
            if not self.remaining:
                self.status = "partial_complete" if self.skipped else "complete"
            else:
                self._plan()   # re-plan from here to remaining/skippable waypoints

        return new_pos, reached

    # ── Dynamic re-routing ────────────────────────────────────────────

    def check_reroute(self) -> bool:
        """
        Inspect every road on the planned route ahead.
        If any is blocked, immediately re-plan from the current position.
        Returns True if a re-route was triggered, False otherwise.

        Call this any time road state changes (road blocked/unblocked).
        """
        if self.status != "active":
            return False
        if city_route_blocked(self.city, self.route, self.step_idx):
            self.reroutes += 1
            self._plan()
            return True
        return False

    # ── Read-only properties ──────────────────────────────────────────

    @property
    def current_pos(self) -> int:
        if not self.route:
            return self.start
        return self.route[min(self.step_idx, len(self.route) - 1)]

    @property
    def path_ahead(self) -> list:
        """Route from the team's current position onward (for display)."""
        return self.route[self.step_idx:]

    @property
    def at_route_end(self) -> bool:
        return self.step_idx >= len(self.route) - 1

    @property
    def is_done(self) -> bool:
        return self.status in ("complete", "partial_complete", "no_path")


def city_route_blocked(city, route: list, from_idx: int) -> bool:
    """Module-level alias used by EmergencyMission.check_reroute."""
    return _route_has_block(city, route, from_idx)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_challenge4(city, start: int, civilians: list) -> EmergencyMission:
    """
    Create and return an EmergencyMission.
    Prints a summary to stdout (captured by GUI's redirect_stdout).
    """
    print("\n" + "=" * 60)
    print("  CityMind - Challenge 4: Emergency Routing")
    print("=" * 60)
    print(f"  Algorithm   : A* with admissible Manhattan heuristic")
    print(f"  Start node  : {city.coords(start)}")
    for i, civ in enumerate(civilians):
        print(f"  Civilian {i+1}  : {city.coords(civ)}")

    mission = EmergencyMission(city, start, civilians)

    if mission.status == "active":
        total_steps = len(mission.route) - 1
        print(f"\n  Route planned : {total_steps} steps through {len(civilians)} waypoints")
        print(f"  Heuristic     : h(n) = Manhattan × 0.8  (admissible)")
        print(f"  Roads built   : {'Yes — using road costs + risk' if city.roads else 'No — using grid adjacency'}")
        print(f"\n  Mission is ACTIVE. Advance the team step by step.")
        print(f"  Blocking a road will trigger immediate A* re-routing.")
    elif mission.status == "partial_complete":
        print(f"\n  Partial mission prepared: {len(mission.skipped)} civilian(s) are currently unreachable and were skipped.")
        print(f"  Reachable civilians will still be handled instead of ending the mission.")
    elif mission.status == "no_path":
        print(f"\n  ERROR: No path found to all civilians.")
        print(f"  Try unblocking roads or building the road network (Ch2).")
    print("=" * 60)

    return mission


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os, io
    sys.path.insert(0, os.path.dirname(__file__))
    from challenge1 import CityLayoutManager
    from contextlib import redirect_stdout

    tc  = {"Residential": 6, "Hospital": 2, "School": 2,
           "Industrial": 2, "PowerPlant": 2, "AmbulanceDepot": 1}
    mgr = CityLayoutManager()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mgr.initialize(5, 5, sum(tc.values()), tc, 300, 500)

    city = mgr.city
    city.build_road_network()

    start = next(n for n in city.active_nodes
                 if city.assignment.get(n) == "AmbulanceDepot")
    civilians = [n for n in city.active_nodes
                 if city.assignment.get(n) == "Residential"][:3]

    print(f"Start: {city.coords(start)}")
    print(f"Civilians: {[city.coords(c) for c in civilians]}")

    m = run_challenge4(city, start, civilians)
    print(f"\nRoute length: {len(m.route)} nodes")
    while not m.is_done:
        pos, reached = m.advance()
        if reached is not None:   # must use 'is not None' — node_id 0 is falsy
            print(f"  Reached civilian at {city.coords(reached)}")
    print(f"Mission complete. Cost={m.total_cost:.2f}, Reroutes={m.reroutes}")
