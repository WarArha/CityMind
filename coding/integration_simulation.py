"""
CityMind - System Integration Simulation (20 Steps)
===================================================

This module connects Challenge 1-5 into one shared 20-step simulation.
It is designed to plug into the existing CityMind project files:

    challenge1.py, challenge2.py, challenge3.py, challenge4.py, challenge5.py

What it demonstrates per project statement:
  1. Challenge 1 city layout is the initial state.
  2. Challenge 2 road network defines the travel graph.
  3. Challenge 5 crime-risk predictions update shared graph weights at start.
  4. Challenge 3 ambulance placement is re-evaluated as risk shifts.
  5. Random flooding blocks roads, and Challenge 4 A* re-routes immediately.

The important integration rule is preserved: every component reads/writes the
same CityGraph object. No module receives a private copy of the graph.
"""

from __future__ import annotations

import io
import random
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from challenge2 import RoadNetworkBuilder
from challenge3 import run_challenge3
from challenge4 import run_challenge4
from challenge5 import run_challenge5, RISK_VALUES

LogFn = Callable[[str], None]


@dataclass
class SimulationState:
    """Small return object so GUI/main code can inspect final simulation state."""
    steps_completed: int = 0
    road_builder: Optional[RoadNetworkBuilder] = None
    primary_hospital: Optional[int] = None
    ambulance_depot: Optional[int] = None
    ambulance_nodes: List[int] = field(default_factory=list)
    crime_risk: Dict[int, float] = field(default_factory=dict)
    crime_predictions: Dict[int, str] = field(default_factory=dict)
    police_deployment: Dict[int, int] = field(default_factory=dict)
    emergency_mission: object = None
    flooded_edges: Set[frozenset] = field(default_factory=set)
    reroutes: int = 0
    mission_status: str = "not_started"


class CityMindIntegrationSimulation:
    """
    Runs the complete 20-step integration scenario on the existing shared city.

    Pass gui=<CityMindGUI instance> when using the pygame interface. The simulator
    will update these existing GUI fields when present:
        road_builder, primary_hospital_id, ambulance_nodes, crime_risk,
        _ch5_predictions, _ch5_deployment, _em_mission, emergency_route.

    Pass only city=<CityGraph> to run it headlessly from a terminal.
    """

    def __init__(
        self,
        city,
        gui=None,
        steps: int = 20,
        seed: Optional[int] = None,
        log: Optional[LogFn] = None,
    ):
        self.city = city
        self.gui = gui
        self.steps = steps
        self.random = random.Random(seed)
        self.log = log or (gui._log if gui is not None and hasattr(gui, "_log") else print)
        self.state = SimulationState()
        self._prepared = False
        self._finished = False

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def prepare(self) -> SimulationState:
        """Run one-time setup before the first simulation step.

        This is used by the GUI stepper so the user can inspect every
        step manually instead of the whole scenario finishing instantly.
        """
        if getattr(self, "_prepared", False):
            return self.state

        self._log("SIM: Preparing 20-step system integration scenario.")
        self._log("SIM: One shared CityGraph will be used by layout, roads, risk, ambulances and routing.")

        self._ensure_risk_storage()
        self._ensure_roads()
        self._run_initial_crime_risk()
        self._place_ambulances(reason="initial risk-weighted placement")
        self._start_emergency_mission()

        self._prepared = True
        self._finished = False
        self._log("SIM READY: click 'Next Sim Step' to advance from step 1 to step 20.")
        return self.state

    def step_once(self) -> SimulationState:
        """Advance exactly one simulation step and then pause for inspection."""
        self.prepare()

        if getattr(self, "_finished", False):
            self._log("SIM: already complete. Reset/restart the city to run again.")
            return self.state

        next_step = self.state.steps_completed + 1
        if next_step > self.steps:
            self._finish()
            return self.state

        step = next_step
        self.state.steps_completed = step
        self._log(f"SIM STEP {step:02d}/{self.steps}")

        # Risk shifts first, so road/routing modules see the new graph state.
        if step == 1 or step % 3 == 0:
            changed = self._shift_risk_weights()
            self._log(f"  Risk shift: {changed} node(s) adjusted; shared city.risk_index updated.")

        # Flooding happens randomly and immediately mutates city.roads.
        flood_event = self._random_flood_event(step)
        if flood_event:
            u, v, action = flood_event
            self._log(f"  Flood event: road {self._coords(u)} <-> {self._coords(v)} {action}.")

        # The mission must check route validity immediately after road changes.
        self._check_dynamic_reroute()

        # Re-evaluate ambulance placement as risk shifts during the scenario.
        if step in (5, 10, 15, 20):
            self._place_ambulances(reason=f"risk re-evaluation at step {step}")

        # Advance emergency team one movement after all current graph changes.
        self._advance_mission_one_step()

        # Push current state to GUI each cycle and stop here for user inspection.
        self._publish_to_gui()
        self._log(f"SIM PAUSED: step {step:02d} complete. Inspect the GUI, then click Next Sim Step.")

        if step >= self.steps:
            self._finish()
        return self.state

    def run(self) -> SimulationState:
        """Run all steps without pausing. Kept for terminal/headless use."""
        self.prepare()
        while not getattr(self, "_finished", False):
            self.step_once()
        return self.state

    def _finish(self):
        if getattr(self, "_finished", False):
            return
        m = self.state.emergency_mission
        self.state.mission_status = getattr(m, "status", "not_started")
        self.state.reroutes = getattr(m, "reroutes", 0) if m is not None else 0
        self._finished = True
        self._log("SIM COMPLETE: 20 integration steps finished.")
        self._log(f"  Mission status={self.state.mission_status}; reroutes={self.state.reroutes}; flooded roads={len(self.state.flooded_edges)}.")

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    def _ensure_risk_storage(self):
        if not hasattr(self.city, "risk_index"):
            self.city.risk_index = {}
        for nid in self._active_nodes():
            self.city.risk_index.setdefault(nid, 0.0)

    def _ensure_roads(self):
        """Guarantee Challenge 2 road metadata exists before simulation begins."""
        if self.gui is not None and getattr(self.gui, "road_builder", None) is not None:
            self.state.road_builder = self.gui.road_builder
            self.state.primary_hospital = getattr(self.gui, "primary_hospital_id", None)
            self.state.ambulance_depot = getattr(self.state.road_builder, "ambulance_depot", None)
            if self.state.primary_hospital is None:
                self.state.primary_hospital = getattr(self.state.road_builder, "primary_hospital", None)
            self._log("SIM: Reusing road network already built in GUI.")
            return

        ph = self._first_node_of_type("Hospital")
        ad = self._first_node_of_type("AmbulanceDepot")
        if ph is None:
            raise RuntimeError("Simulation cannot start: no Hospital node exists.")
        if ad is None:
            raise RuntimeError("Simulation cannot start: no AmbulanceDepot node exists.")

        builder = RoadNetworkBuilder(self.city)
        builder.primary_hospital = ph
        builder.ambulance_depot = ad
        buf = io.StringIO()
        with redirect_stdout(buf):
            all_edges = builder._get_candidate_edges()
            builder._run_kruskals(all_edges)
            builder._second_path_augmentation()
            builder._write_to_city_graph(blocked_edges=None)
            safe, failing = builder._verify_safety()

        self.state.road_builder = builder
        self.state.primary_hospital = ph
        self.state.ambulance_depot = ad
        self._log(f"SIM: Ch2 roads built automatically. Primary Hospital={self._coords(ph)}, Depot={self._coords(ad)}.")
        if safe:
            self._log("  Safety check passed: independent Hospital-Depot backup route exists.")
        else:
            self._log("  Safety warning: full independent-route guarantee could not be proven.")
            for msg in failing[:2]:
                self._log("    " + msg)
        self._publish_to_gui()

    def _run_initial_crime_risk(self):
        """Run Challenge 5 once at the start, then normalize costs to avoid double-counting risk."""
        self._log("SIM: Running Ch5 crime-risk prediction before step 1.")

        def cb(msg):
            text = str(msg)
            if text.startswith("Done") or "Phase" in text or "Updating" in text:
                self._log("  Ch5: " + text)

        pipeline = run_challenge5(self.city, callback=cb)
        self.state.crime_predictions = dict(getattr(pipeline, "predictions", {}))
        self.state.police_deployment = dict(getattr(pipeline, "deployment", {}))
        self.state.crime_risk = {nid: RISK_VALUES[label] for nid, label in self.state.crime_predictions.items()}

        # Your Ch3 and Ch4 already multiply edge cost by (1 + city.risk_index).
        # Ch5 also writes adjusted edge["cost"]. Reset cost to base_cost here so
        # simulation applies the multiplier exactly once, not twice.
        self._reset_edge_costs_to_base()

        counts = {"High": 0, "Medium": 0, "Low": 0}
        for label in self.state.crime_predictions.values():
            counts[label] = counts.get(label, 0) + 1
        self._log(f"SIM: Ch5 integrated. Risk counts H={counts['High']} M={counts['Medium']} L={counts['Low']}.")
        self._publish_to_gui()

    def _start_emergency_mission(self):
        start = None
        if self.state.ambulance_nodes:
            start = self.state.ambulance_nodes[0]
        if start is None:
            start = self._first_node_of_type("AmbulanceDepot") or self._first_node_of_type("Hospital")
        if start is None:
            raise RuntimeError("Simulation cannot start emergency mission: no valid start node.")

        civilians = self._choose_civilians(start=start, count=5)
        if not civilians:
            raise RuntimeError("Simulation cannot start: no civilian/target nodes available.")

        buf = io.StringIO()
        with redirect_stdout(buf):
            mission = run_challenge4(self.city, start, civilians)
        self.state.emergency_mission = mission
        self._log(f"SIM: Ch4 mission started from {self._coords(start)} with {len(civilians)} civilian target(s).")
        if getattr(mission, "status", None) == "active":
            self._log(f"  Initial A* route length: {len(mission.route)-1} step(s).")
        else:
            self._log("  WARNING: A* could not find an initial full route.")
        self._publish_to_gui()

    # ------------------------------------------------------------------
    # Per-step events
    # ------------------------------------------------------------------
    def _shift_risk_weights(self) -> int:
        """Small stochastic risk drift to force downstream modules to react."""
        active = self._active_nodes()
        if not active:
            return 0
        k = max(1, len(active) // 5)
        changed_nodes = self.random.sample(active, min(k, len(active)))
        for nid in changed_nodes:
            old = self.city.risk_index.get(nid, 0.1)
            delta = self.random.choice([-0.10, -0.05, 0.05, 0.10])
            new = max(0.0, min(0.9, round(old + delta, 2)))
            self.city.risk_index[nid] = new
            self.state.crime_risk[nid] = new
        self._reset_edge_costs_to_base()
        return len(changed_nodes)

    def _random_flood_event(self, step: int):
        """
        Randomly block an unblocked road. Occasionally clear one old flood so the
        simulation remains dynamic instead of becoming permanently disconnected.
        """
        if not self.city.roads:
            return None
        edges = self._unique_edges()
        if not edges:
            return None

        # Every 4th step tries to clear a flooded road; otherwise flooding may add one.
        if step % 4 == 0 and self.state.flooded_edges:
            key = self.random.choice(list(self.state.flooded_edges))
            u, v = tuple(key)
            self._set_blocked(u, v, False)
            self.state.flooded_edges.discard(key)
            return u, v, "cleared"

        # 65% chance of a flood each step, but force at least one early event.
        should_flood = step in (2, 6, 11, 16) or self.random.random() < 0.65
        if not should_flood:
            return None

        open_edges = [(u, v) for (u, v) in edges if not self._is_blocked(u, v)]
        if not open_edges:
            return None
        u, v = self.random.choice(open_edges)
        self._set_blocked(u, v, True)
        self.state.flooded_edges.add(frozenset({u, v}))
        return u, v, "blocked"

    def _check_dynamic_reroute(self):
        m = self.state.emergency_mission
        if m is None or getattr(m, "status", None) != "active":
            return
        before = getattr(m, "reroutes", 0)
        skipped_before = len(getattr(m, "skipped", []))
        rerouted = m.check_reroute()
        after = getattr(m, "reroutes", 0)
        skipped_after = len(getattr(m, "skipped", []))
        self.state.reroutes = after
        if rerouted:
            if skipped_after > skipped_before:
                skipped_now = getattr(m, "last_skipped", [])
                coords = ", ".join(self._coords(n) for n in skipped_now) if skipped_now else "unknown"
                self._log(f"  Ch4: {skipped_after - skipped_before} unreachable civilian(s) skipped for now: {coords}.")
                self._log("  Ch4: mission continues toward the remaining reachable civilians.")
            if getattr(m, "status", None) == "active":
                self._log(f"  Ch4: blocked route detected -> A* re-routed immediately. Reroutes={after}.")
                self._log(f"  Ch4: new path ahead has {max(0, len(m.path_ahead)-1)} step(s).")
            elif getattr(m, "status", None) == "partial_complete":
                self._log(f"  Ch4: no reachable civilians remain; partial mission complete with {len(getattr(m, 'skipped', []))} skipped.")
            else:
                self._log("  Ch4: route blocked and no alternate A* path currently exists.")
        elif after != before:
            self._log(f"  Ch4: reroute counter changed to {after}.")

    def _advance_mission_one_step(self):
        m = self.state.emergency_mission
        if m is None:
            return
        if getattr(m, "status", None) != "active":
            status = getattr(m, 'status', 'unknown')
            if status == "partial_complete":
                self._log(f"  Ch4: reachable-civilian mission complete; skipped={len(getattr(m, 'skipped', []))}, reached={len(getattr(m, 'reached', []))}.")
            else:
                self._log(f"  Ch4: mission status is {status}; team cannot advance this step.")
            return
        if getattr(m, "at_route_end", False):
            self._log("  Ch4: team is at current route end; waiting for route update.")
            return
        new_pos, reached = m.advance()
        self._log(f"  Ch4: team advanced to {self._coords(new_pos)}.")
        if reached is not None:
            self._log(f"  Ch4: civilian reached at {self._coords(reached)} ({len(m.reached)}/{len(m.civilians)}).")
        status = getattr(m, "status", None)
        if status == "complete":
            self._log(f"  Ch4: mission complete. Total travel cost={m.total_cost:.2f}.")
        elif status == "partial_complete":
            self._log(f"  Ch4: reachable-civilian mission complete. Reached={len(m.reached)}, skipped={len(getattr(m, 'skipped', []))}, cost={m.total_cost:.2f}.")

    # ------------------------------------------------------------------
    # Challenge 3 integration
    # ------------------------------------------------------------------
    def _place_ambulances(self, reason: str):
        self._log(f"SIM: Running Ch3 ambulance GA ({reason}).")

        def cb(gen, worst):
            # Keep event log readable during simulation.
            if gen in (0, 50, 100):
                if gen == 0:
                    self._log("  Ch3: distance matrix ready; GA evolving.")
                else:
                    self._log(f"  Ch3: generation {gen}, worst-case={worst:.2f}.")

        ga = run_challenge3(self.city, callback=cb)
        self.state.ambulance_nodes = list(ga.best_placement or [])
        coords = [self._coords(n) for n in self.state.ambulance_nodes]
        self._log(f"  Ch3: selected ambulances at {coords}; worst-case={ga.best_worst_case:.2f}.")

        # Update GUI's coverage map if possible.
        if self.gui is not None:
            coverage = {}
            for nid, _amb, dist in ga.coverage_report():
                coverage[nid] = dist
            self.gui._amb_coverage = coverage
            self.gui._ga_worst = ga.best_worst_case
            self.gui._ga_gens = ga.generations_run
        self._publish_to_gui()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _publish_to_gui(self):
        if self.gui is None:
            return
        self.gui.road_builder = self.state.road_builder
        self.gui.primary_hospital_id = self.state.primary_hospital
        self.gui.ambulance_nodes = list(self.state.ambulance_nodes)
        self.gui.crime_risk = dict(self.state.crime_risk)
        self.gui._ch5_predictions = dict(self.state.crime_predictions)
        self.gui._ch5_deployment = dict(self.state.police_deployment)
        self.gui._em_mission = self.state.emergency_mission
        if self.state.emergency_mission is not None:
            self.gui.emergency_route = self.state.emergency_mission.path_ahead
        if hasattr(self.gui, "_pending_view"):
            self.gui._pending_view = "Emergency"

    def _active_nodes(self) -> List[int]:
        return [n for n in self.city.active_nodes if self.city.assignment.get(n) is not None]

    def _first_node_of_type(self, loc_type: str) -> Optional[int]:
        return next((n for n in self.city.active_nodes if self.city.assignment.get(n) == loc_type), None)

    def _choose_civilians(self, start: int, count: int) -> List[int]:
        active = [n for n in self._active_nodes() if n != start]
        if not active:
            return []
        # Prefer residential/high-risk nodes to make the route meaningful.
        def score(n):
            residential_bonus = 1.0 if self.city.assignment.get(n) == "Residential" else 0.0
            risk = self.city.risk_index.get(n, 0.0)
            r1, c1 = self.city.coords(start)
            r2, c2 = self.city.coords(n)
            distance = abs(r1-r2) + abs(c1-c2)
            return (residential_bonus, risk, distance)
        ranked = sorted(active, key=score, reverse=True)
        return ranked[: min(count, len(ranked))]

    def _unique_edges(self) -> List[Tuple[int, int]]:
        seen = set()
        result = []
        for u, nbrs in self.city.roads.items():
            for v in nbrs:
                key = frozenset({u, v})
                if key not in seen:
                    seen.add(key)
                    result.append((u, v))
        return result

    def _is_blocked(self, u: int, v: int) -> bool:
        edge = self.city.roads.get(u, {}).get(v)
        return isinstance(edge, dict) and edge.get("blocked", False)

    def _set_blocked(self, u: int, v: int, blocked: bool):
        for a, b in ((u, v), (v, u)):
            edge = self.city.roads.get(a, {}).get(b)
            if isinstance(edge, dict):
                edge["blocked"] = blocked

    def _reset_edge_costs_to_base(self):
        """Keep edge['cost'] as base; Ch3/Ch4 apply risk_index during path search."""
        for u, nbrs in self.city.roads.items():
            for v, edge in nbrs.items():
                if isinstance(edge, dict):
                    base = edge.get("base_cost", edge.get("cost", 1.0))
                    edge["base_cost"] = base
                    edge["cost"] = base
                    edge["effective_cost"] = base * (1.0 + self.city.risk_index.get(v, 0.0))
                    edge["risk_multiplier"] = 1.0 + self.city.risk_index.get(v, 0.0)

    def _coords(self, nid: Optional[int]):
        if nid is None:
            return "None"
        try:
            return self.city.coords(nid)
        except Exception:
            return nid

    def _log(self, msg: str):
        self.log(str(msg))


def create_integration_simulation(city, gui=None, steps: int = 20, seed: Optional[int] = None, log: Optional[LogFn] = None) -> CityMindIntegrationSimulation:
    """Create a step-controlled simulator for GUI use."""
    return CityMindIntegrationSimulation(city=city, gui=gui, steps=steps, seed=seed, log=log)


def run_integration_simulation(city, gui=None, steps: int = 20, seed: Optional[int] = None, log: Optional[LogFn] = None) -> SimulationState:
    """Convenience wrapper used by GUI button or terminal code."""
    sim = create_integration_simulation(city=city, gui=gui, steps=steps, seed=seed, log=log)
    return sim.run()
